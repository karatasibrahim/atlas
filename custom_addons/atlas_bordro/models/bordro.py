import base64
import calendar
import io
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_round

from .calisan import EKSIK_GUN_NEDENLERI

AYLAR = [(str(i), ad) for i, ad in enumerate(['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül',
                                                  'Ekim', 'Kasım', 'Aralık'], start=1)]
DONEM_DURUMLARI = [('taslak', 'Taslak'), ('hesaplandi', 'Hesaplandı'), ('onaylandi', 'Onaylandı (Muhasebeleşti)'), ('iptal', 'İptal')]
AYLIK_SAAT = 225.0  # 4857 SK: haftalık 45 saat → aylık 225 saat


def yuvarla(x):
    return float_round(x or 0.0, precision_digits=2)


class AtlasBordroKalemTuru(models.Model):
    _name = 'atlas.bordro.kalem.turu'
    _description = 'Bordro Ek Ödeme / Kesinti Türü'
    _order = 'yon, sequence, id'

    name = fields.Char(string='Kalem', required=True)
    kod = fields.Char(string='Kod')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    yon = fields.Selection([('ek', 'Ek Ödeme'), ('kesinti', 'Kesinti')], string='Tür', required=True, default='ek')
    sgk_tabi = fields.Boolean(string='SGK\'ya Tabi', default=True)
    gv_tabi = fields.Boolean(string='Gelir Vergisine Tabi', default=True)
    dv_tabi = fields.Boolean(string='Damga Vergisine Tabi', default=True)
    saatlik = fields.Boolean(string='Saat Üzerinden', help='Fazla mesai gibi: tutar = saat × saatlik ücret × oran.')
    oran = fields.Float(string='Saat Ücreti Çarpanı', default=1.5)
    yemek_istisnasi = fields.Boolean(string='Yemek İstisnası Uygulanır',
                                     help='Nakit yemek yardımında günlük istisna tutarı kadarı vergiden düşülür.')
    hesap_id = fields.Many2one('account.account', string='Muhasebe Hesabı',
                               help='Kesintilerde alacaklı hesap (ör. 196 avans, 335 icra); boşsa personele borçlar.')


