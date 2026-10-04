import base64
import calendar
import io
from collections import defaultdict
from datetime import date, timedelta

import xlsxwriter
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError

TIPLER = [('kdv1', 'KDV1 Beyannamesi'), ('kdv2', 'KDV2 Beyannamesi (Sorumlu Sıfatıyla)'),
          ('ba', 'Form Ba (Alışlar)'), ('bs', 'Form Bs (Satışlar)')]
BOLUMLER = [
    ('matrah', 'Teslim ve Hizmetler'),
    ('tevkifat', 'Kısmi Tevkifat Uygulanan İşlemler'),
    ('istisna', 'İstisnalar'),
    ('ihrac_kayitli', 'İhraç Kaydıyla Teslimler'),
    ('indirim', 'İndirilecek KDV'),
    ('kdv2', 'Sorumlu Sıfatıyla Beyan Edilen KDV'),
    ('babs', 'Bildirim'),
    ('kontrol', 'Hesap Kontrolü'),
]
def _onceki_ay(env_self):
    """Beyanname varsayılanı: bir önceki ay."""
    return fields.Date.context_today(env_self).replace(day=1) - timedelta(days=1)


AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def _tax_account_code(tax):
    """Verginin fatura dağılımındaki vergi hesabının kodu (391 hesaplanan, 191 indirilecek, 360 tevkifat)."""
    lines = tax.invoice_repartition_line_ids.filtered(lambda r: r.repartition_type == 'tax' and r.account_id)
    return lines[:1].account_id.code or ''


def _pay(oran_pozitif, oran_negatif):
    """%20 içinden %14 tevkif → 7/10"""
    if not oran_pozitif:
        return ''
    onda = round(abs(oran_negatif) / oran_pozitif * 10)
    return f'{onda}/10'


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_babs_sinir = fields.Monetary(string='Ba-Bs Bildirim Sınırı', default=5000.0,
                                       help='Bir cariyle dönem içindeki KDV hariç toplam bu tutara ulaşırsa bildirilir.')
    atlas_beyan_eposta = fields.Char(string='Beyanname e-Posta')
    atlas_beyan_telefon = fields.Char(string='Beyanname Telefon')
    atlas_duzenleyen_tip = fields.Selection([('mukellef', 'Mükellefin kendisi'), ('smmm', 'SM / SMMM')], string='Beyannameyi Düzenleyen',
                                            default='smmm')
    atlas_smmm_vkn = fields.Char(string='SMMM VKN/TCKN')
    atlas_smmm_ad = fields.Char(string='SMMM Adı')
    atlas_smmm_soyad = fields.Char(string='SMMM Soyadı / Unvanı')
    atlas_smmm_telefon = fields.Char(string='SMMM Telefon')
    atlas_smmm_eposta = fields.Char(string='SMMM e-Posta')
    atlas_kdv1_kodver = fields.Char(string='KDV1 Şema Sürümü', default='KDV1_44')
    atlas_kdv2_kodver = fields.Char(string='KDV2 Şema Sürümü', default='KDV2_24')
    atlas_ba_kodver = fields.Char(string='Form Ba Şema Sürümü', default='BA_7')
    atlas_bs_kodver = fields.Char(string='Form Bs Şema Sürümü', default='BS_7')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_babs_sinir = fields.Monetary(related='company_id.atlas_babs_sinir', readonly=False)
    atlas_beyan_eposta = fields.Char(related='company_id.atlas_beyan_eposta', readonly=False)
    atlas_beyan_telefon = fields.Char(related='company_id.atlas_beyan_telefon', readonly=False)
    atlas_duzenleyen_tip = fields.Selection(related='company_id.atlas_duzenleyen_tip', readonly=False)
    atlas_smmm_vkn = fields.Char(related='company_id.atlas_smmm_vkn', readonly=False)
    atlas_smmm_ad = fields.Char(related='company_id.atlas_smmm_ad', readonly=False)
    atlas_smmm_soyad = fields.Char(related='company_id.atlas_smmm_soyad', readonly=False)
    atlas_smmm_telefon = fields.Char(related='company_id.atlas_smmm_telefon', readonly=False)
    atlas_smmm_eposta = fields.Char(related='company_id.atlas_smmm_eposta', readonly=False)
    atlas_kdv1_kodver = fields.Char(related='company_id.atlas_kdv1_kodver', readonly=False)
    atlas_kdv2_kodver = fields.Char(related='company_id.atlas_kdv2_kodver', readonly=False)
    atlas_ba_kodver = fields.Char(related='company_id.atlas_ba_kodver', readonly=False)
    atlas_bs_kodver = fields.Char(related='company_id.atlas_bs_kodver', readonly=False)


