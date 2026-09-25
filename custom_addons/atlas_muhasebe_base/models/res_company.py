from odoo import fields, models

TCMB_RATE_TYPE_SELECTION = [
    ('forex_buying', 'Döviz Alış'),
    ('forex_selling', 'Döviz Satış'),
    ('banknote_buying', 'Efektif Alış'),
    ('banknote_selling', 'Efektif Satış'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_tcmb_auto = fields.Boolean(
        string='TCMB Kurlarını Otomatik Güncelle',
        default=True,
    )
    atlas_tcmb_rate_type = fields.Selection(
        TCMB_RATE_TYPE_SELECTION,
        string='TCMB Kur Tipi',
        default='forex_buying',
        required=True,
        help='Sistem kuru olarak kullanılacak TCMB kuru.',
    )
