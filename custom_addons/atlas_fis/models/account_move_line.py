from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    atlas_kasa_line = fields.Boolean(
        string='Kasa Satırı', readonly=True, copy=False,
        help='Tahsil/Tediye fişinde otomatik oluşturulan kasa karşılık satırı.')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._atlas_set_cari_partner()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'account_id' in vals:
            self._atlas_set_cari_partner()
        return res

    @api.onchange('account_id')
    def _onchange_atlas_cari_account(self):
        if self.account_id.atlas_partner_id:
            self.partner_id = self.account_id.atlas_partner_id

    def _atlas_set_cari_partner(self):
        """Cari alt hesabına (120-00-0001 vb.) yazılan satıra, cari boşsa hesabın carisini ata."""
        for line in self.filtered(lambda l: l.account_id.atlas_partner_id and not l.partner_id and l.parent_state == 'draft'):
            line.partner_id = line.account_id.atlas_partner_id

    def _atlas_check_cari_partner(self):
        for line in self.filtered('account_id.atlas_partner_id'):
            account_partner = line.account_id.atlas_partner_id
            if line.partner_id.commercial_partner_id != account_partner:
                raise UserError(self.env._(
                    '%(account)s hesabı "%(cari)s" carisine aittir; satırdaki cari "%(line_partner)s" olamaz.',
                    account=line.account_id.display_name,
                    cari=account_partner.display_name,
                    line_partner=line.partner_id.display_name or '-',
                ))
