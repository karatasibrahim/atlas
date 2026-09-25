from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        self._atlas_prepare_cari()
        return super()._post(soft=soft)

    def _atlas_prepare_cari(self):
        """Türkiye şirketlerinde faturası kesilen cariye tip/kod/alt hesap verir ve
        faturanın alacak/borç satırını genel 120/320 hesabından carinin alt hesabına taşır."""
        Partner = self.env['res.partner']
        for move in self.filtered(lambda m: m.state == 'draft'
                                  and m.is_invoice(include_receipts=True)
                                  and m.commercial_partner_id
                                  and m.company_id.account_fiscal_country_id.code == 'TR'):
            partner = move.commercial_partner_id
            is_sale = move.is_sale_document(include_receipts=True)
            partner._atlas_add_cari_tipi('alici' if is_sale else 'satici')

            property_field = 'property_account_receivable_id' if is_sale else 'property_account_payable_id'
            target = partner.with_company(move.company_id)[property_field]
            fallback = Partner._fields[property_field].get_company_dependent_fallback(Partner.with_company(move.company_id))
            if not target or target == fallback:
                continue
            move.line_ids.filtered(
                lambda line: line.display_type == 'payment_term' and line.account_id == fallback
            ).account_id = target
