import base64
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round, html2plaintext

from .mysoft_api import anahtar_bul, liste_bul, sadece_rakam, zipten_dosya

_logger = logging.getLogger(__name__)

MYSOFT_DURUMLARI = [
    ('gonderilmedi', 'Gönderilmedi'),
    ('kuyrukta', 'Gönderim Kuyruğunda'),
    ('taslak', 'MySoft\'ta Taslak'),
    ('gonderildi', 'GİB\'e Gönderildi'),
    ('basarili', 'Alıcıya Ulaştı'),
    ('kabul', 'Alıcı Kabul Etti'),
    ('red', 'Alıcı Reddetti'),
    ('hata', 'Hata'),
    ('iptal', 'İptal Edildi'),
]
# UN/ECE Rec 20 birim kodları (GİB e-Fatura kod listesi)
BIRIM_KODLARI = {
    'units': 'C62', 'unit': 'C62', 'adet': 'C62', 'dozen': 'DZN', 'düzine': 'DZN', 'pack of 6': 'PA', 'paket': 'PA',
    'kg': 'KGM', 'g': 'GRM', 'mg': 'MGM', 't': 'TNE', 'ton': 'TNE',
    'l': 'LTR', 'litre': 'LTR', 'ml': 'MLT', 'm³': 'MTQ', 'm3': 'MTQ',
    'm': 'MTR', 'mm': 'MMT', 'cm': 'CMT', 'km': 'KMT', 'm²': 'MTK', 'm2': 'MTK',
    'hours': 'HUR', 'hour': 'HUR', 'saat': 'HUR', 'days': 'DAY', 'day': 'DAY', 'gün': 'DAY', 'minutes': 'D61', 'dakika': 'D61',
    'months': 'MON', 'ay': 'MON', 'kwh': 'KWH',
}
TASIMA_MODLARI = [('1', 'Deniz'), ('2', 'Demiryolu'), ('3', 'Karayolu'), ('4', 'Hava'), ('5', 'Posta'), ('6', 'Çok araçlı'),
                  ('7', 'Sabit tesisat'), ('8', 'İç su'), ('9', 'Kendi gücüyle')]


def tutar(deger, hane=2):
    return float_round(deger or 0.0, precision_digits=hane)


def durum_eslestir(metin):
    """MySoft durum metnini Atlas durumuna çevirir (kod/ad biçimi belgelenmediği için anahtar kelimeyle)."""
    m = (str(metin or '')).upper().replace('İ', 'I').replace('Ş', 'S').replace('Ğ', 'G').replace('Ü', 'U').replace('Ö', 'O').replace('Ç', 'C')
    if not m:
        return None
    if 'IPTAL' in m or 'CANCEL' in m:
        return 'iptal'
    if 'RED' in m or 'REJECT' in m or 'DENY' in m:
        return 'red'
    if 'KABUL' in m or 'ACCEPT' in m:
        return 'kabul'
    if 'HATA' in m or 'ERROR' in m or 'BASARISIZ' in m or 'FAIL' in m:
        return 'hata'
    if 'TASLAK' in m or 'DRAFT' in m:
        return 'taslak'
    if 'BASARI' in m or 'SUCCESS' in m or 'TAMAM' in m or 'ULASTI' in m or 'DELIVER' in m or 'ARSIVLENDI' in m or 'RAPORLANDI' in m:
        return 'basarili'
    return 'gonderildi'