class AtlasBordroDonem(models.Model):
    _name = 'atlas.bordro.donem'
    _description = 'Bordro Dönemi'
    _inherit = ['mail.thread']
    _order = 'yil desc, ay desc, id desc'

    name = fields.Char(string='Dönem', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    yil = fields.Integer(string='Yıl', required=True, default=lambda self: fields.Date.context_today(self).year)
    ay = fields.Selection(AYLAR, string='Ay', required=True, default=lambda self: str(fields.Date.context_today(self).month))
    tarih_bas = fields.Date(string='Başlangıç', compute='_compute_tarihler', store=True)
    tarih_bit = fields.Date(string='Bitiş', compute='_compute_tarihler', store=True)
    durum = fields.Selection(DONEM_DURUMLARI, string='Durum', default='taslak', required=True, tracking=True, copy=False)
    parametre_id = fields.Many2one('atlas.bordro.parametre', string='Parametreler', readonly=True, copy=False)
    bordro_ids = fields.One2many('atlas.bordro', 'donem_id', string='Bordrolar')
    move_id = fields.Many2one('account.move', string='Muhasebe Fişi', readonly=True, copy=False)
    odeme_tarihi = fields.Date(string='Ödeme Tarihi')
    calisan_sayisi = fields.Integer(compute='_compute_toplamlar', string='Çalışan')
    toplam_brut = fields.Monetary(compute='_compute_toplamlar', string='Brüt Toplam', currency_field='currency_id')
    toplam_net = fields.Monetary(compute='_compute_toplamlar', string='Net Ödenecek', currency_field='currency_id')
    toplam_gv = fields.Monetary(compute='_compute_toplamlar', string='Gelir Vergisi', currency_field='currency_id')
    toplam_dv = fields.Monetary(compute='_compute_toplamlar', string='Damga Vergisi', currency_field='currency_id')
    toplam_sgk = fields.Monetary(compute='_compute_toplamlar', string='SGK + İşsizlik (Toplam)', currency_field='currency_id')
    toplam_maliyet = fields.Monetary(compute='_compute_toplamlar', string='İşveren Maliyeti', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')

    _donem_uniq = models.Constraint('UNIQUE(company_id, yil, ay)', 'Bu ay için bordro dönemi zaten var.')

    @api.depends('yil', 'ay')
    def _compute_name(self):
        for d in self:
            d.name = f"{dict(AYLAR).get(d.ay, '')} {d.yil}"

    @api.depends('yil', 'ay')
    def _compute_tarihler(self):
        for d in self:
            if d.yil and d.ay:
                ay = int(d.ay)
                d.tarih_bas = date(d.yil, ay, 1)
                d.tarih_bit = date(d.yil, ay, calendar.monthrange(d.yil, ay)[1])
            else:
                d.tarih_bas = d.tarih_bit = False

    @api.depends('bordro_ids.brut_toplam', 'bordro_ids.net', 'bordro_ids.maliyet')
    def _compute_toplamlar(self):
        for d in self:
            b = d.bordro_ids
            d.calisan_sayisi = len(b)
            d.toplam_brut = sum(b.mapped('brut_toplam'))
            d.toplam_net = sum(b.mapped('net'))
            d.toplam_gv = sum(b.mapped('gv'))
            d.toplam_dv = sum(b.mapped('dv'))
            d.toplam_sgk = sum(b.mapped('sgk_isci')) + sum(b.mapped('issizlik_isci')) + sum(b.mapped('sgk_isveren')) + sum(b.mapped('issizlik_isveren'))
            d.toplam_maliyet = sum(b.mapped('maliyet'))

    def unlink(self):
        if any(d.durum == 'onaylandi' for d in self):
            raise UserError(self.env._('Onaylanmış bordro dönemi silinemez; önce taslağa alın.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # İş akışı
    # -------------------------------------------------------------------------

    def _kilit_kontrol(self):
        for d in self:
            if d.durum == 'onaylandi':
                raise UserError(self.env._('%s onaylanmış; değişiklik için önce taslağa alın.', d.name))

    def action_calisanlari_getir(self):
        """Dönemde sözleşmesi geçerli çalışanlar için bordro satırı açar."""
        self._kilit_kontrol()
        for d in self:
            mevcut = d.bordro_ids.employee_id
            calisanlar = self.env['hr.employee'].search([('company_id', '=', d.company_id.id)])
            for emp in calisanlar - mevcut:
                v = emp._get_versions_with_contract_overlap_with_period(d.tarih_bas, d.tarih_bit) \
                    if hasattr(emp, '_get_versions_with_contract_overlap_with_period') else emp.version_id
                v = v.filtered(lambda x: x.contract_date_start and x.contract_date_start <= d.tarih_bit
                               and (not x.contract_date_end or x.contract_date_end >= d.tarih_bas))
                if v and (v[:1].wage or emp.sudo().atlas_ucret_tipi == 'net'):
                    self.env['atlas.bordro'].create({'donem_id': d.id, 'employee_id': emp.id, 'version_id': v[:1].id})
        return True

    def action_hesapla(self):
        self._kilit_kontrol()
        for d in self:
            if not d.bordro_ids:
                d.action_calisanlari_getir()
            d.parametre_id = self.env['atlas.bordro.parametre']._bul(d.yil, int(d.ay))
            for b in d.bordro_ids.sorted(lambda x: x.employee_id.name):
                b._hesapla()
            d.durum = 'hesaplandi'
        return True

    def action_onayla(self):
        for d in self:
            if d.durum != 'hesaplandi':
                raise UserError(self.env._('Önce bordroyu hesaplayın.'))
            d.action_hesapla()  # son verilerle tekrar
            d.move_id = d._muhasebe_fisi()
            d.durum = 'onaylandi'
            d.message_post(body=self.env._('Bordro onaylandı, muhasebe fişi %s oluşturuldu.', d.move_id.name))
        return True

    def action_taslaga_al(self):
        for d in self:
            sonraki = self.search([('company_id', '=', d.company_id.id), ('yil', '=', d.yil), ('durum', '=', 'onaylandi'),
                                   ('id', '!=', d.id)]).filtered(lambda x: int(x.ay) > int(d.ay))
            if sonraki:
                raise UserError(self.env._('Sonraki aylar (%s) onaylı; kümülatif vergi matrahı bozulmaması için önce onları taslağa alın.',
                                           ', '.join(sonraki.mapped('name'))))
            if d.move_id:
                if d.move_id.state == 'posted':
                    d.move_id.button_draft()
                d.move_id.button_cancel()
            d.write({'durum': 'taslak', 'move_id': False})
        return True

    # -------------------------------------------------------------------------
    # Muhasebe
    # -------------------------------------------------------------------------

    def _hesap(self, kod):
        hesap = self.env['account.account'].search([('code', '=like', f'{kod}%'), ('company_ids', 'in', self.company_id.root_id.id)],
                                                   order='code', limit=1)
        if not hesap:
            raise UserError(self.env._('%s hesabı hesap planında bulunamadı.', kod))
        return hesap

    def _muhasebe_fisi(self):
        self.ensure_one()
        yevmiye = self.company_id.atlas_bordro_yevmiye_id or self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company_id.id)], limit=1)
        varsayilan_gider = self.company_id.atlas_bordro_gider_hesap_id or self._hesap('770')
        h335, h360, h361 = self._hesap('335'), self._hesap('360'), self._hesap('361')
        satirlar = []

        def ekle(hesap, borc, alacak, ad, partner=False):
            if yuvarla(borc) or yuvarla(alacak):
                satirlar.append(Command.create({'account_id': hesap.id, 'debit': yuvarla(borc), 'credit': yuvarla(alacak),
                                                'name': ad, 'partner_id': partner}))

        gider_toplam = {}
        vergi = sgk = 0.0
        for b in self.bordro_ids:
            gider = b.employee_id.department_id.atlas_gider_hesap_id or varsayilan_gider
            gider_toplam[gider] = gider_toplam.get(gider, 0.0) + b.brut_toplam + b.sgk_isveren + b.issizlik_isveren
            partner = b.employee_id.work_contact_id.id or False
            ekle(h335, 0, b.net, self.env._('%(ad)s %(donem)s net ücret', ad=b.employee_id.name, donem=self.name), partner)
            for k in b.kalem_ids.filtered(lambda x: x.yon == 'kesinti' and x.tutar):
                ekle(k.tur_id.hesap_id or h335, 0, k.tutar, f'{b.employee_id.name} - {k.tur_id.name}', partner)
            vergi += b.gv + b.dv
            sgk += b.sgk_isci + b.issizlik_isci + b.sgk_isveren + b.issizlik_isveren
        for gider, tutar in gider_toplam.items():
            ekle(gider, tutar, 0, self.env._('%s ücret ve SGK işveren gideri', self.name))
        ekle(h360, 0, vergi, self.env._('%s gelir ve damga vergisi', self.name))
        ekle(h361, 0, sgk, self.env._('%s SGK ve işsizlik primleri', self.name))
        fis = self.env['account.move'].create({'move_type': 'entry', 'journal_id': yevmiye.id, 'date': self.tarih_bit,
                                               'ref': self.env._('Bordro %s', self.name), 'line_ids': satirlar})
        fis.action_post()
        return fis

    # -------------------------------------------------------------------------
    # Çıktılar
    # -------------------------------------------------------------------------

    def _xlsx(self, ad, basliklar, satirlar):
        import xlsxwriter
        tampon = io.BytesIO()
        kitap = xlsxwriter.Workbook(tampon, {'in_memory': True})
        sayfa = kitap.add_worksheet(ad[:31])
        kalin = kitap.add_format({'bold': True, 'bg_color': '#E5E7EB', 'border': 1})
        para = kitap.add_format({'num_format': '#,##0.00', 'border': 1})
        duz = kitap.add_format({'border': 1})
        for i, b in enumerate(basliklar):
            sayfa.write(0, i, b, kalin)
            sayfa.set_column(i, i, max(12, len(b) + 2))
        for r, satir in enumerate(satirlar, start=1):
            for c, deger in enumerate(satir):
                sayfa.write(r, c, deger, para if isinstance(deger, float) else duz)
        kitap.close()
        ek = self.env['ir.attachment'].create({'name': f'{ad}.xlsx', 'raw': tampon.getvalue(), 'res_model': self._name, 'res_id': self.id,
                                               'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{ek.id}?download=true', 'target': 'self'}

    def action_banka_listesi(self):
        self.ensure_one()
        satirlar = []
        for b in self.bordro_ids.sorted(lambda x: x.employee_id.name):
            hesap = b.employee_id.sudo().primary_bank_account_id
            satirlar.append([b.employee_id.name, b.employee_id.sudo().identification_id or '', hesap.account_number or '',
                             hesap.bank_name or '', b.net, self.env._('%s maaş', self.name)])
        return self._xlsx(f'Maaş Ödeme Listesi {self.name}', ['Ad Soyad', 'TCKN', 'IBAN', 'Banka', 'Tutar', 'Açıklama'], satirlar)

    def action_sgk_listesi(self):
        """e-Bildirge / MUHSGK için çalışan bazında prime esas kazanç dökümü."""
        self.ensure_one()
        satirlar = []
        for b in self.bordro_ids.sorted(lambda x: x.employee_id.name):
            e = b.employee_id.sudo()
            ad, _, soyad = (e.name or '').rpartition(' ')
            satirlar.append([e.identification_id or '', ad or e.name, soyad, e.atlas_sgk_no or '', e.atlas_meslek_kodu or '',
                             b.gun, b.sgk_matrah, b.sgk_matrah_ikramiye, b.eksik_gun, b.eksik_gun_nedeni or '',
                             fields.Date.to_string(b.giris_tarihi) if b.giris_tarihi else '',
                             fields.Date.to_string(b.cikis_tarihi) if b.cikis_tarihi else '',
                             b.gv_matrah, b.gv, b.dv, '5510/81-ı (5 puan)' if b.tesvik else ''])
        return self._xlsx(f'SGK-MUHSGK {self.name}', ['TCKN', 'Ad', 'Soyad', 'SGK No', 'Meslek Kodu', 'Prim Günü', 'PEK',
                                                      'İkramiye PEK', 'Eksik Gün', 'Eksik Gün Nedeni', 'Giriş', 'Çıkış',
                                                      'GV Matrahı', 'Gelir Vergisi', 'Damga Vergisi', 'Teşvik'], satirlar)

    def action_pusulalar(self):
        return self.env.ref('atlas_bordro.action_report_pusula').report_action(self.bordro_ids)


class AtlasBordro(models.Model):
    _name = 'atlas.bordro'
    _description = 'Çalışan Bordrosu'
    _order = 'donem_id desc, employee_id'

    donem_id = fields.Many2one('atlas.bordro.donem', string='Dönem', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', string='Çalışan', required=True, index=True)
    version_id = fields.Many2one('hr.version', string='Sözleşme')
    company_id = fields.Many2one(related='donem_id.company_id', store=True)
    currency_id = fields.Many2one(related='donem_id.currency_id')
    yil = fields.Integer(related='donem_id.yil', store=True)
    ay = fields.Selection(related='donem_id.ay', store=True)
    durum = fields.Selection(related='donem_id.durum', store=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    kalem_ids = fields.One2many('atlas.bordro.kalem', 'bordro_id', string='Ek Ödeme ve Kesintiler')

    gun = fields.Integer(string='Prim Günü', readonly=True)
    eksik_gun = fields.Integer(string='Eksik Gün', readonly=True)
    eksik_gun_nedeni = fields.Selection(EKSIK_GUN_NEDENLERI, string='Eksik Gün Nedeni')
    giris_tarihi = fields.Date(string='Giriş', readonly=True)
    cikis_tarihi = fields.Date(string='Çıkış', readonly=True)
    aylik_brut = fields.Monetary(string='Aylık Brüt Ücret', readonly=True)
    brut_ucret = fields.Monetary(string='Dönem Brüt Ücreti', readonly=True)
    ek_odeme = fields.Monetary(string='Ek Ödemeler', readonly=True)
    brut_toplam = fields.Monetary(string='Brüt Toplam', readonly=True)
    sgk_matrah = fields.Monetary(string='SGK Matrahı (PEK)', readonly=True)
    sgk_matrah_ikramiye = fields.Monetary(string='İkramiye PEK', readonly=True)
    sgk_isci = fields.Monetary(string='SGK İşçi Payı', readonly=True)
    issizlik_isci = fields.Monetary(string='İşsizlik İşçi Payı', readonly=True)
    engelli_indirimi = fields.Monetary(string='Engelli İndirimi', readonly=True)
    gv_matrah = fields.Monetary(string='GV Matrahı', readonly=True)
    kumulatif_onceki = fields.Monetary(string='Önceki Kümülatif Matrah', readonly=True)
    kumulatif = fields.Monetary(string='Kümülatif Matrah', readonly=True)
    gv_hesaplanan = fields.Monetary(string='Hesaplanan GV', readonly=True)
    gv_istisna = fields.Monetary(string='Asgari Ücret GV İstisnası', readonly=True)
    gv = fields.Monetary(string='Gelir Vergisi', readonly=True)
    dv_hesaplanan = fields.Monetary(string='Hesaplanan DV', readonly=True)
    dv_istisna = fields.Monetary(string='Asgari Ücret DV İstisnası', readonly=True)
    dv = fields.Monetary(string='Damga Vergisi', readonly=True)
    kesinti = fields.Monetary(string='Kesintiler', readonly=True)
    net = fields.Monetary(string='Net Ödenecek', readonly=True)
    sgk_isveren = fields.Monetary(string='SGK İşveren Payı', readonly=True)
    issizlik_isveren = fields.Monetary(string='İşsizlik İşveren Payı', readonly=True)
    tesvik = fields.Monetary(string='Hazine Teşviki', readonly=True)
    maliyet = fields.Monetary(string='Toplam İşveren Maliyeti', readonly=True)
    vergi_dilimi = fields.Float(string='Vergi Dilimi %', readonly=True)

    _calisan_uniq = models.Constraint('UNIQUE(donem_id, employee_id)', 'Çalışan bu dönemde zaten var.')

    @api.depends('employee_id', 'donem_id')
    def _compute_display_name(self):
        for b in self:
            b.display_name = f'{b.employee_id.name} - {b.donem_id.name}'

    # -------------------------------------------------------------------------
    # Gün hesabı
    # -------------------------------------------------------------------------

    def _gunler(self):
        """(prim günü, eksik gün, eksik nedeni, giriş, çıkış). SGK'da tam ay 30 gündür."""
        self.ensure_one()
        d = self.donem_id
        v = self.version_id or self.employee_id.version_id
        bas, bit = d.tarih_bas, d.tarih_bit
        giris = v.contract_date_start if v.contract_date_start and v.contract_date_start > bas else False
        cikis = v.contract_date_end if v.contract_date_end and v.contract_date_end < bit else False
        calisma_bas, calisma_bit = giris or bas, cikis or bit
        if calisma_bas > calisma_bit:
            return 0, 0, False, giris, cikis
        # Ay 30 gün kabul edilir: ay içi girişte 30 - (giriş günü - 1), ay içi çıkışta çıkış günü (en çok 30)
        ilk = giris.day if giris else 1
        son = min(cikis.day, 30) if cikis else 30
        gun = max(son - ilk + 1, 0)
        # Ücretsiz izinler
        izinler = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id), ('state', '=', 'validate'), ('work_entry_type_id.atlas_ucretsiz', '=', True),
            ('request_date_from', '<=', calisma_bit), ('request_date_to', '>=', calisma_bas)])
        eksik, neden = 0, False
        for izin in izinler:
            ust = min(izin.request_date_to, calisma_bit)
            alt = max(izin.request_date_from, calisma_bas)
            eksik += (ust - alt).days + 1
            neden = izin.work_entry_type_id.atlas_eksik_gun_nedeni or '21'
        eksik = min(eksik, gun)
        return gun - eksik, eksik, (neden if eksik else False), giris, cikis

    # -------------------------------------------------------------------------
    # Hesap
    # -------------------------------------------------------------------------

    def _onceki_kumulatif(self):
        self.ensure_one()
        onceki = self.search([('employee_id', '=', self.employee_id.id), ('yil', '=', self.yil), ('company_id', '=', self.company_id.id),
                              ('id', '!=', self.id), ('durum', 'in', ('hesaplandi', 'onaylandi'))]).filtered(lambda b: int(b.ay) < int(self.ay))
        devreden = self.employee_id.sudo().atlas_devreden_matrah if self.employee_id.sudo().atlas_devreden_yil == self.yil else 0.0
        return sum(onceki.mapped('gv_matrah')) + (devreden or 0.0)

    def _hesap_motoru(self, aylik_brut, p, gun, kum_once, kalemli=True):
        """Verilen aylık brüt için tüm kalemleri hesaplar. kalemli=False: ek ödeme/kesintisiz (net→brüt araması)."""
        emp = self.employee_id.sudo()
        ay = int(self.ay)
        oran = gun / 30.0
        brut_ucret = yuvarla(aylik_brut * oran)
        kalemler = self.kalem_ids if kalemli else self.env['atlas.bordro.kalem']
        ekler = kalemler.filtered(lambda k: k.yon == 'ek')
        kesintiler = kalemler.filtered(lambda k: k.yon == 'kesinti')
        saatlik_ucret = aylik_brut / AYLIK_SAAT
        ek_tutarlari = {k: (yuvarla(k.saat * saatlik_ucret * (k.tur_id.oran or 1.0)) if k.tur_id.saatlik else k.tutar) for k in ekler}
        ek_toplam = sum(ek_tutarlari.values())
        brut_toplam = brut_ucret + ek_toplam
        sgk_tabi = brut_ucret + sum(t for k, t in ek_tutarlari.items() if k.tur_id.sgk_tabi)
        yemek_istisna = 0.0
        for k, t in ek_tutarlari.items():
            if k.tur_id.yemek_istisnasi:
                yemek_istisna += min(t, p.yemek_istisna_gunluk * (k.gun or gun))
        sgk_tabi -= min(yemek_istisna, sgk_tabi)
        tavan = p._sgk_tavan() * oran
        taban = p.asgari_brut * oran
        sgk_matrah = yuvarla(min(max(sgk_tabi, taban if gun else 0), tavan))
        if emp.atlas_emekli:
            sgk_isci, issizlik_isci = yuvarla(sgk_matrah * p.sgdp_isci / 100), 0.0
            sgk_isveren, issizlik_isveren, tesvik = yuvarla(sgk_matrah * p.sgdp_isveren / 100), 0.0, 0.0
        else:
            sgk_isci = yuvarla(sgk_matrah * p.sgk_isci / 100)
            issizlik_isci = yuvarla(sgk_matrah * p.issizlik_isci / 100)
            tesvik = yuvarla(sgk_matrah * p.tesvik_puan / 100) if emp.atlas_tesvik else 0.0
            sgk_isveren = yuvarla(sgk_matrah * p.sgk_isveren / 100) - tesvik
            issizlik_isveren = yuvarla(sgk_matrah * p.issizlik_isveren / 100)
        gv_tabi = brut_ucret + sum(t for k, t in ek_tutarlari.items() if k.tur_id.gv_tabi) - yemek_istisna
        engelli = yuvarla(p._engelli_indirimi(emp.atlas_engelli_derece) * oran) if emp.atlas_engelli_derece not in (False, '0') else 0.0
        gv_matrah = yuvarla(max(gv_tabi - sgk_isci - issizlik_isci - engelli, 0.0))
        kumulatif = kum_once + gv_matrah
        gv_hesaplanan = yuvarla(p._vergi(kumulatif) - p._vergi(kum_once))
        # Asgari ücret istisnası: asgari ücretin kümülatif matrahına göre o ayın vergisi (gün oranında)
        asg = p._asgari_gv_matrah()
        istisna_tam = p._vergi(asg * ay) - p._vergi(asg * (ay - 1))
        gv_istisna = yuvarla(min(istisna_tam * oran, gv_hesaplanan))
        gv = yuvarla(gv_hesaplanan - gv_istisna)
        dv_tabi = brut_ucret + sum(t for k, t in ek_tutarlari.items() if k.tur_id.dv_tabi)
        dv_hesaplanan = yuvarla(dv_tabi * p.damga_binde / 1000)
        dv_istisna = yuvarla(min(p.asgari_brut * oran * p.damga_binde / 1000, dv_hesaplanan))
        dv = yuvarla(dv_hesaplanan - dv_istisna)
        kesinti = yuvarla(sum(kesintiler.mapped('tutar')))
        net = yuvarla(brut_toplam - sgk_isci - issizlik_isci - gv - dv - kesinti)
        dilim = next((o for ust, o in p._dilimler() if ust is None or kumulatif <= ust), 0.0)
        return {
            'aylik_brut': yuvarla(aylik_brut), 'brut_ucret': brut_ucret, 'ek_odeme': yuvarla(ek_toplam), 'brut_toplam': yuvarla(brut_toplam),
            'sgk_matrah': sgk_matrah, 'sgk_matrah_ikramiye': 0.0, 'sgk_isci': sgk_isci, 'issizlik_isci': issizlik_isci,
            'engelli_indirimi': engelli, 'gv_matrah': gv_matrah, 'kumulatif_onceki': yuvarla(kum_once), 'kumulatif': yuvarla(kumulatif),
            'gv_hesaplanan': gv_hesaplanan, 'gv_istisna': gv_istisna, 'gv': gv, 'dv_hesaplanan': dv_hesaplanan, 'dv_istisna': dv_istisna,
            'dv': dv, 'kesinti': kesinti, 'net': net, 'sgk_isveren': yuvarla(sgk_isveren), 'issizlik_isveren': issizlik_isveren,
            'tesvik': tesvik, 'maliyet': yuvarla(brut_toplam + sgk_isveren + issizlik_isveren), 'vergi_dilimi': dilim,
            '_ek_tutarlari': ek_tutarlari,
        }

    def _hesapla(self):
        for b in self:
            p = b.donem_id.parametre_id or self.env['atlas.bordro.parametre']._bul(b.yil, int(b.ay))
            emp = b.employee_id.sudo()
            gun, eksik, neden, giris, cikis = b._gunler()
            kum_once = b._onceki_kumulatif()
            v = b.version_id or emp.version_id
            if emp.atlas_ucret_tipi == 'net':
                if not emp.atlas_net_ucret:
                    raise UserError(self.env._('%s için anlaşılan net ücret girilmemiş.', emp.name))
                hedef = emp.atlas_net_ucret
                # Anlaşılan net (tam ay, ek/kesintisiz) için gereken aylık brüt: ikili arama
                alt, ust = hedef, hedef * 2.5 + 1
                for _ in range(100):
                    orta = (alt + ust) / 2
                    if b._hesap_motoru(orta, p, 30, kum_once, kalemli=False)['net'] < hedef:
                        alt = orta
                    else:
                        ust = orta
                    if ust - alt < 0.001:
                        break
                aylik_brut = yuvarla(ust)
            else:
                aylik_brut = v.wage
                if not aylik_brut:
                    raise UserError(self.env._('%s için sözleşmede brüt ücret yok.', emp.name))
            sonuc = b._hesap_motoru(aylik_brut, p, gun, kum_once)
            for kalem, tutar in sonuc.pop('_ek_tutarlari').items():
                if kalem.tur_id.saatlik:
                    kalem.tutar = tutar
            sonuc.update({'gun': gun, 'eksik_gun': eksik, 'eksik_gun_nedeni': neden or b.eksik_gun_nedeni, 'giris_tarihi': giris,
                          'cikis_tarihi': cikis, 'version_id': v.id})
            b.write(sonuc)
        return True

    def action_yeniden_hesapla(self):
        self.donem_id._kilit_kontrol()
        if any(not b.donem_id.parametre_id for b in self):
            for d in self.donem_id:
                d.parametre_id = self.env['atlas.bordro.parametre']._bul(d.yil, int(d.ay))
        self._hesapla()
        return True

    def action_pusula(self):
        return self.env.ref('atlas_bordro.action_report_pusula').report_action(self)


class AtlasBordroKalem(models.Model):
    _name = 'atlas.bordro.kalem'
    _description = 'Bordro Ek Ödeme / Kesinti'
    _order = 'bordro_id, yon, id'

    bordro_id = fields.Many2one('atlas.bordro', required=True, ondelete='cascade', index=True)
    tur_id = fields.Many2one('atlas.bordro.kalem.turu', string='Kalem', required=True)
    yon = fields.Selection(related='tur_id.yon', store=True)
    saatlik = fields.Boolean(related='tur_id.saatlik')
    saat = fields.Float(string='Saat')
    gun = fields.Integer(string='Gün', help='Yemek yardımında istisna için çalışılan gün; boşsa prim günü.')
    tutar = fields.Monetary(string='Tutar', currency_field='currency_id')
    currency_id = fields.Many2one(related='bordro_id.currency_id')
    aciklama = fields.Char(string='Açıklama')

    @api.constrains('tutar', 'saat')
    def _check_tutar(self):
        for k in self:
            if k.tutar < 0 or k.saat < 0:
                raise ValidationError(self.env._('Tutar ve saat negatif olamaz; kesinti için kesinti türü seçin.'))
