from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Command

from ..models.makale import YETKILER


class AtlasBilgiPaylas(models.TransientModel):
    """Paylaş penceresi: şirket içi erişim, üyeler, davet ve herkese açık bağlantı."""
    _name = 'atlas.bilgi.paylas'
    _description = 'Bilgi Makalesi Paylaş'

    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade')
    ic_yetki = fields.Selection(YETKILER, string='Şirket içi erişim', compute='_compute_makale', readonly=False, store=True)
    yetki_kaynak_id = fields.Many2one(related='makale_id.yetki_kaynak_id', string='Erişimin geldiği makale')
    uye_ids = fields.One2many(related='makale_id.uye_ids', readonly=False)
    uyeler_bagimsiz = fields.Boolean(related='makale_id.uyeler_bagimsiz', readonly=False)
    herkese_acik = fields.Boolean(string='Bağlantıyla herkese açık', compute='_compute_makale', readonly=False, store=True)
    paylasim_url = fields.Char(related='makale_id.paylasim_url')
    davet_partner_ids = fields.Many2many('res.partner', string='Davet edilecekler')
    davet_yetki = fields.Selection(YETKILER[:2], string='Yetki', default='write')
    mesaj = fields.Text(string='Mesaj')

    @api.depends('makale_id')
    def _compute_makale(self):
        for w in self:
            w.ic_yetki = w.makale_id.etkin_yetki
            w.herkese_acik = w.makale_id.herkese_acik

    def _kontrol(self):
        if self.makale_id.kullanici_yetkisi != 'write':
            raise AccessError(self.env._('Bu makaleyi paylaşma yetkiniz yok.'))

    def action_kaydet(self):
        self.ensure_one()
        self._kontrol()
        m = self.makale_id
        vals = {}
        if self.ic_yetki != m.etkin_yetki:
            vals['ic_yetki'] = self.ic_yetki
        if self.herkese_acik != m.herkese_acik:
            vals['herkese_acik'] = self.herkese_acik
        if vals:
            m.with_context(atlas_bilgi_sessiz=True).write(vals)
        if self.herkese_acik:
            m._paylasim_anahtari()
        if self.davet_partner_ids:
            self.action_davet()
        return {'type': 'ir.actions.act_window_close'}

    def action_davet(self):
        self.ensure_one()
        self._kontrol()
        m = self.makale_id
        mevcut = {u.partner_id.id: u for u in m.uye_ids}
        komutlar = []
        for p in self.davet_partner_ids:
            if p.id in mevcut:
                komutlar.append(Command.update(mevcut[p.id].id, {'yetki': self.davet_yetki}))
            else:
                komutlar.append(Command.create({'partner_id': p.id, 'yetki': self.davet_yetki}))
        m.with_context(atlas_bilgi_sessiz=True).write({'uye_ids': komutlar})
        govde = self.env._('%(kim)s sizi "%(makale)s" makalesine davet etti.', kim=self.env.user.name, makale=m.name)
        if self.mesaj:
            govde += '\n\n' + self.mesaj
        m.message_post(body=govde, partner_ids=self.davet_partner_ids.ids, message_type='comment', subtype_xmlid='mail.mt_comment')
        self.davet_partner_ids = False
        self.mesaj = False
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Paylaş')}
