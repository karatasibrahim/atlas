from odoo import fields, models


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    atlas_source = fields.Selection(
        [('manual', 'Manuel'), ('tcmb', 'TCMB')],
        string='Kaynak',
        default='manual',
        readonly=True,
    )
    atlas_bulletin_date = fields.Date(string='TCMB Bülten Tarihi', readonly=True)
    atlas_forex_buying = fields.Float(string='Döviz Alış', digits=(12, 4), readonly=True)
    atlas_forex_selling = fields.Float(string='Döviz Satış', digits=(12, 4), readonly=True)
    atlas_banknote_buying = fields.Float(string='Efektif Alış', digits=(12, 4), readonly=True)
    atlas_banknote_selling = fields.Float(string='Efektif Satış', digits=(12, 4), readonly=True)
