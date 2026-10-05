from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

DERECELER = [('A', 'A - Olağanüstü'), ('B', 'B - Beklentinin Üstünde'), ('C', 'C - Beklentiyi Karşılıyor'),
             ('D', 'D - Gelişmeli'), ('E', 'E - Yetersiz')]
DURUMLAR = [('oz', 'Öz Değerlendirme'), ('yonetici', 'Yönetici Değerlendirmesi'), ('gorusme', 'Görüşme'),
            ('tamamlandi', 'Tamamlandı'), ('iptal', 'İptal')]


def derece_bul(puan):
    if puan >= 90:
        return 'A'
    if puan >= 75:
        return 'B'
    if puan >= 60:
        return 'C'
    if puan >= 40:
        return 'D'
    return 'E'


class AtlasDegerlendirmeSablon(models.Model):
    _name = 'atlas.degerlendirme.sablon'
    _description = 'Değerlendirme Şablonu'

    name = fields.Char(string='Şablon', required=True)
    active = fields.Boolean(default=True)
    aciklama = fields.Html(string='Açıklama')
    soru_ids = fields.One2many('atlas.degerlendirme.soru', 'sablon_id', string='Yetkinlikler / Sorular', copy=True)
    hedef_agirligi = fields.Float(string='Hedeflerin Ağırlığı %', default=40.0,
                                  help='Sonuç puanında hedef başarısının payı; kalan yetkinlik puanlarından gelir.')

    @api.constrains('hedef_agirligi')
    def _check_agirlik(self):
        for s in self:
            if not 0 <= s.hedef_agirligi <= 100:
                raise ValidationError(self.env._('Hedef ağırlığı 0-100 arasında olmalı.'))


