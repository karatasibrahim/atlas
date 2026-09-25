from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_fis_turu = fields.Selection(selection_add=[('cek_senet', 'Çek / Senet')], ondelete={'cek_senet': 'set null'})
    atlas_cek_bordro_id = fields.Many2one('atlas.cek.bordro', string='Çek/Senet Bordrosu', readonly=True, index='btree_not_null')
