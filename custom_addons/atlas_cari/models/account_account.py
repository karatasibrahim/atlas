from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    atlas_partner_id = fields.Many2one(
        'res.partner',
        string='Cari',
        index='btree_not_null',
        ondelete='restrict',
        readonly=True,
        help='Bu hesap, cari için otomatik açılmış 120/320 alt hesabıdır.',
    )
