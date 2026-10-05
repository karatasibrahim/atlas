from odoo import api, models


class AtlasBelgeBagla(models.TransientModel):
    _inherit = 'atlas.belge.bagla'

    @api.model
    def _bagli_modeller(self):
        return super()._bagli_modeller() + ['hr.applicant', 'hr.job']


class AtlasBelge(models.Model):
    _inherit = 'atlas.belge'

    def action_belge_aday(self):
        self._bagli_degil()
        adaylar = self.env['hr.applicant']
        for belge in self:
            ad = (belge.name or '').rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').strip()
            aday = adaylar.create({'partner_name': ad or belge.name})
            belge._kayda_ekle(aday)
            if hasattr(aday, '_atlas_belgeden_doldur'):
                aday._atlas_belgeden_doldur()
            adaylar |= aday
        return self._kayit_ac(adaylar, self.env._('Adaylar'))
