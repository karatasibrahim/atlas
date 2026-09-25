from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_yevmiye_no = fields.Integer(
        string='Yevmiye Madde No', readonly=True, copy=False, index='btree_not_null',
        help='Yevmiye defterindeki kesin madde numarası (dönem sonu numaralandırmasıyla verilir).')
