from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class AtlasPlanlamaTekrarWizard(models.TransientModel):
    _name = 'atlas.planlama.tekrar.wizard'
    _description = 'Vardiya Tekrarlama'

    vardiya_ids = fields.Many2many('atlas.planlama.vardiya', string='Vardiyalar', required=True)
    aralik = fields.Selection([('gunluk', 'Her gün'), ('is_gunleri', 'Hafta içi her gün'), ('haftalik', 'Her hafta')],
                              string='Tekrar', required=True, default='is_gunleri')
    adet = fields.Integer(string='Tekrar Sayısı', default=4, required=True)

    def _gun_farklari(self, baslangic_gunu):
        farklar, fark, gun = [], 0, baslangic_gunu
        while len(farklar) < self.adet:
            adim = 7 if self.aralik == 'haftalik' else 1
            fark += adim
            gun = baslangic_gunu + timedelta(days=fark)
            if self.aralik == 'is_gunleri' and gun.weekday() >= 5:
                continue
            farklar.append(fark)
        return farklar

    def action_tekrarla(self):
        self.ensure_one()
        if not 0 < self.adet <= 366:
            raise UserError(self.env._('Tekrar sayısı 1-366 arasında olmalı.'))
        Vardiya = self.env['atlas.planlama.vardiya']
        yeni = Vardiya
        for vardiya in self.vardiya_ids:
            gun = Vardiya._yerel(vardiya.baslangic).date()
            for fark in self._gun_farklari(gun):
                yeni |= vardiya._kopyala(fark)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': self.env._('%s vardiya oluşturuldu (taslak).', len(yeni)), 'type': 'success',
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