class AtlasBeyanname(models.Model):
    _name = 'atlas.beyanname'
    _description = 'Beyanname'
    _inherit = ['mail.thread']
    _order = 'yil desc, ay desc, tip'

    name = fields.Char(string='No', required=True, copy=False, readonly=True, default='/')
    tip = fields.Selection(TIPLER, string='Beyanname', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    yil = fields.Integer(string='Yıl', required=True, default=lambda self: _onceki_ay(self).year)
    ay = fields.Selection([(str(i), AYLAR[i - 1]) for i in range(1, 13)], string='Ay', required=True,
                          default=lambda self: str(_onceki_ay(self).month))
    durum = fields.Selection([('taslak', 'Taslak'), ('onaylandi', 'Onaylandı (verildi)')], string='Durum', default='taslak',
                             required=True, tracking=True)
    satir_ids = fields.One2many('atlas.beyanname.satir', 'beyanname_id', string='Satırlar', copy=False)
    # KDV1 özet
    matrah_toplam = fields.Monetary(string='Matrah Toplamı', readonly=True)
    hesaplanan_kdv = fields.Monetary(string='Hesaplanan KDV', readonly=True)
    tevkif_edilen = fields.Monetary(string='Alıcılarca Tevkif Edilen', readonly=True)
    beyan_edilen_kdv = fields.Monetary(string='Beyan Edilen KDV', readonly=True,
                                       help='Hesaplanan KDV − alıcılarca tevkif edilen KDV.')
    indirilecek_kdv = fields.Monetary(string='Bu Dönem İndirilecek KDV', readonly=True)
    devreden_kdv = fields.Monetary(string='Önceki Dönemden Devreden KDV', tracking=True,
                                   help='Önceki dönem beyannamesi onaylıysa otomatik gelir; ilk dönemde elle girin.')
    odenecek_kdv = fields.Monetary(string='Ödenmesi Gereken KDV', readonly=True)
    sonraki_devreden = fields.Monetary(string='Sonraki Döneme Devreden KDV', readonly=True)
    # KDV2 / Ba-Bs
    kdv2_toplam = fields.Monetary(string='Sorumlu Sıfatıyla Ödenecek KDV', readonly=True)
    babs_sinir = fields.Monetary(string='Bildirim Sınırı', readonly=True)
    bildirim_sayisi = fields.Integer(string='Bildirilen Cari', readonly=True)
    uyari = fields.Text(string='Uyarılar', readonly=True)
    xml_dosya = fields.Binary(string='XML', readonly=True, attachment=True)
    xml_adi = fields.Char(readonly=True)

    _donem_uniq = models.UniqueIndex('(company_id, tip, yil, ay)', 'Bu dönem için bu beyanname zaten var.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.beyanname') or '/'
        return super().create(vals_list)

    @api.depends('tip', 'yil', 'ay')
    def _compute_display_name(self):
        for b in self:
            b.display_name = f'{dict(TIPLER).get(b.tip, "")} {AYLAR[int(b.ay) - 1] if b.ay else ""} {b.yil or ""}'.strip()

    def _donem(self):
        self.ensure_one()
        ay = int(self.ay)
        return date(self.yil, ay, 1), date(self.yil, ay, calendar.monthrange(self.yil, ay)[1])

    def _onceki(self):
        self.ensure_one()
        ay, yil = (int(self.ay) - 1, self.yil) if self.ay != '1' else (12, self.yil - 1)
        return self.search([('company_id', '=', self.company_id.id), ('tip', '=', self.tip), ('yil', '=', yil),
                            ('ay', '=', str(ay))], limit=1)

    def _aml(self, extra):
        bas, bit = self._donem()
        return self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('date', '>=', bas), ('date', '<=', bit)] + extra)

    # -------------------------------------------------------------------------
    # Hesaplama
    # -------------------------------------------------------------------------

    def action_hesapla(self):
        for b in self:
            if b.durum != 'taslak':
                raise UserError(self.env._('Onaylanmış beyanname yeniden hesaplanamaz; önce taslağa alın.'))
            b.satir_ids.unlink()
            getattr(b, f'_hesapla_{"babs" if b.tip in ("ba", "bs") else b.tip}')()
            b.xml_dosya = False
        return True

    def _satir(self, bolum, **vals):
        return {'beyanname_id': self.id, 'bolum': bolum, **vals}

    def _hesapla_kdv1(self):
        cur = self.currency_id
        uyarilar = []
        # Matrah satırları (fatura kalemleri) — satış vergileri
        taban = defaultdict(float)  # anahtar → matrah
        for line in self._aml([('tax_ids', '!=', False), ('tax_line_id', '=', False)]):
            for tax in line.tax_ids.filtered(lambda t: t.type_tax_use == 'sale'):
                taban[tax] += -line.balance
        # Vergi satırları
        vergi = defaultdict(float)  # (grup vergisi, vergi) → tutar (alacak pozitif)
        for line in self._aml([('tax_line_id', '!=', False)]):
            vergi[(line.group_tax_id, line.tax_line_id)] += -line.balance

        satirlar = []
        matrah_by_oran, vergi_by_oran = defaultdict(float), defaultdict(float)
        hesaplanan = tevkif_toplam = 0.0
        for tax, matrah in taban.items():
            if cur.is_zero(matrah):
                continue
            if tax.amount_type == 'group':
                pos = tax.children_tax_ids.filtered(lambda c: c.amount > 0)[:1]
                neg = tax.children_tax_ids.filtered(lambda c: c.amount < 0)[:1]
                v_pos = vergi.get((tax, pos), 0.0)
                v_neg = -vergi.get((tax, neg), 0.0)  # tevkif edilen (pozitif)
                kod = tax.atlas_gib_kod_id
                ihrac_kayitli = kod.tip == 'ihrac_kayitli' or '701' in (tax.name or '')
                bolum = 'ihrac_kayitli' if ihrac_kayitli else 'tevkifat'
                if not ihrac_kayitli and not kod:
                    uyarilar.append(self.env._('"%s" vergisine GİB tevkifat kodu atanmamış.', tax.name))
                satirlar.append(self._satir(bolum, kod=kod.kod or '', aciklama=tax.name, oran=pos.amount,
                                            tevkifat_orani=_pay(pos.amount, neg.amount), matrah=matrah, vergi=v_pos, tevkifat=v_neg))
                matrah_by_oran[pos.amount] += matrah
                hesaplanan += v_pos
                tevkif_toplam += v_neg
            elif tax.amount == 0:
                kod = tax.atlas_gib_kod_id
                if not kod:
                    uyarilar.append(self.env._('"%s" (KDV %%0) vergisine GİB istisna kodu atanmamış.', tax.name))
                satirlar.append(self._satir('istisna', kod=kod.kod or '', aciklama=kod.name or tax.name, matrah=matrah))
            elif tax.amount > 0 and _tax_account_code(tax).startswith('391'):
                matrah_by_oran[tax.amount] += matrah
                v = vergi.get((self.env['account.tax'], tax), 0.0)
                vergi_by_oran[tax.amount] += v
                hesaplanan += v
        for oran in sorted(matrah_by_oran):
            # Tevkifatlı işlemler de oran bazında matraha dahildir (vergisi kendi bölümünde)
            v = vergi_by_oran.get(oran, 0.0) + sum(s['vergi'] for s in satirlar
                                                   if s['bolum'] in ('tevkifat', 'ihrac_kayitli') and s['oran'] == oran)
            satirlar.insert(0, self._satir('matrah', aciklama=self.env._('KDV %%%s', f'{oran:g}'), oran=oran,
                                           matrah=matrah_by_oran[oran], vergi=v))
        # İndirilecek KDV (191)
        indirim_by_oran = defaultdict(float)
        for (grup, tax), tutar in vergi.items():
            if _tax_account_code(tax).startswith('191'):
                indirim_by_oran[tax.amount] += -tutar
        for oran, tutar in sorted(indirim_by_oran.items()):
            satirlar.append(self._satir('indirim', aciklama=self.env._('İndirilecek KDV %%%s', f'{oran:g}'), oran=oran, vergi=tutar))
        indirilecek = sum(indirim_by_oran.values())

        onceki = self._onceki()
        if onceki and onceki.durum == 'onaylandi':
            self.devreden_kdv = onceki.sonraki_devreden
        beyan = hesaplanan - tevkif_toplam
        fark = beyan - indirilecek - self.devreden_kdv
        istisna_matrah = sum(s['matrah'] for s in satirlar if s['bolum'] == 'istisna')
        self.write({
            'matrah_toplam': cur.round(sum(matrah_by_oran.values()) + istisna_matrah),
            'hesaplanan_kdv': cur.round(hesaplanan), 'tevkif_edilen': cur.round(tevkif_toplam),
            'beyan_edilen_kdv': cur.round(beyan), 'indirilecek_kdv': cur.round(indirilecek),
            'odenecek_kdv': cur.round(max(fark, 0.0)), 'sonraki_devreden': cur.round(max(-fark, 0.0)),
        })
        # Hesap kontrolü
        h391 = -sum(self._aml([('account_id.code', '=like', '391%')]).mapped('balance'))
        h191 = sum(self._aml([('account_id.code', '=like', '191%')]).mapped('balance'))
        satirlar.append(self._satir('kontrol', kod='391', aciklama=self.env._('391 hesap hareketi (net alacak)'), vergi=h391,
                                    tevkifat=beyan - h391))
        satirlar.append(self._satir('kontrol', kod='191', aciklama=self.env._('191 hesap hareketi (net borç)'), vergi=h191,
                                    tevkifat=indirilecek - h191))
        if not cur.is_zero(beyan - h391):
            uyarilar.append(self.env._('Beyan edilen KDV 391 hesabıyla %s fark veriyor (elle fiş/aktarım olabilir).', f'{beyan - h391:,.2f}'))
        if not cur.is_zero(indirilecek - h191):
            uyarilar.append(self.env._('İndirilecek KDV 191 hesabıyla %s fark veriyor.', f'{indirilecek - h191:,.2f}'))
        self.env['atlas.beyanname.satir'].create(satirlar)
        self.uyari = '\n'.join(dict.fromkeys(uyarilar)) or False

    def _hesapla_kdv2(self):
        taban = defaultdict(float)
        for line in self._aml([('tax_ids', '!=', False), ('tax_line_id', '=', False)]):
            for tax in line.tax_ids.filtered(lambda t: t.type_tax_use == 'purchase' and t.amount_type == 'group'):
                if tax.children_tax_ids.filtered(lambda c: c.amount < 0):
                    taban[tax] += line.balance
        vergi = defaultdict(float)
        for line in self._aml([('tax_line_id', '!=', False), ('group_tax_id', '!=', False)]):
            vergi[(line.group_tax_id, line.tax_line_id)] += -line.balance
        satirlar, toplam, uyarilar = [], 0.0, []
        for tax, matrah in taban.items():
            pos = tax.children_tax_ids.filtered(lambda c: c.amount > 0)[:1]
            neg = tax.children_tax_ids.filtered(lambda c: c.amount < 0)[:1]
            if not _tax_account_code(neg).startswith('360'):
                continue  # kira stopajı vb. KDV dışı
            tevkif = vergi.get((tax, neg), 0.0)
            kdv = matrah * pos.amount / 100.0
            if not tax.atlas_gib_kod_id:
                uyarilar.append(self.env._('"%s" vergisine GİB tevkifat kodu atanmamış.', tax.name))
            satirlar.append(self._satir('kdv2', kod=tax.atlas_gib_kod_id.kod or '', aciklama=tax.name, oran=pos.amount,
                                        tevkifat_orani=_pay(pos.amount, neg.amount), matrah=matrah, vergi=kdv, tevkifat=tevkif))
            toplam += tevkif
        h360 = -sum(self._aml([('account_id.code', '=like', '360001%')]).mapped('balance'))
        satirlar.append(self._satir('kontrol', kod='360001', aciklama=self.env._('360001 hesap hareketi (net alacak)'),
                                    vergi=h360, tevkifat=toplam - h360))
        self.env['atlas.beyanname.satir'].create(satirlar)
        self.write({'kdv2_toplam': self.currency_id.round(toplam), 'uyari': '\n'.join(dict.fromkeys(uyarilar)) or False})

    def _hesapla_babs(self):
        bas, bit = self._donem()
        tipler = ('in_invoice', 'out_refund') if self.tip == 'ba' else ('out_invoice', 'in_refund')
        moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'), ('move_type', 'in', tipler),
            ('invoice_date', '>=', bas), ('invoice_date', '<=', bit)])
        gruplu = defaultdict(lambda: [0, 0.0])
        for move in moves:
            g = gruplu[move.commercial_partner_id]
            g[0] += 1
            g[1] += abs(move.amount_untaxed_signed)
        sinir = self.company_id.atlas_babs_sinir
        satirlar, uyarilar = [], []
        for partner, (adet, tutar) in sorted(gruplu.items(), key=lambda kv: -kv[1][1]):
            if tutar < sinir:
                continue
            vkn = (partner.vat or '').upper().removeprefix('TR').strip()
            if not vkn:
                uyarilar.append(self.env._('%s carisinin VKN/TCKN bilgisi yok.', partner.name))
            satirlar.append(self._satir('babs', partner_id=partner.id, aciklama=partner.name, kod=vkn,
                                        ulke=partner.country_id.code or 'TR', belge_sayisi=adet, matrah=round(tutar)))
        self.env['atlas.beyanname.satir'].create(satirlar)
        self.write({'babs_sinir': sinir, 'bildirim_sayisi': len(satirlar), 'uyari': '\n'.join(uyarilar) or False})

    # -------------------------------------------------------------------------
    # Durum
    # -------------------------------------------------------------------------

    def action_onayla(self):
        for b in self:
            if not b.satir_ids:
                raise UserError(self.env._('Önce beyannameyi hesaplayın.'))
        self.write({'durum': 'onaylandi'})
        return True

    def action_taslak(self):
        self.write({'durum': 'taslak'})
        return True

    # -------------------------------------------------------------------------
    # Çıktılar
    # -------------------------------------------------------------------------

    def _bolum(self, bolum):
        return self.satir_ids.filtered(lambda s: s.bolum == bolum)

    @staticmethod
    def _tutar(v):
        return f'{v:.2f}'

    def _xml_genel(self, kok, kodver):
        company = self.company_id
        vkn = (company.vat or '').upper().removeprefix('TR').strip()
        if not vkn:
            raise UserError(self.env._('Şirket VKN/TCKN bilgisi eksik.'))
        if not company.l10n_tr_tax_office_id:
            raise UserError(self.env._('Şirketin vergi dairesi seçilmemiş (şirket kartı).'))
        genel = etree.SubElement(kok, 'genel')
        idari = etree.SubElement(genel, 'idari')
        etree.SubElement(idari, 'vdKodu').text = str(company.l10n_tr_tax_office_id.code)
        donem = etree.SubElement(idari, 'donem')
        etree.SubElement(donem, 'tip').text = 'aylik'
        etree.SubElement(donem, 'yil').text = str(self.yil)
        etree.SubElement(donem, 'ay').text = f'{int(self.ay):02d}'
        mukellef = etree.SubElement(genel, 'mukellef')
        etree.SubElement(mukellef, 'vergiNo' if len(vkn) == 10 else 'tcKimlikNo').text = vkn
        etree.SubElement(mukellef, 'soyadi').text = company.name
        etree.SubElement(mukellef, 'eposta').text = company.atlas_beyan_eposta or company.email or ''
        etree.SubElement(mukellef, 'telefonNumarasi').text = company.atlas_beyan_telefon or company.phone or ''
        duzenleyen = etree.SubElement(genel, 'duzenleyen')
        if company.atlas_duzenleyen_tip == 'smmm' and company.atlas_smmm_vkn:
            smmm = company.atlas_smmm_vkn.strip()
            etree.SubElement(duzenleyen, 'vergiNo' if len(smmm) == 10 else 'tcKimlikNo').text = smmm
            etree.SubElement(duzenleyen, 'soyadi').text = company.atlas_smmm_soyad or ''
            etree.SubElement(duzenleyen, 'adi').text = company.atlas_smmm_ad or ''
            etree.SubElement(duzenleyen, 'eposta').text = company.atlas_smmm_eposta or ''
            etree.SubElement(duzenleyen, 'telefonNumarasi').text = company.atlas_smmm_telefon or ''
        else:
            etree.SubElement(duzenleyen, 'vergiNo' if len(vkn) == 10 else 'tcKimlikNo').text = vkn
            etree.SubElement(duzenleyen, 'soyadi').text = company.name
        return etree.SubElement(kok, 'ozel')

    def _xml_kdv1(self, ozel):
        matrah = etree.SubElement(ozel, 'matrah')
        teslimler = etree.SubElement(matrah, 'teslimVeHizmetler')
        for s in self._bolum('matrah'):
            t = etree.SubElement(teslimler, 'teslimHizmet')
            etree.SubElement(t, 'kdvOrani').text = f'{s.oran:g}'
            etree.SubElement(t, 'matrah').text = self._tutar(s.matrah)
            etree.SubElement(t, 'vergi').text = self._tutar(s.vergi)
        if self._bolum('tevkifat'):
            kismi = etree.SubElement(matrah, 'kismiTevkifatUygulananIslemler')
            for s in self._bolum('tevkifat'):
                t = etree.SubElement(kismi, 'kismiTevkifat')
                etree.SubElement(t, 'islemTuru').text = s.kod or ''
                etree.SubElement(t, 'matrah').text = self._tutar(s.matrah)
                etree.SubElement(t, 'kdvOrani').text = f'{s.oran:g}'
                etree.SubElement(t, 'tevkifatOrani').text = s.tevkifat_orani or ''
                etree.SubElement(t, 'vergi').text = self._tutar(s.vergi - s.tevkifat)
        etree.SubElement(matrah, 'matrahToplami').text = self._tutar(self.matrah_toplam)
        etree.SubElement(matrah, 'hesaplananKDV').text = self._tutar(self.hesaplanan_kdv)
        etree.SubElement(matrah, 'toplamKDV').text = self._tutar(self.beyan_edilen_kdv)
        indirim = etree.SubElement(ozel, 'indirimler')
        etree.SubElement(indirim, 'oncekiDonemdenDevredenIndirilecekKDV').text = self._tutar(self.devreden_kdv)
        etree.SubElement(indirim, 'buDonemeAitIndirilecekKDV').text = self._tutar(self.indirilecek_kdv)
        etree.SubElement(indirim, 'indirimlerToplami').text = self._tutar(self.devreden_kdv + self.indirilecek_kdv)
        if self._bolum('istisna') or self._bolum('ihrac_kayitli'):
            istisnalar = etree.SubElement(ozel, 'istisnalar')
            for s in self._bolum('istisna'):
                t = etree.SubElement(istisnalar, 'istisna')
                etree.SubElement(t, 'islemTuru').text = s.kod or ''
                etree.SubElement(t, 'teslimVeHizmetTutari').text = self._tutar(s.matrah)
            for s in self._bolum('ihrac_kayitli'):
                t = etree.SubElement(istisnalar, 'ihracKayitliTeslim')
                etree.SubElement(t, 'islemTuru').text = s.kod or '701'
                etree.SubElement(t, 'teslimBedeli').text = self._tutar(s.matrah)
                etree.SubElement(t, 'teminataTabiKDV').text = self._tutar(s.tevkifat)
        sonuc = etree.SubElement(ozel, 'sonucHesaplari')
        etree.SubElement(sonuc, 'odenmesiGerekenKDV').text = self._tutar(self.odenecek_kdv)
        etree.SubElement(sonuc, 'sonrakiDonemeDevredenKDV').text = self._tutar(self.sonraki_devreden)

    def _xml_kdv2(self, ozel):
        bolum = etree.SubElement(ozel, 'kismiTevkifatUygulananIslemler')
        for s in self._bolum('kdv2'):
            t = etree.SubElement(bolum, 'kismiTevkifat')
            etree.SubElement(t, 'islemTuru').text = s.kod or ''
            etree.SubElement(t, 'matrah').text = self._tutar(s.matrah)
            etree.SubElement(t, 'kdvOrani').text = f'{s.oran:g}'
            etree.SubElement(t, 'tevkifatOrani').text = s.tevkifat_orani or ''
            etree.SubElement(t, 'vergi').text = self._tutar(s.tevkifat)
        etree.SubElement(ozel, 'odenecekKDV').text = self._tutar(self.kdv2_toplam)

    def _xml_babs(self, ozel):
        bildirimler = etree.SubElement(ozel, 'bildirimler')
        for i, s in enumerate(self._bolum('babs'), start=1):
            b = etree.SubElement(bildirimler, 'bildirim')
            etree.SubElement(b, 'siraNo').text = str(i)
            etree.SubElement(b, 'soyadiUnvani').text = (s.aciklama or '')[:100]
            etree.SubElement(b, 'ulke').text = s.ulke or 'TR'
            etree.SubElement(b, 'vergiNo' if len(s.kod or '') != 11 else 'tcKimlikNo').text = s.kod or ''
            etree.SubElement(b, 'belgeSayisi').text = str(s.belge_sayisi)
            etree.SubElement(b, 'malVeHizmetToplamBedeli').text = str(int(round(s.matrah)))

    def action_xml(self):
        self.ensure_one()
        if not self.satir_ids:
            raise UserError(self.env._('Önce beyannameyi hesaplayın.'))
        company = self.company_id
        kodver = {'kdv1': company.atlas_kdv1_kodver, 'kdv2': company.atlas_kdv2_kodver,
                  'ba': company.atlas_ba_kodver, 'bs': company.atlas_bs_kodver}[self.tip]
        kok = etree.Element('beyanname', kodVer=kodver or '', verDonemTip='aylik', verDonemYil=str(self.yil),
                            verDonemAy=f'{int(self.ay):02d}')
        ozel = self._xml_genel(kok, kodver)
        {'kdv1': self._xml_kdv1, 'kdv2': self._xml_kdv2, 'ba': self._xml_babs, 'bs': self._xml_babs}[self.tip](ozel)
        icerik = etree.tostring(kok, xml_declaration=True, encoding='ISO-8859-9', pretty_print=True)
        ad = f'{self.tip.upper()}_{self.yil}{int(self.ay):02d}.xml'
        self.write({'xml_dosya': base64.b64encode(icerik).decode(), 'xml_adi': ad})
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': f'/web/content/atlas.beyanname/{self.id}/xml_dosya/{ad}?download=true'}

    def _xlsx(self):
        self.ensure_one()
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet(self.tip.upper())
        kalin = wb.add_format({'bold': True})
        para = wb.add_format({'num_format': '#,##0.00'})
        ws.write(0, 0, self.display_name, kalin)
        ws.write(1, 0, self.company_id.name)
        basliklar = ['Bölüm', 'Kod / VKN', 'Açıklama', 'Ülke', 'Oran', 'Tevkifat', 'Belge Sayısı', 'Matrah / Tutar', 'Vergi', 'Tevkif / Fark']
        for c, b in enumerate(basliklar):
            ws.write(3, c, b, kalin)
        for r, s in enumerate(self.satir_ids, start=4):
            ws.write(r, 0, dict(BOLUMLER)[s.bolum])
            ws.write(r, 1, s.kod or '')
            ws.write(r, 2, s.aciklama or '')
            ws.write(r, 3, s.ulke or '')
            ws.write(r, 4, s.oran or '')
            ws.write(r, 5, s.tevkifat_orani or '')
            ws.write(r, 6, s.belge_sayisi or '')
            ws.write(r, 7, s.matrah, para)
            ws.write(r, 8, s.vergi, para)
            ws.write(r, 9, s.tevkifat, para)
        ws.set_column(0, 0, 30)
        ws.set_column(2, 2, 45)
        ws.set_column(7, 9, 16)
        wb.close()
        return buf.getvalue()

    def action_xlsx(self):
        self.ensure_one()
        ad = f'{self.tip.upper()}_{self.yil}{int(self.ay):02d}.xlsx'
        ek = self.env['ir.attachment'].create({'name': ad, 'raw': self._xlsx(), 'res_model': self._name, 'res_id': self.id})
        return {'type': 'ir.actions.act_url', 'target': 'self', 'url': f'/web/content/{ek.id}?download=true'}

    def action_pdf(self):
        return self.env.ref('atlas_beyanname.action_report_beyanname').report_action(self)


class AtlasBeyannameSatir(models.Model):
    _name = 'atlas.beyanname.satir'
    _description = 'Beyanname Satırı'
    _order = 'beyanname_id, id'

    beyanname_id = fields.Many2one('atlas.beyanname', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='beyanname_id.currency_id')
    bolum = fields.Selection(BOLUMLER, string='Bölüm', required=True)
    kod = fields.Char(string='Kod / VKN')
    aciklama = fields.Char(string='Açıklama')
    partner_id = fields.Many2one('res.partner', string='Cari')
    ulke = fields.Char(string='Ülke')
    oran = fields.Float(string='KDV Oranı')
    tevkifat_orani = fields.Char(string='Tevkifat Oranı')
    belge_sayisi = fields.Integer(string='Belge Sayısı')
    matrah = fields.Monetary(string='Matrah / Tutar')
    vergi = fields.Monetary(string='Vergi')
    tevkifat = fields.Monetary(string='Tevkif / Fark')
