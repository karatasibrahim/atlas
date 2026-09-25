from odoo import api, models
from odoo.fields import Command


class AtlasSeri(models.Model):
    _inherit = 'atlas.seri'

    @api.model
    def _atlas_create_cek_series(self, company):
        belge = self.env.ref('atlas_cek_senet.belge_cek_senet')
        if not self.search_count([('company_id', '=', company.id)]) \
                or self.search_count([('company_id', '=', company.id), ('belge_turu_ids', 'in', belge.ids)]):
            return self
        return self.create({
            'name': 'Çek / Senet Bordroları',
            'sequence': 110,
            'company_id': company.id,
            'on_ek': 'CSB',
            'yil_ekle': True,
            'hane': 6,
            'varsayilan': True,
            'belge_turu_ids': [Command.set(belge.ids)],
        })

    @api.model
    def _atlas_create_default_series(self, company):
        series = super()._atlas_create_default_series(company)
        self._atlas_create_cek_series(company)
        return series
