import base64
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


def _kullanici(env, value):
    """Arama değeri: kullanıcı kimliği (kayıt kuralı) veya True (geçerli kullanıcı)."""
    if isinstance(value, bool) or value is None:
        return env.user
    if not isinstance(value, int):
        value = next(iter(value), True)
        if isinstance(value, bool):
            return env.user
    return env['res.users'].browse(value)


class AtlasBelgeKlasor(models.Model):
    _name = 'atlas.belge.klasor'
    _description = 'Belge Klasörü'
    _parent_store = True
    _order = 'complete_name'
    _rec_name = 'complete_name'

    name = fields.Char(string='Klasör', required=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True, recursive=True)
    parent_id = fields.Many2one('atlas.belge.klasor', string='Üst Klasör', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('atlas.belge.klasor', 'parent_id', string='Alt Klasörler')
    company_id = fields.Many2one('res.company', string='Şirket')
    aciklama = fields.Text(string='Açıklama')
    color = fields.Integer(string='Renk')
    okuma_grup_ids = fields.Many2many('res.groups', 'atlas_klasor_okuma_grup_rel', string='Okuyabilen Gruplar')
    okuma_user_ids = fields.Many2many('res.users', 'atlas_klasor_okuma_user_rel', string='Okuyabilen Kullanıcılar')
    yazma_grup_ids = fields.Many2many('res.groups', 'atlas_klasor_yazma_grup_rel', string='Yazabilen Gruplar')
    yazma_user_ids = fields.Many2many('res.users', 'atlas_klasor_yazma_user_rel', string='Yazabilen Kullanıcılar')
    erisim_okuma = fields.Boolean(compute='_compute_erisim', search='_search_erisim_okuma', string='Okuyabilir')
    erisim_yazma = fields.Boolean(compute='_compute_erisim', search='_search_erisim_yazma', string='Yazabilir')
    # Kayıt kuralları için: ('okuma_kullanici_id', '=', user.id) → bu kullanıcının okuyabildiği klasörler
    okuma_kullanici_id = fields.Many2one('res.users', compute='_compute_erisim', search='_search_okuma_kullanici')
    yazma_kullanici_id = fields.Many2one('res.users', compute='_compute_erisim', search='_search_yazma_kullanici')
    belge_ids = fields.One2many('atlas.belge', 'klasor_id', string='Belgeler')
    belge_sayisi = fields.Integer(compute='_compute_belge_sayisi', string='Belge')

    _cycle_check = models.Constraint('CHECK(id != parent_id)', 'Klasör kendisinin alt klasörü olamaz.')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for k in self:
            k.complete_name = f'{k.parent_id.complete_name} / {k.name}' if k.parent_id else k.name

    def _compute_belge_sayisi(self):
        data = dict(self.env['atlas.belge']._read_group([('klasor_id', 'in', self.ids)], ['klasor_id'], ['__count']))
        for k in self:
            k.belge_sayisi = data.get(k, 0)

    def _etkin(self, tip):
        """Kendi kısıtı yoksa üst klasörün kısıtı geçerlidir: (gruplar, kullanıcılar)."""
        self.ensure_one()
        k = self.sudo()
        while k:
            gruplar, kullanicilar = (k.okuma_grup_ids, k.okuma_user_ids) if tip == 'okuma' else (k.yazma_grup_ids, k.yazma_user_ids)
            if gruplar or kullanicilar:
                return gruplar, kullanicilar
            k = k.parent_id
        return None

    def _izinli(self, user, tip):
        self.ensure_one()
        if user._is_superuser() or user.has_group('atlas_belgeler.group_belge_manager'):
            return True
        kural = self._etkin(tip)
        if tip == 'yazma' and kural is None:
            kural = self._etkin('okuma')  # yazma kısıtı yoksa okuyan yazabilir
        if kural is None:
            return True
        gruplar, kullanicilar = kural
        return user in kullanicilar or bool(gruplar & user.sudo().all_group_ids)

    def _compute_erisim(self):
        for k in self:
            k.erisim_okuma = k._izinli(self.env.user, 'okuma')
            k.erisim_yazma = k._izinli(self.env.user, 'yazma')
            k.okuma_kullanici_id = self.env.user if k.erisim_okuma else False
            k.yazma_kullanici_id = self.env.user if k.erisim_yazma else False

    def _search_erisim(self, tip, operator, value):
        user = _kullanici(self.env, value)
        ids = [k.id for k in self.sudo().with_context(active_test=False).search([]) if k._izinli(user, tip)]
        olumlu = operator in ('=', 'in')
        return [('id', 'in' if olumlu else 'not in', ids)]

    def _search_erisim_okuma(self, operator, value):
        return self._search_erisim('okuma', operator, value)

    def _search_erisim_yazma(self, operator, value):
        return self._search_erisim('yazma', operator, value)

    def _search_okuma_kullanici(self, operator, value):
        return self._search_erisim('okuma', 'in', value)

    def _search_yazma_kullanici(self, operator, value):
        return self._search_erisim('yazma', 'in', value)

    def action_belgeler(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_belgeler.action_atlas_belge')
        action['context'] = {'searchpanel_default_klasor_id': self.id, 'default_klasor_id': self.id}
        return action


class AtlasBelgeEtiket(models.Model):
    _name = 'atlas.belge.etiket'
    _description = 'Belge Etiketi'
    _order = 'name'

    name = fields.Char(string='Etiket', required=True)
    color = fields.Integer(string='Renk')


class AtlasBelge(models.Model):
    _name = 'atlas.belge'
    _description = 'Belge'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date desc, id desc'

    name = fields.Char(string='Belge Adı', required=True, tracking=True)
    tip = fields.Selection([('dosya', 'Dosya'), ('url', 'Bağlantı')], string='Tür', default='dosya', required=True)
    dosya = fields.Binary(string='Dosya', attachment=True)
    dosya_adi = fields.Char(string='Dosya Adı')
    url = fields.Char(string='Bağlantı')
    mimetype = fields.Char(string='Dosya Türü', compute='_compute_dosya_bilgi', store=True)
    boyut = fields.Integer(string='Boyut (bayt)', compute='_compute_dosya_bilgi', store=True)
    aciklama = fields.Text(string='Açıklama')
    klasor_id = fields.Many2one('atlas.belge.klasor', string='Klasör', required=True, index=True, tracking=True)
    etiket_ids = fields.Many2many('atlas.belge.etiket', string='Etiketler')
    owner_id = fields.Many2one('res.users', string='Sahibi', default=lambda self: self.env.user, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Cari', tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    res_model = fields.Char(string='İlgili Model', index=True)
    res_id = fields.Many2oneReference(string='İlgili Kayıt No', model_field='res_model')
    kaynak_ek_id = fields.Many2one('ir.attachment', string='Kaynak Ek', index='btree_not_null', ondelete='set null', copy=False)
    kilitleyen_id = fields.Many2one('res.users', string='Kilitleyen', tracking=True, copy=False)
    aktif = fields.Boolean(string='Aktif', default=True)
    surum = fields.Integer(string='Sürüm', default=1, copy=False)
    surum_ids = fields.One2many('atlas.belge.surum', 'belge_id', string='Önceki Sürümler', copy=False)
    ilgili_kayit = fields.Char(string='İlgili Kayıt', compute='_compute_ilgili_kayit')
    resim_mi = fields.Boolean(compute='_compute_dosya_bilgi', store=True)

    @api.depends('dosya', 'dosya_adi')
    def _compute_dosya_bilgi(self):
        import mimetypes
        for belge in self:
            belge.mimetype = mimetypes.guess_type(belge.dosya_adi or belge.name or '')[0] or (
                'application/octet-stream' if belge.dosya else False)
            belge.boyut = len(belge.dosya.content) if belge.dosya else 0
            belge.resim_mi = bool(belge.mimetype and belge.mimetype.startswith('image/'))

    @api.depends('res_model', 'res_id')
    def _compute_ilgili_kayit(self):
        for belge in self:
            if belge.res_model and belge.res_id and belge.res_model in self.env:
                kayit = self.env[belge.res_model].sudo().browse(belge.res_id).exists()
                belge.ilgili_kayit = kayit.display_name if kayit else ''
            else:
                belge.ilgili_kayit = ''

    @api.onchange('dosya_adi')
    def _onchange_dosya_adi(self):
        if self.dosya_adi and not self.name:
            self.name = self.dosya_adi

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = vals.get('dosya_adi') or self.env._('Belge')
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda b: b.kilitleyen_id and b.kilitleyen_id != self.env.user) and \
                set(vals) - {'kilitleyen_id', 'etiket_ids', 'aktif'}:
            raise UserError(self.env._('Belge başka bir kullanıcı tarafından kilitlenmiş.'))
        return super().write(vals)

    def action_kilitle(self):
        for belge in self:
            if belge.kilitleyen_id and belge.kilitleyen_id != self.env.user:
                raise UserError(self.env._('%s zaten kilitli.', belge.name))
            belge.kilitleyen_id = False if belge.kilitleyen_id else self.env.user
        return True

    def yeni_surum(self, dosya, dosya_adi=None):
        """Mevcut dosyayı sürüm geçmişine alır, yeni içeriği yükler. dosya: base64 metin veya bayt."""
        self.ensure_one()
        if isinstance(dosya, bytes):
            dosya = base64.b64encode(dosya).decode()
        self.env['atlas.belge.surum'].create({'belge_id': self.id, 'surum': self.surum, 'dosya_adi': self.dosya_adi or self.name,
                                             'dosya': base64.b64encode(self.dosya.content).decode() if self.dosya else False})
        self.write({'dosya': dosya, 'dosya_adi': dosya_adi or self.dosya_adi, 'surum': self.surum + 1})
        self.message_post(body=self.env._('Yeni sürüm yüklendi (v%s).', self.surum))
        return True

    def action_ilgili_kayit(self):
        self.ensure_one()
        if not self.ilgili_kayit:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}

    def action_paylas(self):
        paylasim = self.env['atlas.belge.paylasim'].create({'belge_ids': [(6, 0, self.ids)]})
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.belge.paylasim', 'res_id': paylasim.id,
                'view_mode': 'form', 'target': 'new'}


