from odoo import api, models
from odoo.fields import Command


class AtlasSeri(models.Model):
    _inherit = 'atlas.seri'

    @api.model
    def _number_sources(self):
        return super()._number_sources() + [('stock.picking', 'atlas_irsaliye_no')]

    @api.model
    def _atlas_create_irsaliye_series(self, company):
        belge = self.env.ref('atlas_stok.belge_irsaliye')
        if not self.search_count([('company_id', '=', company.id)]) \
                or self.search_count([('company_id', '=', company.id), ('belge_turu_ids', 'in', belge.ids)]):
            return self
        return self.create({
            'name': 'Sevk İrsaliyeleri (e-İrsaliye)',
            'sequence': 15,
            'company_id': company.id,
            'on_ek': 'IRS',
            'yil_ekle': True,
            'hane': 9,
            'varsayilan': True,
            'belge_turu_ids': [Command.set(belge.ids)],
        })

    @api.model
    def _atlas_create_default_series(self, company):
        series = super()._atlas_create_default_series(company)
        self._atlas_create_irsaliye_series(company)
        return series
