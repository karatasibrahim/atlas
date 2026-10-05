import base64

from odoo import api, models
from odoo.exceptions import UserError


class AtlasBelgeBagla(models.TransientModel):
    _inherit = 'atlas.belge.bagla'

    @api.model
    def _bagli_modeller(self):
        return super()._bagli_modeller() + ['atlas.imza.talep']


class AtlasBelge(models.Model):
    _inherit = 'atlas.belge'

    def action_belge_imza(self):
        self.ensure_one()
        if not (self.mimetype or '').endswith('pdf'):
            raise UserError(self.env._('Yalnız PDF belgeler imzaya gönderilebilir.'))
        talep = self.env['atlas.imza.talep'].create({'konu': self.name, 'dosya': base64.b64encode(self.dosya.content).decode(),
                                                     'dosya_adi': self.dosya_adi or self.name})
        self.message_post(body=self.env._('İmza talebi oluşturuldu: %s', talep.name))
        return self._kayit_ac(talep, self.env._('İmza Talebi'))
