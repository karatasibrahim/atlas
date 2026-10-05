from odoo import api, fields, models
from odoo.exceptions import UserError

from .bordro import yuvarla


class AtlasBordroKidem(models.TransientModel):
    _name = 'atlas.bordro.kidem'
    _description = 'Kıdem ve İhbar Tazminatı Hesabı'

    employee_id = fields.Many2one('hr.employee', string='Çalışan', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    giris_tarihi = fields.Date(string='İşe Giriş', required=True)
    cikis_tarihi = fields.Date(string='Çıkış Tarihi', required=True, default=fields.Date.context_today)
    giydirilmis_brut = fields.Monetary(string='Giydirilmiş Brüt Ücret', required=True,
                                       help='Son brüt ücret + sürekli ödenen yan haklar (yol, yemek, ikramiyenin aylık payı …).')
    kidem_hakki = fields.Boolean(string='Kıdem Tazminatı Hakkı', default=True,
                                 help='En az 1 yıl çalışma ve kanunda sayılan fesih nedeni gerekir.')
    ihbar_hakki = fields.Boolean(string='İhbar Tazminatı Ödenecek', help='İşveren bildirim süresine uymadan feshederse.')
    kullanilmayan_izin_gun = fields.Float(string='Kullanılmayan Yıllık İzin (Gün)')
    # Sonuçlar
    hizmet_yil = fields.Integer(string='Yıl', compute='_compute_sonuc')
    hizmet_ay = fields.Integer(string='Ay', compute='_compute_sonuc')
    hizmet_gun = fields.Integer(string='Gün', compute='_compute_sonuc')
    kidem_tavan = fields.Monetary(string='Kıdem Tavanı', compute='_compute_sonuc')
    kidem_esas = fields.Monetary(string='Kıdeme Esas Ücret', compute='_compute_sonuc')
    kidem_brut = fields.Monetary(string='Kıdem Tazminatı (Brüt)', compute='_compute_sonuc')
    kidem_dv = fields.Monetary(string='Kıdem Damga Vergisi', compute='_compute_sonuc')
    kidem_net = fields.Monetary(string='Kıdem Tazminatı (Net)', compute='_compute_sonuc')
    ihbar_hafta = fields.Integer(string='İhbar Süresi (Hafta)', compute='_compute_sonuc')
    ihbar_brut = fields.Monetary(string='İhbar Tazminatı (Brüt)', compute='_compute_sonuc')
    ihbar_gv = fields.Monetary(string='İhbar Gelir Vergisi', compute='_compute_sonuc')
    ihbar_dv = fields.Monetary(string='İhbar Damga Vergisi', compute='_compute_sonuc')
    ihbar_net = fields.Monetary(string='İhbar Tazminatı (Net)', compute='_compute_sonuc')
    izin_brut = fields.Monetary(string='İzin Ücreti (Brüt)', compute='_compute_sonuc')
    toplam_net = fields.Monetary(string='Toplam Net Ödeme', compute='_compute_sonuc')
    uyari = fields.Char(compute='_compute_sonuc')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        v = self.employee_id.sudo().version_id
        if v:
            self.giris_tarihi = v.contract_date_start
            self.giydirilmis_brut = v.wage

    @api.depends('employee_id', 'giris_tarihi', 'cikis_tarihi', 'giydirilmis_brut', 'kidem_hakki', 'ihbar_hakki', 'kullanilmayan_izin_gun')
    def _compute_sonuc(self):
        Parametre = self.env['atlas.bordro.parametre']
        for w in self:
            sifir = dict.fromkeys(['hizmet_yil', 'hizmet_ay', 'hizmet_gun', 'kidem_tavan', 'kidem_esas', 'kidem_brut', 'kidem_dv', 'kidem_net',
                                   'ihbar_hafta', 'ihbar_brut', 'ihbar_gv', 'ihbar_dv', 'ihbar_net', 'izin_brut', 'toplam_net'], 0)
            w.update(sifir)
            w.uyari = False
            if not (w.giris_tarihi and w.cikis_tarihi and w.cikis_tarihi >= w.giris_tarihi):
                continue
            try:
                p = Parametre._bul(w.cikis_tarihi.year, w.cikis_tarihi.month)
            except UserError as hata:
                w.uyari = str(hata)
                continue
            gun_toplam = (w.cikis_tarihi - w.giris_tarihi).days + 1
            yil, kalan = divmod(gun_toplam, 365)
            ay, gun = divmod(kalan, 30)
            w.hizmet_yil, w.hizmet_ay, w.hizmet_gun = yil, ay, gun
            gunluk = w.giydirilmis_brut / 30.0
            dv_oran = p.damga_binde / 1000
            if w.kidem_hakki:
                if gun_toplam < 365:
                    w.uyari = self.env._('1 yıldan az çalışmada kıdem tazminatı hakkı doğmaz.')
                else:
                    w.kidem_tavan = p.kidem_tavan
                    esas = min(w.giydirilmis_brut, p.kidem_tavan) if p.kidem_tavan else w.giydirilmis_brut
                    w.kidem_esas = esas
                    w.kidem_brut = yuvarla(esas * gun_toplam / 365)
                    w.kidem_dv = yuvarla(w.kidem_brut * dv_oran)
                    w.kidem_net = w.kidem_brut - w.kidem_dv  # kıdem tazminatı gelir vergisinden istisna
            if w.ihbar_hakki:
                ay_toplam = gun_toplam / 30.0
                w.ihbar_hafta = 2 if ay_toplam < 6 else 4 if ay_toplam < 18 else 6 if ay_toplam < 36 else 8
                w.ihbar_brut = yuvarla(gunluk * 7 * w.ihbar_hafta)
            w.izin_brut = yuvarla(gunluk * (w.kullanilmayan_izin_gun or 0))
            # İhbar ve izin ücreti gelir vergisine tabi: çalışanın yıl içindeki kümülatif matrahıyla
            kum = sum(self.env['atlas.bordro'].search([('employee_id', '=', w.employee_id.id), ('yil', '=', w.cikis_tarihi.year),
                                                       ('durum', 'in', ('hesaplandi', 'onaylandi'))]).mapped('gv_matrah'))
            vergili = w.ihbar_brut + w.izin_brut
            if vergili:
                gv = p._vergi(kum + vergili) - p._vergi(kum)
                w.ihbar_gv = yuvarla(gv)
                w.ihbar_dv = yuvarla(vergili * dv_oran)
                w.ihbar_net = vergili - w.ihbar_gv - w.ihbar_dv
            w.toplam_net = w.kidem_net + w.ihbar_net
