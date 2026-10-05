from odoo import api, fields, models
from odoo.exceptions import UserError


class AtlasBilgiTasi(models.TransientModel):
    _name = 'atlas.bilgi.tasi'
    _description = 'Bilgi Makalesi Taşı'

    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade')
    hedef = fields.Selection([('makale', 'Başka bir makalenin altına'), ('calisma', 'Çalışma Alanı (kök)'), ('ozel', 'Özel (kök)')],
                             string='Hedef', default='makale', required=True)
    ust_id = fields.Many2one('atlas.bilgi.makale', string='Üst Makale',
                             domain="[('id', '!=', makale_id), ('oge_mi', '=', False), ('sablon_mi', '=', False)]")

    @api.onchange('makale_id')
    def _onchange_makale(self):
        return {'domain': {'ust_id': [('id', 'not child_of', self.makale_id.id), ('oge_mi', '=', False), ('sablon_mi', '=', False)]}}

    def action_tasi(self):
        self.ensure_one()
        if self.hedef == 'makale':
            if not self.ust_id:
                raise UserError(self.env._('Üst makale seçin.'))
            self.env['atlas.bilgi.makale'].makale_tasi(self.makale_id.id, self.ust_id.id)
        else:
            self.env['atlas.bilgi.makale'].makale_tasi(self.makale_id.id, False, self.hedef)
        return self.makale_id.action_ac()
