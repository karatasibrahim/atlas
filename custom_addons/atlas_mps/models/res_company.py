from odoo import fields, models

MPS_PERIYOTLARI = [('gun', 'Gün'), ('hafta', 'Hafta'), ('ay', 'Ay')]
MPS_TALEP = [
    ('en_buyuk', 'Tahmin ile gerçek talebin büyüğü'),
    ('tahmin', 'Yalnızca tahmin'),
    ('gercek', 'Yalnızca gerçek talep'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_mps_periyot = fields.Selection(MPS_PERIYOTLARI, string='MPS Dönemi', default='ay', required=True)
    atlas_mps_periyot_sayisi = fields.Integer(string='MPS Dönem Sayısı', default=12)
    atlas_mps_talep = fields.Selection(MPS_TALEP, string='MPS Talep Hesabı', default='en_buyuk', required=True)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_mps_periyot = fields.Selection(related='company_id.atlas_mps_periyot', readonly=False)
    atlas_mps_periyot_sayisi = fields.Integer(related='company_id.atlas_mps_periyot_sayisi', readonly=False)
    atlas_mps_talep = fields.Selection(related='company_id.atlas_mps_talep', readonly=False)