class AtlasBelgeSurum(models.Model):
    _name = 'atlas.belge.surum'
    _description = 'Belge Sürümü'
    _order = 'surum desc'

    belge_id = fields.Many2one('atlas.belge', required=True, ondelete='cascade', index=True)
    surum = fields.Integer(string='Sürüm')
    dosya = fields.Binary(string='Dosya', attachment=True)
    dosya_adi = fields.Char(string='Dosya Adı')


class AtlasBelgeKural(models.Model):
    """Ek dosyaları otomatik belgeye çevirir (ör. alış faturası ekleri → Muhasebe / Gelen Faturalar)."""
    _name = 'atlas.belge.kural'
    _description = 'Belge Toplama Kuralı'

    name = fields.Char(string='Kural', required=True)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(related='model_id.model', store=True, string='Model Adı')
    alan_adi = fields.Char(string='Ek Alanı', help='Boşsa yalnızca sohbetteki (chatter) ekler; doluysa bu ikili alanın dosyası da.')
    klasor_id = fields.Many2one('atlas.belge.klasor', string='Klasör', required=True)
    etiket_ids = fields.Many2many('atlas.belge.etiket', string='Etiketler')

    @api.model
    def _atlas_varsayilan_kurallar(self):
        """Muhasebe kuruluysa alış faturası ekleri 'Gelen Faturalar' klasörüne toplanır."""
        model = self.env['ir.model']._get('account.move')
        klasor = self.env.ref('atlas_belgeler.klasor_gelen_fatura', raise_if_not_found=False)
        if model and klasor and not self.with_context(active_test=False).search_count([('model_id', '=', model.id)]):
            self.create({'name': 'Fatura ekleri', 'model_id': model.id, 'klasor_id': klasor.id,
                         'etiket_ids': [(6, 0, self.env.ref('atlas_belgeler.etiket_fatura').ids)]})


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        ekler = super().create(vals_list)
        ekler._atlas_belge_kural_uygula()
        return ekler

    def _atlas_belge_kural_uygula(self):
        modeller = set(self.mapped('res_model')) - {False, 'atlas.belge', 'atlas.belge.surum', 'atlas.belge.yukle', 'mail.compose.message'}
        if not modeller:
            return
        kurallar = self.env['atlas.belge.kural'].sudo().search([('model', 'in', list(modeller))])
        if not kurallar:
            return
        Belge = self.env['atlas.belge'].sudo()
        for ek in self.filtered(lambda a: a.res_model in kurallar.mapped('model') and a.res_id and a.type == 'binary'):
            for kural in kurallar.filtered(lambda k: k.model == ek.res_model):
                if ek.res_field and ek.res_field != kural.alan_adi:
                    continue
                if Belge.search_count([('kaynak_ek_id', '=', ek.id)]):
                    continue
                kayit = self.env[ek.res_model].sudo().browse(ek.res_id)
                partner = kayit.partner_id if 'partner_id' in kayit._fields else False
                Belge.create({'name': ek.name, 'dosya_adi': ek.name, 'dosya': base64.b64encode(ek.sudo().raw.content).decode(),
                              'kaynak_ek_id': ek.id, 'res_model': ek.res_model, 'res_id': ek.res_id, 'klasor_id': kural.klasor_id.id,
                              'etiket_ids': [(6, 0, kural.etiket_ids.ids)], 'partner_id': partner.id if partner else False})