class AtlasDegerlendirmeSoru(models.Model):
    _name = 'atlas.degerlendirme.soru'
    _description = 'Değerlendirme Sorusu'
    _order = 'sequence, id'

    sablon_id = fields.Many2one('atlas.degerlendirme.sablon', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Yetkinlik / Soru', required=True)
    aciklama = fields.Text(string='Açıklama')
    tur = fields.Selection([('puan', 'Puan (1-5)'), ('metin', 'Yorum')], string='Tür', default='puan', required=True)
    agirlik = fields.Float(string='Ağırlık', default=1.0)


class AtlasHedef(models.Model):
    _name = 'atlas.hedef'
    _description = 'Çalışan Hedefi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'son_tarih, id'

    name = fields.Char(string='Hedef', required=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Çalışan', required=True, index=True, tracking=True)
    yonetici_id = fields.Many2one(related='employee_id.parent_id', string='Yönetici', store=True)
    calisan_kullanici_id = fields.Many2one(related='employee_id.user_id', store=True, string='Çalışan Kullanıcı')
    yonetici_kullanici_id = fields.Many2one(related='employee_id.parent_id.user_id', store=True, string='Yönetici Kullanıcı')
    aciklama = fields.Html(string='Açıklama / Ölçüt')
    baslangic = fields.Date(string='Başlangıç', default=fields.Date.context_today)
    son_tarih = fields.Date(string='Son Tarih')
    agirlik = fields.Float(string='Ağırlık', default=1.0)
    ilerleme = fields.Integer(string='İlerleme %', tracking=True)
    durum = fields.Selection([('acik', 'Devam Ediyor'), ('tamamlandi', 'Tamamlandı'), ('iptal', 'İptal')], string='Durum',
                             default='acik', required=True, tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)

    @api.constrains('ilerleme')
    def _check_ilerleme(self):
        for h in self:
            if not 0 <= h.ilerleme <= 100:
                raise ValidationError(self.env._('İlerleme 0-100 arasında olmalı.'))

    def write(self, vals):
        if vals.get('ilerleme') == 100 and 'durum' not in vals:
            vals['durum'] = 'tamamlandi'
        return super().write(vals)


class AtlasDegerlendirmeDonem(models.Model):
    _name = 'atlas.degerlendirme.donem'
    _description = 'Değerlendirme Dönemi'
    _inherit = ['mail.thread']
    _order = 'tarih_bit desc, id desc'

    name = fields.Char(string='Dönem', required=True, tracking=True)
    sablon_id = fields.Many2one('atlas.degerlendirme.sablon', string='Şablon', required=True)
    tarih_bas = fields.Date(string='Değerlendirilen Dönem Başı', required=True)
    tarih_bit = fields.Date(string='Değerlendirilen Dönem Sonu', required=True)
    son_tarih = fields.Date(string='Tamamlanma Son Tarihi', required=True)
    oz_degerlendirme = fields.Boolean(string='Öz Değerlendirme', default=True)
    employee_ids = fields.Many2many('hr.employee', string='Çalışanlar')
    department_ids = fields.Many2many('hr.department', string='Bölümler', help='Seçilirse bu bölümlerin tüm çalışanları eklenir.')
    degerlendirme_ids = fields.One2many('atlas.degerlendirme', 'donem_id', string='Değerlendirmeler')
    durum = fields.Selection([('taslak', 'Taslak'), ('devam', 'Devam Ediyor'), ('kapandi', 'Kapandı')], default='taslak',
                             required=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    tamamlanan = fields.Integer(compute='_compute_ilerleme')
    toplam = fields.Integer(compute='_compute_ilerleme')
    ortalama_puan = fields.Float(compute='_compute_ilerleme', string='Ortalama Puan')

    @api.depends('degerlendirme_ids.durum', 'degerlendirme_ids.sonuc_puan')
    def _compute_ilerleme(self):
        for d in self:
            aktif = d.degerlendirme_ids.filtered(lambda x: x.durum != 'iptal')
            biten = aktif.filtered(lambda x: x.durum == 'tamamlandi')
            d.toplam, d.tamamlanan = len(aktif), len(biten)
            d.ortalama_puan = sum(biten.mapped('sonuc_puan')) / len(biten) if biten else 0.0

    def action_baslat(self):
        Deg = self.env['atlas.degerlendirme']
        for d in self:
            calisanlar = d.employee_ids | self.env['hr.employee'].search([('department_id', 'child_of', d.department_ids.ids)]) \
                if d.department_ids else d.employee_ids
            if not calisanlar:
                raise UserError(self.env._('Değerlendirilecek çalışan seçin.'))
            mevcut = d.degerlendirme_ids.employee_id
            for emp in calisanlar - mevcut:
                deg = Deg.create({'donem_id': d.id, 'employee_id': emp.id,
                                  'durum': 'oz' if d.oz_degerlendirme and emp.user_id else 'yonetici'})
                deg._aktivite_olustur()
            d.durum = 'devam'
        return True

    def action_kapat(self):
        for d in self:
            acik = d.degerlendirme_ids.filtered(lambda x: x.durum not in ('tamamlandi', 'iptal'))
            if acik:
                raise UserError(self.env._('%s değerlendirme tamamlanmadı.', len(acik)))
            d.durum = 'kapandi'
        return True


class AtlasDegerlendirme(models.Model):
    _name = 'atlas.degerlendirme'
    _description = 'Performans Değerlendirmesi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    donem_id = fields.Many2one('atlas.degerlendirme.donem', string='Dönem', required=True, ondelete='cascade', index=True)
    sablon_id = fields.Many2one(related='donem_id.sablon_id')
    employee_id = fields.Many2one('hr.employee', string='Çalışan', required=True, index=True)
    yonetici_id = fields.Many2one('hr.employee', string='Değerlendiren Yönetici', compute='_compute_yonetici', store=True, readonly=False)
    calisan_kullanici_id = fields.Many2one(related='employee_id.user_id', store=True, string='Çalışan Kullanıcı')
    yonetici_kullanici_id = fields.Many2one(related='yonetici_id.user_id', store=True, string='Yönetici Kullanıcı')
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    durum = fields.Selection(DURUMLAR, string='Durum', default='oz', required=True, tracking=True)
    cevap_ids = fields.One2many('atlas.degerlendirme.cevap', 'degerlendirme_id', string='Yetkinlikler')
    hedef_ids = fields.Many2many('atlas.hedef', compute='_compute_hedef_ids', string='Dönem Hedefleri')
    guclu_yonler = fields.Text(string='Güçlü Yönler')
    gelisim_alanlari = fields.Text(string='Gelişim Alanları')
    oz_yorum = fields.Text(string='Çalışanın Yorumu')
    yonetici_yorum = fields.Text(string='Yöneticinin Yorumu')
    gorusme_tarihi = fields.Datetime(string='Görüşme')
    calisan_onayi = fields.Boolean(string='Çalışan Okudu ve Onayladı', readonly=True)
    yetkinlik_puan = fields.Float(string='Yetkinlik Puanı', compute='_compute_puan', store=True, digits=(5, 1))
    hedef_puan = fields.Float(string='Hedef Başarısı', compute='_compute_puan', store=True, digits=(5, 1))
    sonuc_puan = fields.Float(string='Sonuç Puanı', compute='_compute_puan', store=True, digits=(5, 1))
    derece = fields.Selection(DERECELER, string='Derece', compute='_compute_puan', store=True)
    son_tarih = fields.Date(related='donem_id.son_tarih', store=True)
    company_id = fields.Many2one(related='donem_id.company_id', store=True)

    _uniq = models.Constraint('UNIQUE(donem_id, employee_id)', 'Çalışan bu dönemde zaten değerlendiriliyor.')

    @api.depends('employee_id', 'donem_id')
    def _compute_name(self):
        for d in self:
            d.name = f'{d.employee_id.name} - {d.donem_id.name}'

    @api.depends('employee_id')
    def _compute_yonetici(self):
        for d in self:
            if not d.yonetici_id:
                d.yonetici_id = d.employee_id.parent_id

    def _compute_hedef_ids(self):
        for d in self:
            d.hedef_ids = self.env['atlas.hedef'].sudo().search([
                ('employee_id', '=', d.employee_id.id), ('durum', '!=', 'iptal'),
                '|', ('son_tarih', '=', False), '&', ('son_tarih', '>=', d.donem_id.tarih_bas), ('son_tarih', '<=', d.donem_id.son_tarih)])

    @api.depends('cevap_ids.yonetici_puan', 'cevap_ids.agirlik', 'donem_id.sablon_id.hedef_agirligi', 'durum')
    def _compute_puan(self):
        for d in self:
            puanli = d.cevap_ids.filtered(lambda c: c.tur == 'puan' and c.yonetici_puan)
            toplam_agirlik = sum(puanli.mapped('agirlik'))
            d.yetkinlik_puan = (sum(int(c.yonetici_puan) * c.agirlik for c in puanli) / toplam_agirlik * 20) if toplam_agirlik else 0.0
            hedefler = d.sudo().hedef_ids
            ha = sum(hedefler.mapped('agirlik'))
            d.hedef_puan = sum(h.ilerleme * h.agirlik for h in hedefler) / ha if ha else 0.0
            pay = (d.sablon_id.hedef_agirligi / 100.0) if hedefler else 0.0
            d.sonuc_puan = d.yetkinlik_puan * (1 - pay) + d.hedef_puan * pay
            d.derece = derece_bul(d.sonuc_puan) if puanli else False

    @api.model_create_multi
    def create(self, vals_list):
        kayitlar = super().create(vals_list)
        for d in kayitlar:
            d.cevap_ids = [Command.create({'soru_id': s.id}) for s in d.donem_id.sablon_id.soru_ids]
        return kayitlar

    # -------------------------------------------------------------------------
    # Yetki ve akış
    # -------------------------------------------------------------------------

    def _ik_mi(self):
        return self.env.su or self.env.user.has_group('hr.group_hr_manager')

    def _calisan_mi(self):
        return self.calisan_kullanici_id == self.env.user

    def _yonetici_mi(self):
        return self.yonetici_kullanici_id == self.env.user

    def _aktivite_olustur(self):
        for d in self.sudo():
            if d.durum == 'oz' and d.employee_id.user_id:
                d.activity_schedule('mail.mail_activity_data_todo', date_deadline=d.son_tarih, user_id=d.employee_id.user_id.id,
                                    summary=self.env._('Öz değerlendirmenizi doldurun'))
            elif d.durum == 'yonetici':
                kullanici = d.yonetici_id.user_id or self.env.user
                d.activity_schedule('mail.mail_activity_data_todo', date_deadline=d.son_tarih, user_id=kullanici.id,
                                    summary=self.env._('%s için değerlendirme yapın', d.employee_id.name))

    def action_oz_tamamla(self):
        for d in self:
            if d.durum != 'oz':
                continue
            if not (d._calisan_mi() or d._ik_mi()):
                raise AccessError(self.env._('Öz değerlendirmeyi yalnız çalışan tamamlayabilir.'))
            eksik = d.cevap_ids.filtered(lambda c: c.tur == 'puan' and not c.oz_puan)
            if eksik:
                raise UserError(self.env._('Puanlanmamış yetkinlikler: %s', ', '.join(eksik.mapped('soru_id.name'))))
            d.sudo().activity_ids.filtered(lambda a: a.user_id == d.calisan_kullanici_id).action_feedback()
            d.sudo().durum = 'yonetici'
            d.sudo()._aktivite_olustur()
        return True

    def action_yonetici_tamamla(self):
        for d in self:
            if d.durum != 'yonetici':
                continue
            if not (d._yonetici_mi() or d._ik_mi()):
                raise AccessError(self.env._('Bu değerlendirmeyi yalnız yöneticisi veya İK tamamlayabilir.'))
            eksik = d.cevap_ids.filtered(lambda c: c.tur == 'puan' and not c.yonetici_puan)
            if eksik:
                raise UserError(self.env._('Puanlanmamış yetkinlikler: %s', ', '.join(eksik.mapped('soru_id.name'))))
            d.sudo().activity_ids.action_feedback()
            d.sudo().durum = 'gorusme'
            d.sudo().activity_schedule('mail.mail_activity_data_meeting', user_id=(d.yonetici_kullanici_id or self.env.user).id,
                                       summary=self.env._('%s ile değerlendirme görüşmesi', d.sudo().employee_id.name))
        return True

    def action_calisan_onayla(self):
        for d in self:
            if d.durum != 'gorusme':
                raise UserError(self.env._('Değerlendirme görüşme aşamasında değil.'))
            if not (d._calisan_mi() or d._ik_mi()):
                raise AccessError(self.env._('Yalnız çalışan onaylayabilir.'))
            d.sudo().calisan_onayi = True
            d.sudo().message_post(body=self.env._('%s değerlendirmeyi okudu ve onayladı.', self.env.user.name))
        return True

    def action_tamamla(self):
        for d in self:
            if d.durum != 'gorusme':
                raise UserError(self.env._('Önce yönetici değerlendirmesi tamamlanmalı.'))
            if not (d._yonetici_mi() or d._ik_mi()):
                raise AccessError(self.env._('Yalnız yönetici veya İK tamamlayabilir.'))
            d.sudo().activity_ids.action_feedback()
            d.sudo().write({'durum': 'tamamlandi', 'gorusme_tarihi': d.gorusme_tarihi or fields.Datetime.now()})
            d.employee_id.sudo().atlas_son_derece = d.derece
            d.employee_id.sudo().atlas_sonraki_degerlendirme = d.donem_id.tarih_bit + relativedelta(years=1)
        return True

    def action_geri_al(self):
        for d in self:
            if not d._ik_mi():
                raise AccessError(self.env._('Yalnız İK geri alabilir.'))
            if d.durum in ('gorusme', 'tamamlandi'):
                d.write({'durum': 'yonetici', 'calisan_onayi': False})
        return True


class AtlasDegerlendirmeCevap(models.Model):
    _name = 'atlas.degerlendirme.cevap'
    _description = 'Değerlendirme Cevabı'
    _order = 'sequence, id'

    degerlendirme_id = fields.Many2one('atlas.degerlendirme', required=True, ondelete='cascade', index=True)
    soru_id = fields.Many2one('atlas.degerlendirme.soru', string='Yetkinlik', required=True)
    sequence = fields.Integer(related='soru_id.sequence', store=True)
    tur = fields.Selection(related='soru_id.tur')
    agirlik = fields.Float(related='soru_id.agirlik', store=True)
    aciklama = fields.Text(related='soru_id.aciklama')
    oz_puan = fields.Selection([('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')], string='Öz Puan')
    oz_yorum = fields.Char(string='Çalışan Notu')
    yonetici_puan = fields.Selection([('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')], string='Yönetici Puanı')
    yonetici_yorum = fields.Char(string='Yönetici Notu')

    def write(self, vals):
        for c in self:
            d = c.degerlendirme_id
            if d._ik_mi():
                continue
            if {'oz_puan', 'oz_yorum'} & set(vals) and not (d.durum == 'oz' and d._calisan_mi()):
                raise AccessError(self.env._('Öz değerlendirme yalnız çalışan tarafından ve öz değerlendirme aşamasında doldurulur.'))
            if {'yonetici_puan', 'yonetici_yorum'} & set(vals) and not (d.durum == 'yonetici' and d._yonetici_mi()):
                raise AccessError(self.env._('Yönetici puanı yalnız yönetici tarafından ve yönetici aşamasında girilir.'))
        return super().write(vals)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    atlas_son_derece = fields.Selection(DERECELER, string='Son Performans Derecesi', groups='hr.group_hr_user')
    atlas_sonraki_degerlendirme = fields.Date(string='Sonraki Değerlendirme', groups='hr.group_hr_user')
    atlas_hedef_ids = fields.One2many('atlas.hedef', 'employee_id', string='Hedefler')
