import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command, Domain

YETKILER = [('write', 'Düzenleyebilir'), ('read', 'Okuyabilir'), ('none', 'Erişim yok')]
YETKI_SIRA = {'none': 0, 'read': 1, 'write': 2}
# ir.access alan kurallarında kullanılan hesaplanmış alanlar: yetkiyi etkileyen her değişiklikten sonra hemen yazılır,
# böylece aynı işlem içindeki sonraki erişim denetimleri güncel değeri görür
ERISIM_ALANLARI = ['etkin_yetki', 'yetki_kaynak_id', 'yazan_partner_ids', 'okuyan_partner_ids', 'kisitli_partner_ids',
                   'engelli_partner_ids', 'kategori']
COP_GUN = 30


class AtlasBilgiMakale(models.Model):
    """Bilgi bankası makalesi (Enterprise knowledge.article eşleniği).

    Yetki modeli: kök makalenin şirket içi erişimi (ic_yetki) alt makalelere miras kalır; bir alt makale kendi erişimini
    belirleyebilir. Üyeler (atlas.bilgi.uye) kişi bazında erişimi yükseltir ya da engeller; "uyeler_bagimsiz" işaretli
    makale üst makalenin üyelerini devralmaz. Etkin sonuç saklanan alanlarda tutulur ve ir.access alan kurallarıyla uygulanır.
    """
    _name = 'atlas.bilgi.makale'
    _description = 'Bilgi Makalesi'
    _inherit = ['mail.thread', 'html.field.history.mixin']
    _parent_store = True
    _order = 'sira, id'
    _rec_name = 'name'

    name = fields.Char(string='Başlık', default='Adsız', tracking=True)
    body = fields.Html(string='İçerik', sanitize_attributes=False, sanitize_style=True)
    simge = fields.Char(string='Simge', help='Emoji')
    kapak = fields.Image(string='Kapak', max_width=1920, max_height=1080)
    kapak_konum = fields.Float(string='Kapak Konumu', default=50.0, help='Dikey konum (%)')
    tam_genislik = fields.Boolean(string='Tam Genişlik')
    kilitli = fields.Boolean(string='Kilitli', help='Kilitli makalenin içeriği düzenlenemez')
    active = fields.Boolean(default=True)
    sira = fields.Integer(string='Sıra', default=0, index=True)
    ozet = fields.Text(string='Özet')

    parent_id = fields.Many2one('atlas.bilgi.makale', string='Üst Makale', ondelete='cascade', index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('atlas.bilgi.makale', 'parent_id', string='Alt Makaleler', context={'active_test': False})
    alt_ids = fields.One2many('atlas.bilgi.makale', 'parent_id', string='Alt Sayfalar', domain=[('oge_mi', '=', False)])
    oge_ids = fields.One2many('atlas.bilgi.makale', 'parent_id', string='Öğeler', domain=[('oge_mi', '=', True)])
    kok_id = fields.Many2one('atlas.bilgi.makale', string='Kök Makale', compute='_compute_kok', store=True, recursive=True, index=True)
    alt_sayisi = fields.Integer(string='Alt Sayfa Sayısı', compute='_compute_alt_sayisi')

    # yetki
    ic_yetki = fields.Selection(YETKILER, string='Şirket İçi Erişim',
                                help='Boşsa üst makaleden devralınır; kök makalede boş = Düzenleyebilir')
    etkin_yetki = fields.Selection(YETKILER, string='Etkin İç Erişim', compute='_compute_etkin_yetki', store=True, recursive=True)
    yetki_kaynak_id = fields.Many2one('atlas.bilgi.makale', string='Erişimin Geldiği Makale', compute='_compute_etkin_yetki', store=True,
                                      recursive=True)
    uye_ids = fields.One2many('atlas.bilgi.uye', 'makale_id', string='Üyeler', copy=True)
    uyeler_bagimsiz = fields.Boolean(string='Üst Makaleden Bağımsız', help='Üst makalenin üyeleri bu makaleye uygulanmaz')
    yazan_partner_ids = fields.Many2many('res.partner', 'atlas_bilgi_yazan_rel', 'makale_id', 'partner_id', string='Düzenleyen Üyeler',
                                         compute='_compute_uye_erisim', store=True, recursive=True)
    okuyan_partner_ids = fields.Many2many('res.partner', 'atlas_bilgi_okuyan_rel', 'makale_id', 'partner_id', string='Erişen Üyeler',
                                          compute='_compute_uye_erisim', store=True, recursive=True)
    kisitli_partner_ids = fields.Many2many('res.partner', 'atlas_bilgi_kisitli_rel', 'makale_id', 'partner_id', string='Kısıtlı Üyeler',
                                           compute='_compute_uye_erisim', store=True, recursive=True,
                                           help='Okuyabilir ya da erişimi olmayan üyeler (iç erişim onlara uygulanmaz)')
    engelli_partner_ids = fields.Many2many('res.partner', 'atlas_bilgi_engelli_rel', 'makale_id', 'partner_id', string='Engelli Üyeler',
                                           compute='_compute_uye_erisim', store=True, recursive=True)
    kategori = fields.Selection([('calisma', 'Çalışma Alanı'), ('paylasilan', 'Paylaşılan'), ('ozel', 'Özel')], string='Bölüm',
                                compute='_compute_kategori', store=True, recursive=True, index=True)
    kullanici_yetkisi = fields.Selection(YETKILER, string='Benim Yetkim', compute='_compute_kullanici_yetkisi')
    duzenleyebilir = fields.Boolean(compute='_compute_kullanici_yetkisi')

    # favoriler ve izleme
    favori_ids = fields.One2many('atlas.bilgi.favori', 'makale_id', string='Favoriler')
    favori_mi = fields.Boolean(string='Favori', compute='_compute_favori_mi', search='_search_favori_mi')
    favori_sayisi = fields.Integer(string='Favori Sayısı', compute='_compute_favori_sayisi', store=True)
    son_duzenleyen_id = fields.Many2one('res.users', string='Son Düzenleyen', readonly=True, default=lambda self: self.env.user)
    son_duzenleme = fields.Datetime(string='Son Düzenleme', readonly=True, default=fields.Datetime.now)

    # öğeler (veritabanı)
    oge_mi = fields.Boolean(string='Öğe', index=True, help='Üst makalenin öğe listesinde (kanban) gösterilen kayıt')
    asama_id = fields.Many2one('atlas.bilgi.asama', string='Aşama', domain="[('makale_id', '=', parent_id)]",
                               group_expand='_asama_genislet')
    ozellik_tanimi = fields.PropertiesDefinition(string='Öğe Özellikleri')
    ozellikler = fields.Properties(string='Özellikler', definition='parent_id.ozellik_tanimi', copy=True)

    # şablon
    sablon_mi = fields.Boolean(string='Şablon')
    sablon_kategori_id = fields.Many2one('atlas.bilgi.sablon.kategori', string='Şablon Kategorisi')
    sablon_aciklama = fields.Char(string='Şablon Açıklaması')

    # çöp ve paylaşım
    cope_atildi = fields.Boolean(string='Çöpte', index=True)
    silinme_tarihi = fields.Date(string='Kalıcı Silinme Tarihi')
    herkese_acik = fields.Boolean(string='Bağlantıyla Herkese Açık')
    erisim_anahtari = fields.Char(string='Paylaşım Anahtarı', copy=False, groups='base.group_user')
    paylasim_url = fields.Char(string='Paylaşım Bağlantısı', compute='_compute_paylasim_url')

    _sira_index = models.Index('(parent_id, sira)')

    # ------------------------------------------------------------------ hesaplananlar
    @api.depends('parent_id', 'parent_id.kok_id')
    def _compute_kok(self):
        for m in self:
            m.kok_id = m.parent_id.kok_id if m.parent_id else m

    @api.depends('child_ids')
    def _compute_alt_sayisi(self):
        veri = dict(self.env['atlas.bilgi.makale']._read_group([('parent_id', 'in', self.ids), ('oge_mi', '=', False)], ['parent_id'], ['__count']))
        for m in self:
            m.alt_sayisi = veri.get(m, 0)

    @api.depends('ic_yetki', 'parent_id.etkin_yetki', 'parent_id.yetki_kaynak_id')
    def _compute_etkin_yetki(self):
        for m in self:
            if m.ic_yetki or not m.parent_id:
                m.etkin_yetki = m.ic_yetki or 'write'
                m.yetki_kaynak_id = m if m.id else False
            else:
                m.etkin_yetki = m.parent_id.etkin_yetki
                m.yetki_kaynak_id = m.parent_id.yetki_kaynak_id

    def _uye_haritasi(self):
        """{partner_id: yetki} — devralınanlar + kendi üyeleri (kendi üyeleri önceliklidir)."""
        self.ensure_one()
        harita = {}
        if self.parent_id and not self.uyeler_bagimsiz:
            harita.update(self.parent_id._uye_haritasi())
        for u in self.uye_ids:
            harita[u.partner_id.id] = u.yetki
        return harita

    @api.depends('uye_ids.yetki', 'uye_ids.partner_id', 'uyeler_bagimsiz', 'parent_id.yazan_partner_ids', 'parent_id.okuyan_partner_ids',
                 'parent_id.kisitli_partner_ids', 'parent_id.engelli_partner_ids')
    def _compute_uye_erisim(self):
        for m in self:
            harita = m._uye_haritasi()
            m.yazan_partner_ids = [Command.set([p for p, y in harita.items() if y == 'write'])]
            m.okuyan_partner_ids = [Command.set([p for p, y in harita.items() if y in ('read', 'write')])]
            m.kisitli_partner_ids = [Command.set([p for p, y in harita.items() if y in ('read', 'none')])]
            m.engelli_partner_ids = [Command.set([p for p, y in harita.items() if y == 'none'])]

    @api.depends('parent_id.kategori', 'etkin_yetki', 'okuyan_partner_ids')
    def _compute_kategori(self):
        for m in self:
            if m.parent_id:
                m.kategori = m.parent_id.kategori
            elif m.etkin_yetki != 'none':
                m.kategori = 'calisma'
            else:
                m.kategori = 'ozel' if len(m.okuyan_partner_ids) <= 1 else 'paylasilan'

    def _yetki_hesapla(self, partner):
        self.ensure_one()
        harita = self._uye_haritasi()
        if partner.id in harita:
            return harita[partner.id]
        return self.etkin_yetki

    @api.depends_context('uid')
    @api.depends('etkin_yetki', 'yazan_partner_ids', 'okuyan_partner_ids', 'engelli_partner_ids', 'kilitli')
    def _compute_kullanici_yetkisi(self):
        yonetici = self.env.user.has_group('base.group_system')
        for m in self:
            yetki = 'write' if yonetici else m.sudo()._yetki_hesapla(self.env.user.partner_id)
            m.kullanici_yetkisi = yetki
            m.duzenleyebilir = yetki == 'write' and not m.kilitli

    @api.depends_context('uid')
    @api.depends('favori_ids.user_id')
    def _compute_favori_mi(self):
        favoriler = set(self.env['atlas.bilgi.favori'].sudo().search([('user_id', '=', self.env.uid), ('makale_id', 'in', self.ids)]).makale_id.ids)
        for m in self:
            m.favori_mi = m.id in favoriler

    def _search_favori_mi(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            raise NotImplementedError()
        olumlu = (operator in ('=', 'in') and bool(value) and value not in ({False}, [False])) or (operator in ('!=', 'not in') and not value)
        ids = self.env['atlas.bilgi.favori'].sudo().search([('user_id', '=', self.env.uid)]).makale_id.ids
        return [('id', 'in' if olumlu else 'not in', ids)]

    @api.depends('favori_ids')
    def _compute_favori_sayisi(self):
        for m in self:
            m.favori_sayisi = len(m.favori_ids)

    @api.depends('herkese_acik', 'erisim_anahtari')
    def _compute_paylasim_url(self):
        taban = self.env['ir.config_parameter'].sudo().get_str('web.base.url') or ''
        for m in self:
            anahtar = m.sudo().erisim_anahtari
            m.paylasim_url = f'{taban}/bilgi/paylas/{m.id}/{anahtar}' if m.herkese_acik and anahtar else False

    @api.model
    def _asama_genislet(self, asamalar, domain):
        ust = self.env.context.get('default_parent_id')
        if not ust:
            return asamalar
        return self.env['atlas.bilgi.asama'].search([('makale_id', '=', ust)])

    # ------------------------------------------------------------------ CRUD
    def _get_versioned_fields(self):
        return [self.__class__.body.name]

    @api.model_create_multi
    def create(self, vals_list):
        partner = self.env.user.partner_id
        for vals in vals_list:
            if not vals.get('parent_id') and vals.get('ic_yetki') == 'none' and not vals.get('uye_ids'):
                # özel makale: oluşturan tek düzenleyici üyedir
                vals['uye_ids'] = [Command.create({'partner_id': partner.id, 'yetki': 'write'})]
            if vals.get('parent_id') and 'sira' not in vals:
                son = self.search([('parent_id', '=', vals['parent_id'])], order='sira desc', limit=1)
                vals['sira'] = (son.sira or 0) + 1
        makaleler = super().create(vals_list)
        self.flush_model(ERISIM_ALANLARI)
        for m in makaleler:
            if m.parent_id and not m.sudo().parent_id._yetki_hesapla(partner) == 'write' and not self.env.user.has_group('base.group_system'):
                raise AccessError(self.env._('Bu makalenin altına sayfa ekleme yetkiniz yok.'))
        return makaleler

    def write(self, vals):
        icerik = {'name', 'body', 'simge', 'kapak'} & set(vals)
        if icerik and not self.env.context.get('atlas_bilgi_sessiz'):
            kilitli = self.filtered(lambda m: m.kilitli and 'kilitli' not in vals)
            if kilitli and {'body'} & set(vals):
                raise UserError(self.env._('Kilitli makale düzenlenemez: %s', ', '.join(kilitli.mapped('name'))))
            vals = dict(vals, son_duzenleyen_id=self.env.uid, son_duzenleme=fields.Datetime.now())
        if 'parent_id' in vals and vals['parent_id']:
            hedef = self.browse(vals['parent_id'])
            if any(hedef.parent_path and hedef.parent_path.startswith(m.parent_path or '-') for m in self):
                raise ValidationError(self.env._('Makale kendi altına taşınamaz.'))
        sonuc = super().write(vals)
        if {'ic_yetki', 'parent_id', 'uyeler_bagimsiz', 'uye_ids'} & set(vals):
            self.flush_model(ERISIM_ALANLARI)
        return sonuc

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for m, vals in zip(self, vals_list):
            if 'name' not in (default or {}):
                vals['name'] = self.env._('%s (kopya)', m.name)
        return vals_list

    # ------------------------------------------------------------------ eylemler
    def action_favori(self):
        Favori = self.env['atlas.bilgi.favori'].sudo()
        for m in self:
            mevcut = Favori.search([('makale_id', '=', m.id), ('user_id', '=', self.env.uid)])
            if mevcut:
                mevcut.unlink()
            else:
                son = Favori.search([('user_id', '=', self.env.uid)], order='sira desc', limit=1)
                Favori.create({'makale_id': m.id, 'user_id': self.env.uid, 'sira': (son.sira or 0) + 1})
        return True

    def action_kilit(self):
        for m in self:
            m.with_context(atlas_bilgi_sessiz=True).kilitli = not m.kilitli
        return True

    def action_tam_genislik(self):
        for m in self:
            m.with_context(atlas_bilgi_sessiz=True).tam_genislik = not m.tam_genislik
        return True

    def _alt_agac(self):
        return self.with_context(active_test=False).search([('id', 'child_of', self.ids)])

    def action_cope_at(self):
        tumu = self._alt_agac()
        tumu.write({'cope_atildi': True, 'active': False, 'silinme_tarihi': fields.Date.today() + timedelta(days=COP_GUN)})
        self.env['atlas.bilgi.favori'].sudo().search([('makale_id', 'in', tumu.ids)]).unlink()
        return self._ana_eylem()

    def action_geri_yukle(self):
        for m in self:
            tumu = m._alt_agac()
            vals = {'cope_atildi': False, 'active': True, 'silinme_tarihi': False}
            tumu.write(vals)
            if m.parent_id and m.parent_id.cope_atildi:
                m.parent_id = False
        return self.action_ac() if len(self) == 1 else True

    def action_kalici_sil(self):
        self._alt_agac().unlink()
        return True

    def action_ac(self):
        """Makaleyi menüye bağlı pencere eylemiyle açar (üst çubukta Bilgi Bankası uygulaması seçili kalır)."""
        self.ensure_one()
        eylem = self.env['ir.actions.act_window']._for_xml_id('atlas_bilgi.action_atlas_bilgi_tumu')
        eylem.update({
            'res_id': self.id, 'name': self.name, 'target': 'current', 'domain': [],
            'views': [(self.env.ref('atlas_bilgi.view_atlas_bilgi_makale_form').id, 'form')],
            'context': {'form_view_initial_mode': 'edit'},
        })
        return eylem

    def action_kopyala(self):
        self.ensure_one()
        kopya = self.copy({'name': self.env._('%s (kopya)', self.name), 'sira': self.sira + 1})
        for alt in self.child_ids:
            alt._alt_kopya(kopya)
        return kopya.action_ac()

    def _alt_kopya(self, ust):
        kopya = self.copy({'parent_id': ust.id, 'name': self.name})
        for alt in self.child_ids:
            alt._alt_kopya(kopya)
        return kopya

    def action_paylas(self):
        self.ensure_one()
        sihirbaz = self.env['atlas.bilgi.paylas'].create({'makale_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.bilgi.paylas', 'res_id': sihirbaz.id, 'view_mode': 'form',
                'target': 'new', 'name': self.env._('Paylaş')}

    def action_tasi(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.bilgi.tasi', 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Taşı'), 'context': {'default_makale_id': self.id}}

    def action_sablona_cevir(self):
        self.ensure_one()
        self.with_context(atlas_bilgi_sessiz=True).sablon_mi = not self.sablon_mi
        return True

    def action_ogeleri_ac(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'name': self.env._('%s: Öğeler', self.name),
            'views': [(self.env.ref('atlas_bilgi.view_atlas_bilgi_oge_kanban').id, 'kanban'),
                      (self.env.ref('atlas_bilgi.view_atlas_bilgi_oge_list').id, 'list'),
                      (self.env.ref('atlas_bilgi.view_atlas_bilgi_makale_form').id, 'form')],
            'domain': [('parent_id', '=', self.id), ('oge_mi', '=', True)],
            'context': {'default_parent_id': self.id, 'default_oge_mi': True},
        }

    def action_oge_kur(self):
        """Makaleyi öğe listesine (veritabanı) çevirir: varsayılan aşamalar ve bir örnek özellik."""
        self.ensure_one()
        Asama = self.env['atlas.bilgi.asama']
        if not Asama.search_count([('makale_id', '=', self.id)]):
            for i, ad in enumerate(('Yapılacak', 'Devam Ediyor', 'Tamamlandı')):
                Asama.create({'name': ad, 'sira': i, 'makale_id': self.id, 'katla': ad == 'Tamamlandı'})
        return self.action_ogeleri_ac()

    def _ana_eylem(self):
        return self.env['atlas.bilgi.makale'].action_bilgi_ana()

    @api.model
    def action_bilgi_ana(self):
        """Menü eylemi: son açılan makale / ilk favori / ilk çalışma alanı makalesi; hiç yoksa hoş geldin makalesi."""
        makale = self.search([('favori_mi', '=', True)], limit=1) or self.search([('parent_id', '=', False), ('sablon_mi', '=', False)], limit=1)
        if not makale:
            makale = self.create({'name': self.env._('Hoş geldiniz'), 'simge': '👋',
                                  'body': self.env._('<h2>Bilgi Bankası</h2><p>Sol menüden yeni sayfa ekleyin; sayfaları sürükleyerek '
                                                     'düzenleyin. <code>/</code> ile başlık, tablo, kontrol listesi ekleyebilirsiniz.</p>')})
        return makale.action_ac()

    @api.model
    def yeni_makale(self, ust_id=False, kategori='calisma', sablon_id=False):
        """Kenar çubuğundaki "+" düğmeleri."""
        vals = {'name': self.env._('Adsız')}
        if ust_id:
            vals['parent_id'] = ust_id
        elif kategori == 'ozel':
            vals['ic_yetki'] = 'none'
        if sablon_id:
            sablon = self.browse(sablon_id)
            vals.update(name=sablon.name, simge=sablon.simge, body=sablon.body)
        makale = self.create(vals)
        if sablon_id:
            for alt in self.browse(sablon_id).child_ids:
                alt._alt_kopya(makale).write({'sablon_mi': False})
        return makale.id

    # ------------------------------------------------------------------ kenar çubuğu
    def _dugum(self, favoriler):
        return {'id': self.id, 'ad': self.name or '', 'simge': self.simge or '', 'alt_var': bool(self.alt_sayisi),
                'favori': self.id in favoriler, 'yazabilir': self.kullanici_yetkisi == 'write', 'kategori': self.kategori}

    @api.model
    def kenar_verisi(self, acik_id=False):
        """Kenar çubuğu: favoriler, bölümlerin kök makaleleri ve açık makalenin üst zinciri (genişletilmiş)."""
        favoriler = self.env['atlas.bilgi.favori'].search([('user_id', '=', self.env.uid), ('makale_id.active', '=', True)], order='sira, id')
        fav_ids = set(favoriler.makale_id.ids)
        kokler = self.search([('parent_id', '=', False), ('oge_mi', '=', False), ('sablon_mi', '=', False)])
        acik = self.browse(acik_id).exists() if acik_id else self.browse()
        zincir = [int(x) for x in (acik.parent_path or '').split('/') if x] if acik else []
        return {
            'favoriler': [f.makale_id._dugum(fav_ids) for f in favoriler],
            'bolumler': {k: [m._dugum(fav_ids) for m in kokler if m.kategori == k] for k in ('calisma', 'paylasilan', 'ozel')},
            'zincir': zincir,
            'cop_sayisi': self.with_context(active_test=False).search_count([('cope_atildi', '=', True), ('parent_id.cope_atildi', '=', False)]),
            'yonetici': self.env.user.has_group('base.group_system'),
        }

    @api.model
    def alt_makaleler(self, ust_id):
        fav_ids = set(self.env['atlas.bilgi.favori'].search([('user_id', '=', self.env.uid)]).makale_id.ids)
        return [m._dugum(fav_ids) for m in self.search([('parent_id', '=', ust_id), ('oge_mi', '=', False)])]

    @api.model
    def makale_tasi(self, makale_id, ust_id=False, kategori=False, once_id=False):
        """Sürükle-bırak: makaleyi yeni üstün altına (ya da bölüm köküne), once_id'den önceye yerleştirir."""
        makale = self.browse(makale_id)
        vals = {'parent_id': ust_id or False}
        if not ust_id and kategori and kategori != makale.kategori:
            if kategori == 'calisma':
                vals['ic_yetki'] = 'write'
            elif kategori == 'ozel':
                vals.update(ic_yetki='none', uyeler_bagimsiz=True,
                            uye_ids=[Command.clear(), Command.create({'partner_id': self.env.user.partner_id.id, 'yetki': 'write'})])
        makale.with_context(atlas_bilgi_sessiz=True).write(vals)
        kardesler = self.search([('parent_id', '=', ust_id or False), ('id', '!=', makale.id)] +
                                ([] if ust_id else [('kategori', '=', makale.kategori)]))
        sirali = list(kardesler)
        konum = next((i for i, k in enumerate(sirali) if k.id == once_id), len(sirali))
        sirali.insert(konum, makale)
        for i, k in enumerate(sirali):
            if k.sira != i:
                k.with_context(atlas_bilgi_sessiz=True).sira = i
        return True

    @api.model
    def favori_sirala(self, makale_ids):
        Favori = self.env['atlas.bilgi.favori']
        for i, mid in enumerate(makale_ids):
            Favori.search([('user_id', '=', self.env.uid), ('makale_id', '=', mid)]).sira = i
        return True

    @api.model
    def ara(self, metin, limit=12):
        alan = Domain('name', 'ilike', metin) | Domain('body', 'ilike', metin)
        sonuc = self.search(alan & Domain('sablon_mi', '=', False), limit=limit, order='son_duzenleme desc')
        return [{'id': m.id, 'ad': m.name, 'simge': m.simge or '', 'yol': ' / '.join(m._ust_zincir().mapped('name')[:-1])} for m in sonuc]

    def _ust_zincir(self):
        self.ensure_one()
        ids = [int(x) for x in (self.parent_path or '').split('/') if x]
        return self.browse(ids).sudo()

    def ust_zincir(self):
        self.ensure_one()
        return [{'id': m.id, 'ad': m.name, 'simge': m.simge or ''} for m in self._ust_zincir()]

    @api.model
    def sablonlar(self):
        sablonlar = self.search([('sablon_mi', '=', True)], order='sablon_kategori_id, sira, id')
        return [{'id': s.id, 'ad': s.name, 'simge': s.simge or '📄', 'aciklama': s.sablon_aciklama or '',
                 'kategori': s.sablon_kategori_id.name or self.env._('Diğer')} for s in sablonlar]

    # ------------------------------------------------------------------ cron
    @api.model
    def _cron_cop_temizle(self):
        eski = self.with_context(active_test=False).search([('cope_atildi', '=', True), ('silinme_tarihi', '<=', fields.Date.today())])
        eski.unlink()

    def _paylasim_anahtari(self):
        for m in self.sudo():
            if not m.erisim_anahtari:
                m.erisim_anahtari = secrets.token_urlsafe(24)


class AtlasBilgiUye(models.Model):
    _name = 'atlas.bilgi.uye'
    _description = 'Bilgi Makalesi Üyesi'
    _order = 'id'

    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Kişi', required=True, ondelete='cascade', index=True)
    yetki = fields.Selection(YETKILER, string='Yetki', required=True, default='read')

    _uye_benzersiz = models.Constraint('UNIQUE(makale_id, partner_id)', 'Bir kişi makaleye bir kez üye olabilir.')

    def _erisim_yaz(self):
        self.flush_model()
        self.env['atlas.bilgi.makale'].flush_model(ERISIM_ALANLARI)

    @api.model_create_multi
    def create(self, vals_list):
        uyeler = super().create(vals_list)
        uyeler._erisim_yaz()
        return uyeler

    def write(self, vals):
        sonuc = super().write(vals)
        self._erisim_yaz()
        return sonuc

    def unlink(self):
        sonuc = super().unlink()
        self.env['atlas.bilgi.makale'].flush_model(ERISIM_ALANLARI)
        return sonuc


class AtlasBilgiFavori(models.Model):
    _name = 'atlas.bilgi.favori'
    _description = 'Favori Makale'
    _order = 'sira, id'

    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Kullanıcı', required=True, ondelete='cascade', default=lambda self: self.env.user, index=True)
    sira = fields.Integer(string='Sıra')

    _favori_benzersiz = models.Constraint('UNIQUE(makale_id, user_id)', 'Makale zaten favorilerde.')


class AtlasBilgiAsama(models.Model):
    _name = 'atlas.bilgi.asama'
    _description = 'Bilgi Öğesi Aşaması'
    _order = 'sira, id'

    name = fields.Char(string='Ad', required=True)
    sira = fields.Integer(string='Sıra')
    katla = fields.Boolean(string='Kanbanda Katla')
    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade', index=True)


class AtlasBilgiSablonKategori(models.Model):
    _name = 'atlas.bilgi.sablon.kategori'
    _description = 'Bilgi Şablon Kategorisi'
    _order = 'sira, id'

    name = fields.Char(string='Ad', required=True)
    sira = fields.Integer(string='Sıra')
