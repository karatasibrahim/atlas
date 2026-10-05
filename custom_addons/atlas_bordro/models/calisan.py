from odoo import fields, models

# SGK eksik gün nedenleri (APHB)
EKSIK_GUN_NEDENLERI = [
    ('01', '01 - İstirahat'), ('03', '03 - Disiplin cezası'), ('04', '04 - Gözaltına alınma'), ('05', '05 - Tutukluluk'),
    ('06', '06 - Kısmi istihdam'), ('07', '07 - Puantaj kayıtları'), ('08', '08 - Grev'), ('09', '09 - Lokavt'),
    ('10', '10 - Genel hayatı etkileyen olaylar'), ('11', '11 - Doğal afet'), ('12', '12 - Birden fazla'),
    ('13', '13 - Diğer'), ('15', '15 - Devamsızlık'), ('16', '16 - Fesih tarihinde çalışmamış'), ('17', '17 - Ev hizmetleri'),
    ('18', '18 - Kısa çalışma ödeneği'), ('19', '19 - Ücretsiz doğum izni'), ('20', '20 - Ücretsiz yol izni'),
    ('21', '21 - Diğer ücretsiz izin'), ('22', '22 - 5434 SK ek 76, GM 192'),
]


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    atlas_ucret_tipi = fields.Selection([('brut', 'Brüt'), ('net', 'Net')], string='Ücret Anlaşması', default='brut',
                                        groups='hr.group_hr_user',
                                        help='Net anlaşmada aylık brüt ücret her ay net tutarı verecek şekilde yeniden hesaplanır.')
    atlas_net_ucret = fields.Monetary(string='Anlaşılan Net Ücret', currency_field='currency_id', groups='hr.group_hr_user')
    atlas_engelli_derece = fields.Selection([('0', 'Yok'), ('1', '1. derece (%80+)'), ('2', '2. derece (%60-79)'),
                                             ('3', '3. derece (%40-59)')], string='Engellilik Derecesi', default='0',
                                            groups='hr.group_hr_user')
    atlas_emekli = fields.Boolean(string='Emekli (SGDP)', groups='hr.group_hr_user',
                                  help='Sosyal güvenlik destek primine tabi çalışan; işsizlik primi kesilmez.')
    atlas_tesvik = fields.Boolean(string='5 Puan Hazine Teşviki', default=True, groups='hr.group_hr_user')
    atlas_sgk_no = fields.Char(string='SGK Sicil No', groups='hr.group_hr_user')
    atlas_meslek_kodu = fields.Char(string='Meslek Kodu', groups='hr.group_hr_user', help='SGK ISCO-08 meslek kodu, ör. 2411.01')
    atlas_devreden_matrah = fields.Monetary(string='Devreden GV Matrahı', currency_field='currency_id', groups='hr.group_hr_user',
                                            help='Yıl içinde başka işverenden gelen çalışanın önceki kümülatif gelir vergisi matrahı.')
    atlas_devreden_yil = fields.Integer(string='Devreden Matrah Yılı', groups='hr.group_hr_user')
    atlas_bordro_ids = fields.One2many('atlas.bordro', 'employee_id', string='Bordrolar', groups='hr.group_hr_user')


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    atlas_gider_hesap_id = fields.Many2one('account.account', string='Personel Gider Hesabı',
                                           help='Bu bölüm çalışanlarının ücret giderleri (ör. 720 direkt işçilik, 730 GÜG, 760, 770). '
                                                'Boşsa şirket varsayılanı.')


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_bordro_gider_hesap_id = fields.Many2one('account.account', string='Varsayılan Personel Gider Hesabı')
    atlas_bordro_yevmiye_id = fields.Many2one('account.journal', string='Bordro Yevmiyesi')
    atlas_sgk_isyeri_no = fields.Char(string='SGK İşyeri Sicil No')


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    atlas_ucretsiz = fields.Boolean(string='Ücretsiz (Bordroda Eksik Gün)',
                                    help='Bu türdeki onaylı izin günleri bordroda eksik gün sayılır ve ücret ödenmez.')
    atlas_eksik_gun_nedeni = fields.Selection(EKSIK_GUN_NEDENLERI, string='SGK Eksik Gün Nedeni')