class UomUom(models.Model):
    _inherit = 'uom.uom'

    atlas_birim_kodu = fields.Char(string='e-Belge Birim Kodu', help='UN/ECE birim kodu (ör. C62 adet, KGM kilogram). Boşsa addan tahmin edilir.')

    def _atlas_birim_kodu(self):
        self.ensure_one()
        return self.atlas_birim_kodu or BIRIM_KODLARI.get((self.name or '').strip().lower(), 'C62')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    atlas_gtip = fields.Char(string='GTİP', size=12, help='Gümrük tarife istatistik pozisyonu (ihracat faturası için).')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_atlas_mukellef_sorgula(self):
        for partner in self:
            partner._atlas_mukellef_sorgula(hata_yut=False)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'info', 'message': ', '.join(
                    f"{p.name}: {self.env._('e-Fatura mükellefi') if p.atlas_efatura_mukellef else self.env._('e-Arşiv')}" for p in self),
                    'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def _atlas_mukellef_sorgula(self, company=None, hata_yut=True):
        """GİB kayıtlı kullanıcı listesinden mükellefiyet ve posta kutusu etiketini getirir."""
        self.ensure_one()
        ticari = self.commercial_partner_id
        vkn = sadece_rakam(ticari.vat)
        company = company or self.env.company
        if len(vkn) not in (10, 11):
            return False
        try:
            yanit = self.env['atlas.mysoft.api']._istek(company, 'GET', '/api/GeneralCard/getGibAccountModel',
                                                        params={'vknTckn': vkn}, islem='Mükellef sorgu', kayit=ticari)
        except UserError:
            if hata_yut:
                _logger.info('MySoft mükellef sorgusu başarısız: %s', vkn)
                return False
            raise
        etiketler = []
        yigin = [yanit]
        while yigin:
            oge = yigin.pop()
            if isinstance(oge, dict):
                yigin.extend(oge.values())
            elif isinstance(oge, list):
                yigin.extend(oge)
            elif isinstance(oge, str) and oge.startswith('urn:mail:'):
                etiketler.append(oge)
        pk = next((e for e in etiketler if 'pk' in e.lower()), etiketler[0] if etiketler else False)
        ticari.sudo().write({'atlas_efatura_mukellef': bool(pk), 'atlas_efatura_etiket': pk or False,
                             'atlas_efatura_kontrol': fields.Date.context_today(self)})
        return bool(pk)


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_mysoft_durum = fields.Selection(MYSOFT_DURUMLARI, string='e-Belge Durumu', default='gonderilmedi', copy=False,
                                          tracking=True, index=True)
    atlas_mysoft_durum_metin = fields.Char(string='MySoft Durumu', copy=False, readonly=True)
    atlas_mysoft_mesaj = fields.Text(string='MySoft Mesajı', copy=False, readonly=True)
    atlas_mysoft_tarih = fields.Datetime(string='Gönderim Zamanı', copy=False, readonly=True)
    atlas_mysoft_belge_no = fields.Char(string='e-Belge No', copy=False, readonly=True)
    atlas_mysoft_gosterilsin = fields.Boolean(compute='_compute_atlas_mysoft_gosterilsin')
    atlas_tasima_modu = fields.Selection(TASIMA_MODLARI, string='Gönderim Şekli', help='İhracat faturası için taşıma modu.')
    atlas_kap_cinsi = fields.Char(string='Kap Cinsi', default='PK', help='İhracatta kap cinsi kodu (ör. PK paket, BX kutu, PL palet).')
    atlas_kap_adedi = fields.Integer(string='Kap Adedi', default=1)

    @api.depends('atlas_ebelge_tipi', 'company_id.atlas_mysoft_aktif', 'move_type')
    def _compute_atlas_mysoft_gosterilsin(self):
        for move in self:
            move.atlas_mysoft_gosterilsin = bool(move.company_id.atlas_mysoft_aktif and move.atlas_ebelge_tipi in ('efatura', 'earsiv')
                                                 and move.move_type in ('out_invoice', 'in_refund'))

    # -------------------------------------------------------------------------
    # Onay
    # -------------------------------------------------------------------------

    def _post(self, soft=True):
        # Mükellefiyeti 7 günden eski/hiç sorgulanmamış alıcılar onaydan önce sorgulanır (bağlantı yoksa sessizce geçer)
        sinir = fields.Date.context_today(self) - timedelta(days=7)
        for move in self.filtered(lambda m: m.state == 'draft' and m.is_invoice() and m.company_id.atlas_mysoft_aktif
                                  and m._atlas_ebelge_uygun() and not m._atlas_ihracat_mi()):
            ticari = move.partner_id.commercial_partner_id
            if ticari.vat and (not ticari.atlas_efatura_kontrol or ticari.atlas_efatura_kontrol < sinir):
                once = ticari.atlas_efatura_mukellef
                move.partner_id._atlas_mukellef_sorgula(move.company_id)
                if ticari.atlas_efatura_mukellef != once:
                    move._compute_atlas_ebelge()
                    move._compute_atlas_seri_id()
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.atlas_mysoft_gosterilsin and m.company_id.atlas_mysoft_otomatik
                                    and m.atlas_mysoft_durum == 'gonderilmedi'):
            move.atlas_mysoft_durum = 'kuyrukta'
        return posted

    def button_draft(self):
        gonderilmis = self.filtered(lambda m: m.atlas_mysoft_durum in ('gonderildi', 'basarili', 'kabul', 'taslak'))
        if gonderilmis:
            raise UserError(self.env._('GİB\'e gönderilmiş e-Belge taslağa alınamaz: %s. e-Arşiv ise önce iptal edin; '
                                       'e-Fatura için iade faturası düzenleyin.', ', '.join(gonderilmis.mapped('name'))))
        return super().button_draft()

    # -------------------------------------------------------------------------
    # İstek gövdesi
    # -------------------------------------------------------------------------

    def _atlas_kur(self):
        self.ensure_one()
        if self.currency_id == self.company_id.currency_id or not self.amount_total:
            return 1.0
        return float_round(abs(self.amount_total_signed) / self.amount_total, precision_digits=6)

    def _atlas_hesap_json(self):
        p = self.partner_id
        ticari = p.commercial_partner_id
        ulke = (p.country_id or ticari.country_id)
        return {
            'vknTckn': sadece_rakam(ticari.vat) or ('2222222222' if self.atlas_ebelge_senaryo == 'IHRACAT' else '11111111111'),
            'accountName': ticari.name,
            'taxOfficeName': ticari.l10n_tr_tax_office_id.name if 'l10n_tr_tax_office_id' in ticari._fields and ticari.l10n_tr_tax_office_id else None,
            'countryName': (ulke.name or 'Türkiye').upper() if ulke.code in (False, 'TR') else ulke.name,
            'cityName': (p.state_id.name or p.city or ticari.city or '').upper() or None,
            'citySubdivision': (p.city if p.state_id else '') or p.street2 or None,
            'streetName': ' '.join(filter(None, [p.street, p.street2 if p.state_id else None])) or None,
            'postalCode': p.zip or None,
            'telephone1': p.phone or ticari.phone or None,
            'email1': p.email or ticari.email or None,
            'webSiteUrl': ticari.website or None,
        }

    def _atlas_satir_vergileri(self, line):
        """Satırın KDV oranı/tutarı, tevkifat ve istisna bilgisi."""
        para = self.currency_id
        hesap = line.tax_ids.compute_all(line.price_unit * (1 - (line.discount or 0) / 100), currency=para, quantity=line.quantity,
                                         product=line.product_id, partner=self.partner_id, is_refund=self.move_type == 'in_refund')
        kdv_orani = kdv = tevkif = 0.0
        tevkif_kod = None
        istisna = None
        ihrac_kayitli = False
        for vergi in line.tax_ids:
            if vergi.amount_type == 'group':
                pozitif = vergi.children_tax_ids.filtered(lambda c: c.amount > 0)[:1]
                negatif = vergi.children_tax_ids.filtered(lambda c: c.amount < 0)[:1]
                kdv_orani = pozitif.amount
                kod = vergi.atlas_gib_kod_id or negatif.atlas_gib_kod_id
                if kod.tip == 'ihrac_kayitli':
                    # ihraç kayıtlı: KDV hesaplanır ama tahsil edilmez → istisna kodu (701-704)
                    ihrac_kayitli, istisna = True, kod
                elif negatif:
                    tevkif_kod = kod
            elif vergi.amount_type == 'percent' and vergi.amount >= 0:
                kdv_orani = vergi.amount
                if not vergi.amount and vergi.atlas_gib_kod_id:
                    istisna = vergi.atlas_gib_kod_id
        for t in hesap['taxes']:
            if t['amount'] >= 0:
                kdv += t['amount']
            elif not ihrac_kayitli:
                tevkif += -t['amount']
        if not kdv_orani and not istisna:
            istisna = self.fiscal_position_id.atlas_gib_kod_id if self.fiscal_position_id.atlas_gib_kod_id.tip != 'tevkifat' else None
        return {'oran': kdv_orani, 'kdv': tutar(kdv), 'tevkif': tutar(tevkif), 'tevkif_kod': tevkif_kod, 'istisna': istisna,
                'ihrac_kayitli': ihrac_kayitli, 'matrah': tutar(hesap['total_excluded'])}

    def _atlas_mysoft_json(self):
        self.ensure_one()
        company = self.company_id
        satirlar, vergi_ozet = [], {}
        brut_toplam = indirim_toplam = kdv_toplam = tevkif_toplam = 0.0
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            v = self._atlas_satir_vergileri(line)
            if line.quantity <= 0:
                raise UserError(self.env._('e-Belgede negatif/sıfır miktar olamaz (%s). İndirim için satır iskontosu kullanın.', line.name))
            net = v['matrah']
            birim_fiyat = net / line.quantity / (1 - (line.discount or 0) / 100) if line.discount < 100 else line.price_unit
            brut = tutar(birim_fiyat * line.quantity)
            indirim = tutar(brut - net)
            urun = line.product_id
            detay = {
                'productCode': urun.default_code or None,
                'productName': (line.name or urun.display_name or '').split('\n')[0][:250],
                'unitCode': line.product_uom_id._atlas_birim_kodu() if line.product_uom_id else 'C62',
                'qty': line.quantity,
                'unitPriceTra': float_round(birim_fiyat, precision_digits=6),
                'amtTra': brut,
                'discRate': line.discount or 0,
                'discAmtTra': indirim,
                'vatRate': v['oran'],
                'amtVatTra': v['kdv'],
                'taxableAmtTra': net,
                'note': '\n'.join((line.name or '').split('\n')[1:]) or None,
            }
            if v['tevkif_kod']:
                detay.update({'withholdingTaxTypeCode': v['tevkif_kod'].kod, 'withholdingTaxTypeName': v['tevkif_kod'].name,
                              'withholdingTaxPercentage': round(v['tevkif'] / v['kdv'] * 100) if v['kdv'] else 0,
                              'withholdingTaxableAmount': v['kdv'], 'withholdingTaxAmount': v['tevkif']})
            elif v['tevkif']:
                raise UserError(self.env._('"%s" satırındaki tevkifatlı vergiye GİB tevkifat kodu atanmamış.', line.name))
            if v['ihrac_kayitli']:
                detay.update({'taxExemptionReasonCode': v['istisna'].kod, 'taxExemptionReasonName': v['istisna'].name})
            elif not v['oran'] and not v['tevkif_kod']:
                if v['istisna']:
                    detay.update({'taxExemptionReasonCode': v['istisna'].kod, 'taxExemptionReasonName': v['istisna'].name})
                elif self.atlas_fatura_tipi in ('ISTISNA', 'IHRACKAYITLI') or self.atlas_ebelge_senaryo == 'IHRACAT':
                    raise UserError(self.env._('"%s" satırı KDV\'siz; vergiye veya mali koşula GİB istisna kodu atayın.', line.name))
                else:
                    # GİB: istisna olmayan %0 KDV'li satış
                    detay.update({'taxExemptionReasonCode': '351', 'taxExemptionReasonName': 'KDV - İstisna Olmayan Diğer'})
            if self.atlas_ebelge_senaryo == 'IHRACAT':
                if not urun.atlas_gtip:
                    raise UserError(self.env._('İhracat faturası için "%s" ürününün GTİP kodu girilmeli.', urun.display_name or line.name))
                detay['gtip'] = urun.atlas_gtip
                detay['shipment'] = {'packageType': self.atlas_kap_cinsi or 'PK', 'packageQty': self.atlas_kap_adedi or 1,
                                     'packageNumber': self.name, 'originCountryCode': 'TR', 'originCountryName': 'Türkiye'}
            satirlar.append(detay)
            brut_toplam += brut
            indirim_toplam += indirim
            kdv_toplam += v['kdv']
            tevkif_toplam += v['tevkif']
            ozet = vergi_ozet.setdefault(v['oran'], [0.0, 0.0])
            ozet[0] += net
            ozet[1] += v['kdv']
        if not satirlar:
            raise UserError(self.env._('Faturada ürün satırı yok.'))
        matrah = tutar(self.amount_untaxed)
        efatura = self.atlas_ebelge_tipi == 'efatura'
        govde = {
            'isCalculateByApi': False,
            'id': 0,
            'eDocumentType': 'EFATURA' if efatura else 'EARSIVFATURA',
            'profile': self.atlas_ebelge_senaryo,
            'invoiceType': self.atlas_fatura_tipi or 'SATIS',
            'ettn': self.atlas_ettn,
            'docDate': fields.Date.to_string(self.invoice_date),
            'docTime': fields.Datetime.context_timestamp(self, self.atlas_mysoft_tarih or fields.Datetime.now()).strftime('%H:%M:%S'),
            'currencyCode': self.currency_id.name,
            'currencyRate': self._atlas_kur(),
            'senderType': company.atlas_mysoft_earsiv_teslim or 'ELEKTRONIK',
            'pkAlias': (self.partner_id.commercial_partner_id.atlas_efatura_etiket or None) if efatura and self.atlas_ebelge_senaryo != 'IHRACAT'
            else ('urn:mail:ihracatpk@gtb.gov.tr' if self.atlas_ebelge_senaryo == 'IHRACAT' else None),
            'gbAlias': company.atlas_mysoft_gb_etiket or None,
            'orderNo': (self.invoice_origin or '')[:50] or None,
            'notes': [{'note': n} for n in filter(None, [html2plaintext(self.narration or '').strip() or None,
                                                         self.ref and self.env._('Referans: %s', self.ref)])] or None,
            'invoiceAccount': self._atlas_hesap_json(),
            'isManuelCalculation': True,
            'invoiceCalculation': {
                'lineExtensionAmount': matrah,
                'taxExclusiveAmount': matrah,
                'taxInclusiveAmount': tutar(matrah + kdv_toplam),
                'allowanceTotalAmount': 0,
                'chargeTotalAmount': 0,
                'payableRoundingAmount': 0,
                'payableAmount': tutar(self.amount_total),
            },
            'tax': [{'taxAmount': tutar(kdv_toplam), 'taxSubTotal': [
                {'taxableAmount': tutar(m), 'taxAmount': tutar(k), 'calculationSequenceNumeric': 0, 'percent': oran,
                 'taxName': 'KDV', 'taxTypeCode': '0015'} for oran, (m, k) in sorted(vergi_ozet.items())]}],
            'invoiceDetail': satirlar,
        }
        if company.atlas_mysoft_numara == 'atlas':
            govde['docNo'] = self.name
        else:
            govde['docNo'] = None
            govde['prefix'] = (company.atlas_mysoft_efatura_onek if efatura else company.atlas_mysoft_earsiv_onek) or None
        if self.atlas_fatura_tipi == 'IADE' and self.reversed_entry_id:
            asil = self.reversed_entry_id
            govde.update({'billingRefInvoiceNo': asil.ref or asil.name, 'billingRefInvoiceDate': fields.Date.to_string(asil.invoice_date)})
        if self.atlas_ebelge_senaryo == 'IHRACAT':
            if not self.invoice_incoterm_id or not self.atlas_tasima_modu:
                raise UserError(self.env._('İhracat faturası için teslim şartı (Incoterm) ve gönderim şekli girilmeli.'))
            govde.update({'deliveryTermCode': self.invoice_incoterm_id.code, 'transportModeCode': int(self.atlas_tasima_modu),
                          'deliveryCountry': self.partner_id.country_id.code or None, 'deliveryCity': self.partner_id.city or None})
        if self.company_id.atlas_mysoft_gonderim == 'taslak':
            govde['isSaveAsDraft'] = True
        return govde

    # -------------------------------------------------------------------------
    # Gönderim ve takip
    # -------------------------------------------------------------------------

    def _atlas_mysoft_kontrol(self):
        self.ensure_one()
        if not self.atlas_mysoft_gosterilsin:
            raise UserError(self.env._('%s bir e-Fatura / e-Arşiv faturası değil veya MySoft entegrasyonu kapalı.', self.name))
        if self.state != 'posted':
            raise UserError(self.env._('Önce faturayı onaylayın.'))
        if self.atlas_mysoft_durum in ('gonderildi', 'basarili', 'kabul', 'iptal', 'taslak'):
            raise UserError(self.env._('%(f)s zaten MySoft\'a iletildi (%(d)s).', f=self.name,
                                       d=dict(MYSOFT_DURUMLARI)[self.atlas_mysoft_durum]))

    def _atlas_mysoft_gonder(self):
        Api = self.env['atlas.mysoft.api']
        for move in self:
            move._atlas_mysoft_kontrol()
            govde = move._atlas_mysoft_json()
            simdi = fields.Datetime.now()
            try:
                yanit = Api._istek(move.company_id, 'POST', '/api/InvoiceOutbox/invoiceOutbox', govde, islem='Fatura gönder', kayit=move)
            except UserError as hata:
                move.write({'atlas_mysoft_durum': 'hata', 'atlas_mysoft_mesaj': str(hata)[:2000], 'atlas_mysoft_tarih': simdi})
                move.message_post(body=self.env._('e-Belge gönderilemedi: %s', hata))
                continue
            ettn = anahtar_bul(yanit, [r'(invoice)?ettn', r'uuid'])
            belge_no = anahtar_bul(yanit, [r'docNo', r'invoiceNo', r'documentNo', r'invoiceNumber'])
            vals = {'atlas_mysoft_durum': 'taslak' if govde.get('isSaveAsDraft') else 'gonderildi', 'atlas_mysoft_tarih': simdi,
                    'atlas_mysoft_mesaj': False, 'atlas_mysoft_belge_no': belge_no or move.name}
            if ettn and str(ettn).upper() != (move.atlas_ettn or '').upper():
                vals['atlas_ettn'] = str(ettn).upper()
            move.write(vals)
            move.message_post(body=self.env._('e-Belge MySoft\'a iletildi. ETTN: %(ettn)s, No: %(no)s',
                                              ettn=move.atlas_ettn, no=move.atlas_mysoft_belge_no))

    def action_atlas_mysoft_gonder(self):
        self._atlas_mysoft_gonder()
        hatali = self.filtered(lambda m: m.atlas_mysoft_durum == 'hata')
        if len(self) == 1 and hatali:
            raise UserError(hatali.atlas_mysoft_mesaj)
        return True

    def action_atlas_mysoft_taslak_gonder(self):
        for move in self.filtered(lambda m: m.atlas_mysoft_durum == 'taslak'):
            self.env['atlas.mysoft.api']._istek(move.company_id, 'POST', '/api/InvoiceOutbox/sendDraftInvoiceToGIB',
                                                [move.atlas_ettn], islem='Taslağı GİB\'e gönder', kayit=move)
            move.write({'atlas_mysoft_durum': 'gonderildi', 'atlas_mysoft_tarih': fields.Datetime.now()})
        return True

    def action_atlas_mysoft_taslak_sil(self):
        for move in self.filtered(lambda m: m.atlas_mysoft_durum == 'taslak'):
            self.env['atlas.mysoft.api']._istek(move.company_id, 'GET', '/api/InvoiceOutbox/deleteDraftInvoiceOutbox',
                                                params={'invoiceETTN': move.atlas_ettn}, islem='Taslak sil', kayit=move)
            move.write({'atlas_mysoft_durum': 'gonderilmedi', 'atlas_mysoft_belge_no': False})
        return True

    def _atlas_durum_uygula(self, ham):
        self.ensure_one()
        metin = anahtar_bul(ham, [r'.*status(Name|Desc|Description|Text)?', r'.*state', r'durum.*']) if not isinstance(ham, str) else ham
        aciklama = anahtar_bul(ham, [r'.*(statusDetail|errorMessage|responseDesc|gibResponse|description|message).*']) \
            if not isinstance(ham, str) else None
        yeni = durum_eslestir(metin)
        vals = {'atlas_mysoft_durum_metin': str(metin)[:200] if metin else False}
        if yeni and yeni != self.atlas_mysoft_durum:
            vals['atlas_mysoft_durum'] = yeni
            if yeni in ('hata', 'red'):
                vals['atlas_mysoft_mesaj'] = str(aciklama or metin)[:2000]
        self.write(vals)
        if vals.get('atlas_mysoft_durum') in ('hata', 'red'):
            sorumlu = self.invoice_user_id or self.create_uid
            self.activity_schedule('mail.mail_activity_data_warning', user_id=sorumlu.id,
                                   summary=self.env._('e-Belge %s', dict(MYSOFT_DURUMLARI)[vals['atlas_mysoft_durum']]),
                                   note=self.atlas_mysoft_mesaj)
        return yeni

    def action_atlas_mysoft_durum(self):
        for move in self.filtered('atlas_ettn'):
            yanit = self.env['atlas.mysoft.api']._istek(move.company_id, 'GET', '/api/InvoiceOutbox/getInvoiceOutboxStatus',
                                                        params={'invoiceETTN': move.atlas_ettn}, islem='Durum sorgula', kayit=move)
            move._atlas_durum_uygula(yanit)
        return True

    def action_atlas_mysoft_pdf(self):
        self.ensure_one()
        if not self.atlas_ettn or self.atlas_mysoft_durum in ('gonderilmedi', 'kuyrukta', 'hata'):
            raise UserError(self.env._('Fatura henüz MySoft\'a iletilmedi.'))
        icerik = self.env['atlas.mysoft.api']._istek(self.company_id, 'GET', '/api/InvoiceOutbox/getInvoiceOutboxPdfAsZip',
                                                     params={'invoiceETTN': self.atlas_ettn}, ikili=True, islem='PDF', kayit=self)
        ad, pdf = zipten_dosya(icerik, ('.pdf',))
        ek = self.env['ir.attachment'].create({'name': f'{self.name or self.atlas_ettn}.pdf'.replace('/', '-'), 'raw': pdf,
                                               'res_model': 'account.move', 'res_id': self.id, 'mimetype': 'application/pdf'})
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{ek.id}?download=true', 'target': 'new'}

    def action_atlas_mysoft_iptal(self):
        """e-Arşiv faturası iptali (e-Fatura iptal edilemez; iade/itiraz süreciyle kapanır)."""
        for move in self:
            if move.atlas_ebelge_tipi != 'earsiv' or move.atlas_mysoft_durum not in ('gonderildi', 'basarili'):
                raise UserError(self.env._('Yalnız gönderilmiş e-Arşiv faturaları iptal edilebilir.'))
            self.env['atlas.mysoft.api']._istek(move.company_id, 'GET', '/api/InvoiceOutbox/cancelEArchiveInvoice', params={
                'invoiceETTN': move.atlas_ettn, 'cancelDate': fields.Date.to_string(fields.Date.context_today(move)),
                'cancelType': 'PORTAL', 'cancelNote': self.env._('%s iptal edildi', move.name)}, islem='e-Arşiv iptal', kayit=move)
            move.atlas_mysoft_durum = 'iptal'
            move.message_post(body=self.env._('e-Arşiv faturası GİB\'de iptal edildi.'))
            move.button_cancel_atlas_mysoft()
        return True

    def button_cancel_atlas_mysoft(self):
        """İptal edilen e-Arşivin muhasebe kaydını ters kayıtla kapatır."""
        for move in self.filtered(lambda m: m.state == 'posted'):
            move._reverse_moves([{'ref': self.env._('e-Arşiv iptali: %s', move.name), 'invoice_date': fields.Date.context_today(move)}],
                                cancel=True)

    def action_atlas_mysoft_eposta(self):
        self.ensure_one()
        self.env['atlas.mysoft.api']._istek(self.company_id, 'GET', '/api/InvoiceOutbox/sendMailForInvoice',
                                            params={'invoiceETTN': self.atlas_ettn}, islem='E-posta gönder', kayit=self)
        return True

    @api.model
    def _cron_atlas_mysoft(self):
        """Kuyruktaki faturaları gönderir ve gönderilenlerin durumunu MySoft'tan günceller."""
        for company in self.env['res.company'].search([('atlas_mysoft_aktif', '=', True)]):
            moves = self.search([('company_id', '=', company.id), ('atlas_mysoft_durum', '=', 'kuyrukta'), ('state', '=', 'posted')],
                                limit=100, order='id')
            for move in moves:
                try:
                    with self.env.cr.savepoint():
                        move._atlas_mysoft_gonder()
                except UserError as hata:
                    move.write({'atlas_mysoft_durum': 'hata', 'atlas_mysoft_mesaj': str(hata)[:2000]})
            try:
                with self.env.cr.savepoint():
                    self._atlas_durum_toplu(company)
            except UserError:
                _logger.warning('MySoft durum güncellemesi başarısız (%s)', company.name)

    @api.model
    def _atlas_durum_toplu(self, company):
        simdi = fields.Datetime.now()
        bas = (company.atlas_mysoft_durum_kontrol or simdi - timedelta(days=2)) - timedelta(minutes=30)
        imlec = 0
        Api = self.env['atlas.mysoft.api']
        for _sayfa in range(20):
            yanit = Api._istek(company, 'POST', '/api/InvoiceOutbox/getInvoiceOutboxStatusChanged', {
                'startDate': fields.Datetime.to_string(bas), 'endDate': fields.Datetime.to_string(simdi),
                'afterValue': imlec, 'limit': 100}, islem='Durum değişiklikleri')
            liste = liste_bul(yanit) or []
            for oge in liste:
                ettn = anahtar_bul(oge, [r'(invoice)?ettn', r'uuid'])
                move = ettn and self.search([('atlas_ettn', '=ilike', str(ettn))], limit=1)
                if move:
                    move._atlas_durum_uygula(oge)
            yeni_imlec = max([int(anahtar_bul(o, [r'id', r'rowId', r'afterValue', r'.*Id']) or 0) for o in liste if isinstance(o, dict)] or [0])
            if len(liste) < 100 or yeni_imlec <= imlec:
                break
            imlec = yeni_imlec
        company.sudo().atlas_mysoft_durum_kontrol = simdi
        # Toplu listede yer almayan, 1 saattir sonuçlanmamış gönderimleri tek tek sorgula
        bekleyen = self.search([('company_id', '=', company.id), ('atlas_mysoft_durum', '=', 'gonderildi'),
                                ('atlas_mysoft_tarih', '<', simdi - timedelta(hours=1))], limit=30)
        for move in bekleyen:
            try:
                with self.env.cr.savepoint():
                    move.action_atlas_mysoft_durum()
            except UserError:
                continue
