from odoo import api, models
from odoo.exceptions import UserError


class AtlasBelgeBagla(models.TransientModel):
    _inherit = 'atlas.belge.bagla'

    @api.model
    def _bagli_modeller(self):
        return super()._bagli_modeller() + ['hr.expense']


class AtlasBelge(models.Model):
    _inherit = 'atlas.belge'

    def action_belge_masraf(self):
        self._bagli_degil()
        calisan = self.env.user.employee_id
        if not calisan:
            raise UserError(self.env._('Kullanıcınıza bağlı çalışan kaydı yok.'))
        masraflar = self.env['hr.expense']
        for belge in self:
            masraf = masraflar.create({'name': belge.name, 'employee_id': calisan.id})
            belge._kayda_ekle(masraf)
            if hasattr(masraf, '_atlas_belgeden_doldur'):
                masraf._atlas_belgeden_doldur()
            masraflar |= masraf
        return self._kayit_ac(masraflar, self.env._('Masraflar'))
