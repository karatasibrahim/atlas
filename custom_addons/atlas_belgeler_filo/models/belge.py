from odoo import api, models


class AtlasBelgeBagla(models.TransientModel):
    _inherit = 'atlas.belge.bagla'

    @api.model
    def _bagli_modeller(self):
        return super()._bagli_modeller() + ['fleet.vehicle']
