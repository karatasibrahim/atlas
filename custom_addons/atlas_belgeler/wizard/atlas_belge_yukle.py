import base64

from odoo import fields, models
from odoo.exceptions import UserError


class AtlasBelgeYukle(models.TransientModel):
    _name = 'atlas.belge.yukle'
    _description = 'Toplu Belge Yükleme'

    klasor_id = fields.Many2one('atlas.belge.klasor', string='Klasör', required=True,
                                default=lambda self: self.env.context.get('default_klasor_id'))
    etiket_ids = fields.Many2many('atlas.belge.etiket', string='Etiketler')
    partner_id = fields.Many2one('res.partner', string='Cari')
    ek_ids = fields.Many2many('ir.attachment', string='Dosyalar')

    def action_yukle(self):
        self.ensure_one()
        if not self.ek_ids:
            raise UserError(self.env._('Yüklenecek dosya seçin.'))
        if not self.klasor_id._izinli(self.env.user, 'yazma'):
            raise UserError(self.env._('Bu klasöre yazma yetkiniz yok.'))
        Belge = self.env['atlas.belge']
        belgeler = Belge
        for ek in self.ek_ids:
            belgeler |= Belge.create({'name': ek.name, 'dosya_adi': ek.name, 'dosya': base64.b64encode(ek.raw.content).decode(),
                                      'klasor_id': self.klasor_id.id, 'etiket_ids': [(6, 0, self.etiket_ids.ids)],
                                      'partner_id': self.partner_id.id})
        self.ek_ids.sudo().unlink()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.belge', 'view_mode': 'kanban,list,form',
                'domain': [('id', 'in', belgeler.ids)], 'name': self.env._('Yüklenen Belgeler')}
