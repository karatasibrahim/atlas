"""Belge bazında TCMB kur tipi (döviz alış / satış, efektif alış / satış).

Odoo tek kur tutar. Atlas TCMB'nin dört kurunu da kur kaydında saklar; faturada seçilen kur tipine göre
belgenin kuru o tipten hesaplanır (Odoo'daki gibi işlem tarihinden önceki son bülten).
"""
from odoo import api, fields, models

from .res_company import TCMB_RATE_TYPE_SELECTION
from .res_currency import TCMB_RATE_TYPES


class ResPartner(models.Model):
    _inherit = 'res.partner'

    atlas_satis_kur_tipi = fields.Selection(TCMB_RATE_TYPE_SELECTION, string='Satış Belgesi Kur Tipi',
                                            help='Boşsa şirket varsayılanı kullanılır.')
    atlas_alis_kur_tipi = fields.Selection(TCMB_RATE_TYPE_SELECTION, string='Alış Belgesi Kur Tipi',
                                           help='Boşsa şirket varsayılanı kullanılır.')

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + ['atlas_satis_kur_tipi', 'atlas_alis_kur_tipi']


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_kur_tipi = fields.Selection(
        TCMB_RATE_TYPE_SELECTION, string='TCMB Kur Tipi',
        compute='_compute_atlas_kur_tipi', store=True, readonly=False, precompute=True,
        help='Dövizli belgede kullanılacak TCMB kuru. Cariden veya şirket ayarından gelir.')

    @api.depends('partner_id', 'move_type', 'company_id')
    def _compute_atlas_kur_tipi(self):
        for move in self:
            partner = move.partner_id.commercial_partner_id
            if move.is_sale_document(include_receipts=True):
                kur = partner.atlas_satis_kur_tipi
            elif move.is_purchase_document(include_receipts=True):
                kur = partner.atlas_alis_kur_tipi
            else:
                kur = False
            move.atlas_kur_tipi = kur or move.company_id.atlas_tcmb_rate_type

    def _get_expected_currency_rate_at(self, date):
        rate = self._atlas_tcmb_rate_at(date)
        return rate or super()._get_expected_currency_rate_at(date)

    def _atlas_tcmb_rate_at(self, date):
        """Seçili kur tipinde, tarihten önceki son TCMB bülteninden şirket para birimi → belge para birimi oranı."""
        self.ensure_one()
        if not (self.atlas_kur_tipi and self.currency_id and self.currency_id != self.company_currency_id
                and self.company_currency_id.name == 'TRY' and date):
            return False
        field_name = TCMB_RATE_TYPES[self.atlas_kur_tipi][1]
        rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', self.currency_id.id),
            ('company_id', 'in', (self.company_id.root_id.id, False)),
            ('name', '<', date),
            (field_name, '>', 0),
        ], order='name desc', limit=1)
        return 1.0 / rate[field_name] if rate else False

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'invoice_date', 'taxable_supply_date', 'atlas_kur_tipi')
    def _compute_expected_currency_rate(self):
        return super()._compute_expected_currency_rate()

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'invoice_date', 'taxable_supply_date', 'atlas_kur_tipi')
    def _compute_invoice_currency_rate(self):
        return super()._compute_invoice_currency_rate()