class AtlasBelgePaylasim(models.Model):
    _name = 'atlas.belge.paylasim'
    _description = 'Belge Paylaşım Bağlantısı'
    _order = 'id desc'

    name = fields.Char(string='Açıklama', default=lambda self: self.env._('Belge paylaşımı'))
    belge_ids = fields.Many2many('atlas.belge', string='Belgeler', required=True)
    token = fields.Char(string='Anahtar', required=True, copy=False, default=lambda self: secrets.token_urlsafe(24), index=True)
    son_tarih = fields.Date(string='Son Geçerlilik', default=lambda self: fields.Date.context_today(self) + timedelta(days=30))
    indirme_sayisi = fields.Integer(string='İndirme', readonly=True)
    url = fields.Char(string='Bağlantı', compute='_compute_url')

    _token_uniq = models.UniqueIndex('(token)')

    def _compute_url(self):
        # website kuruluyken get_base_url tekil kayıt ister
        for p in self:
            p.url = f'{p.get_base_url()}/belge/paylas/{p.token}'

    def _gecerli(self):
        self.ensure_one()
        return not self.son_tarih or self.son_tarih >= fields.Date.context_today(self)

    @api.constrains('son_tarih')
    def _check_son_tarih(self):
        for p in self:
            if p.son_tarih and p.son_tarih < fields.Date.context_today(p):
                raise ValidationError(self.env._('Son geçerlilik tarihi geçmişte olamaz.'))
