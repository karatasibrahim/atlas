from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_fis_turu = fields.Selection(selection_add=[('virman', 'Virman')], ondelete={'virman': 'set null'})


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    atlas_banka_journal_id = fields.Many2one(
        'account.journal', string='Beklenen Banka', index='btree_not_null', readonly=True, copy=False,
        help='Virmanın banka ayağı: bu banka hesabının ekstresiyle eşleşmesi beklenen transit satır.')
