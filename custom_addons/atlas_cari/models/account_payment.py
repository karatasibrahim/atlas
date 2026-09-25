from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        for payment in self.filtered(lambda p: p.state == 'draft'
                                     and p.partner_type in ('customer', 'supplier')
                                     and p.commercial_partner_id
                                     and p.company_id.account_fiscal_country_id.code == 'TR'):
            needed = 'alici' if payment.partner_type == 'customer' else 'satici'
            if payment.commercial_partner_id._atlas_add_cari_tipi(needed):
                payment._compute_destination_account_id()
        return super().action_post()
