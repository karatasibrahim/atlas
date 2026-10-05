from odoo import api, fields, models
from odoo.exceptions import UserError


class AtlasStudioOnayKural(models.Model):
    """Studio düğmesine eklenen onay adımı (Enterprise Studio 'Add an approval step')."""
    _name = 'atlas.studio.onay.kural'
    _description = 'Studio Onay Kuralı'
    _order = 'anahtar, sira, id'

    anahtar = fields.Char(string='Düğme Anahtarı', required=True, index=True, help='model:hedef (ör. x_talep:action_confirm)')
    model = fields.Char(string='Model', required=True)
    hedef = fields.Char(string='Hedef', required=True, help='metot:<ad> ya da eylem:<id>')
    sira = fields.Integer(string='Sıra', default=10)
    grup_id = fields.Many2one('res.groups', string='Onaylayan Grup')
    kullanici_id = fields.Many2one('res.users', string='Onaylayan Kullanıcı')
    aciklama = fields.Char(string='Açıklama')
    bildirim = fields.Boolean(string='Onaylayıcıya Aktivite', default=True)
    active = fields.Boolean(default=True)

    def _onaylayabilir(self, kullanici):
        self.ensure_one()
        if self.kullanici_id:
            return kullanici == self.kullanici_id
        return not self.grup_id or self.grup_id in kullanici.all_group_ids

    def _onaylayicilar(self):
        self.ensure_one()
        if self.kullanici_id:
            return self.kullanici_id
        return self.grup_id.all_user_ids if self.grup_id else self.env['res.users']


class AtlasStudioOnayTalep(models.Model):
    _name = 'atlas.studio.onay.talep'
    _description = 'Studio Onayı'
    _order = 'id desc'

    kural_id = fields.Many2one('atlas.studio.onay.kural', string='Kural', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='kural_id.model', store=True)
    res_id = fields.Integer(string='Kayıt', required=True, index=True)
    kayit_adi = fields.Char(string='Kayıt Adı')
    durum = fields.Selection([('bekliyor', 'Bekliyor'), ('onaylandi', 'Onaylandı'), ('reddedildi', 'Reddedildi')], string='Durum',
                             default='bekliyor', required=True)
    isteyen_id = fields.Many2one('res.users', string='İsteyen', default=lambda self: self.env.user)
    onaylayan_id = fields.Many2one('res.users', string='Onaylayan')
    tarih = fields.Datetime(string='Karar Tarihi')

    def _karar(self, durum):
        for t in self:
            if not t.kural_id._onaylayabilir(self.env.user):
                raise UserError(self.env._('Bu onayı vermeye yetkiniz yok.'))
            t.sudo().write({'durum': durum, 'onaylayan_id': self.env.uid, 'tarih': fields.Datetime.now()})
            kayit = self.env[t.model].browse(t.res_id).exists()
            if kayit and hasattr(kayit, 'message_post'):
                kayit.message_post(body=self.env._('%(kural)s: %(durum)s (%(kim)s)', kural=t.kural_id.aciklama or t.kural_id.hedef,
                                                   durum=dict(self._fields['durum'].selection)[durum], kim=self.env.user.name))

    def action_onayla(self):
        self._karar('onaylandi')

    def action_reddet(self):
        self._karar('reddedildi')

    def action_kayit(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.model, 'res_id': self.res_id, 'view_mode': 'form'}


class Base(models.AbstractModel):
    _inherit = 'base'

    def atlas_studio_onayli_calistir(self):
        """Onay adımlı Studio düğmesi: tüm adımlar onaylıysa hedefi çalıştırır, değilse onay ister.
        Düğmenin context'inde 'atlas_studio_onay' = kural anahtarı bulunur."""
        anahtar = self.env.context.get('atlas_studio_onay')
        kurallar = self.env['atlas.studio.onay.kural'].sudo().search([('anahtar', '=', anahtar)], order='sira, id')
        if not kurallar:
            raise UserError(self.env._('Onay kuralı bulunamadı.'))
        Talep = self.env['atlas.studio.onay.talep'].sudo()
        eksik = []
        for kayit in self:
            for kural in kurallar:
                onay = Talep.search([('kural_id', '=', kural.id), ('res_id', '=', kayit.id)], order='id desc', limit=1)
                if onay.durum == 'onaylandi':
                    continue
                if onay.durum == 'reddedildi':
                    raise UserError(self.env._('Bu işlem reddedildi: %s', kural.aciklama or kural.hedef))
                if kural._onaylayabilir(self.env.user):
                    # Onaylama yetkisi olan kişinin tıklaması onay sayılır (Enterprise davranışı)
                    (onay or Talep.create({'kural_id': kural.id, 'res_id': kayit.id, 'kayit_adi': kayit.display_name})).write(
                        {'durum': 'onaylandi', 'onaylayan_id': self.env.uid, 'tarih': fields.Datetime.now()})
                    continue
                if not onay:
                    onay = Talep.create({'kural_id': kural.id, 'res_id': kayit.id, 'kayit_adi': kayit.display_name})
                    if kural.bildirim and hasattr(kayit, 'activity_schedule'):
                        for u in kural._onaylayicilar()[:10]:
                            kayit.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=u.id,
                                                           summary=self.env._('Onay bekleniyor: %s', kural.aciklama or kural.hedef))
                eksik.append(kural.aciklama or (kural.grup_id.display_name or kural.kullanici_id.name))
        if eksik:
            raise UserError(self.env._('Bu işlem için onay gerekiyor: %s. Onay isteği gönderildi.', ', '.join(dict.fromkeys(eksik))))
        hedef = kurallar[0].hedef
        tur, _, ad = hedef.partition(':')
        if tur == 'metot':
            if ad.startswith('_') or not hasattr(self, ad):
                raise UserError(self.env._('Geçersiz düğme metodu: %s', ad))
            return getattr(self, ad)()
        eylem = self.env['ir.actions.server'].browse(int(ad))
        return eylem.with_context(active_model=self._name, active_ids=self.ids, active_id=self[:1].id).run()


class AtlasStudio(models.AbstractModel):
    _inherit = 'atlas.studio'

    @api.model
    def onay_kurallari(self, model, hedef):
        self._yetki()
        anahtar = f'{model}:{hedef}'
        return [{'id': k.id, 'grup': [k.grup_id.id, k.grup_id.display_name] if k.grup_id else False,
                 'kullanici': [k.kullanici_id.id, k.kullanici_id.name] if k.kullanici_id else False,
                 'aciklama': k.aciklama or '', 'bildirim': k.bildirim}
                for k in self.env['atlas.studio.onay.kural'].search([('anahtar', '=', anahtar)])]

    @api.model
    def onay_kurallari_kaydet(self, model, hedef, kurallar):
        """kurallar: [{'grup_id', 'kullanici_id', 'aciklama', 'bildirim'}] — düğmenin onay adımlarını baştan yazar."""
        self._yetki()
        anahtar = f'{model}:{hedef}'
        Kural = self.env['atlas.studio.onay.kural']
        Kural.search([('anahtar', '=', anahtar)]).unlink()
        for i, k in enumerate(kurallar):
            self._xmlid(Kural.create({'anahtar': anahtar, 'model': model, 'hedef': hedef, 'sira': i,
                                      'grup_id': k.get('grup_id') or False, 'kullanici_id': k.get('kullanici_id') or False,
                                      'aciklama': k.get('aciklama') or False, 'bildirim': k.get('bildirim', True)}), 'onay')
        return {'anahtar': anahtar, 'adet': len(kurallar)}
