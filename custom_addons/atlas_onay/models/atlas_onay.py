from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

ALAN_SECENEK = [('yok', 'Yok'), ('opsiyonel', 'İsteğe bağlı'), ('zorunlu', 'Zorunlu')]
TALEP_DURUMLARI = [
    ('taslak', 'Taslak'),
    ('beklemede', 'Onay Bekliyor'),
    ('onaylandi', 'Onaylandı'),
    ('reddedildi', 'Reddedildi'),
    ('iptal', 'İptal'),
]
SATIR_DURUMLARI = [
    ('yeni', 'Sırada'),
    ('bekliyor', 'Onay Bekliyor'),
    ('onayladi', 'Onayladı'),
    ('reddetti', 'Reddetti'),
    ('iptal', 'Gerek Kalmadı'),
]
ONAY_MODELLERI = [
    ('purchase.order', 'Satın Alma Siparişi'),
    ('sale.order', 'Satış Siparişi'),
    ('account.move', 'Fatura / Fiş'),
]
# Kayıt alanı -> (talep alanı) eşlemesi; onaya gönderirken talebe aktarılır
TALEP_ALANLARI = ['tarih', 'donem', 'tutar', 'partner', 'urun', 'miktar', 'referans', 'ek']


class AtlasOnayKategori(models.Model):
    _name = 'atlas.onay.kategori'
    _description = 'Onay Kategorisi'
    _order = 'sequence, id'

    name = fields.Char(string='Kategori', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    aciklama = fields.Text(string='Açıklama', translate=True)
    renk = fields.Integer(string='Renk')
    company_id = fields.Many2one('res.company', string='Şirket')
    onaylayici_ids = fields.One2many('atlas.onay.kategori.onaylayici', 'kategori_id', string='Onaylayıcılar', copy=True)
    yonetici_onayi = fields.Selection(
        [('yok', 'Hayır'), ('ekle', 'Onaylayıcı olarak ekle'), ('zorunlu', 'Zorunlu onaylayıcı olarak ekle')],
        string='Yönetici Onayı', default='yok', required=True,
        help='Talep edenin çalışan kaydındaki yöneticisi onaylayıcılara eklenir.')
    min_onay = fields.Integer(string='Gereken Onay Sayısı', default=1,
                              help='Talebin onaylanması için gereken en az onay. Zorunlu onaylayıcıların hepsi ayrıca onaylamalıdır.')
    sirali = fields.Boolean(string='Sıralı Onay', help='Onaylayıcılar sıra numarasına göre birbiri ardına onay verir.')
    alan_tarih = fields.Selection(ALAN_SECENEK, string='Tarih', default='yok', required=True)
    alan_donem = fields.Selection(ALAN_SECENEK, string='Tarih Aralığı', default='yok', required=True)
    alan_tutar = fields.Selection(ALAN_SECENEK, string='Tutar', default='yok', required=True)
    alan_partner = fields.Selection(ALAN_SECENEK, string='Cari', default='yok', required=True)
    alan_urun = fields.Selection(ALAN_SECENEK, string='Ürün', default='yok', required=True)
    alan_miktar = fields.Selection(ALAN_SECENEK, string='Miktar', default='yok', required=True)
    alan_referans = fields.Selection(ALAN_SECENEK, string='Referans', default='yok', required=True)
    alan_ek = fields.Selection(ALAN_SECENEK, string='Belge Eki', default='yok', required=True)
    bekleyen_sayisi = fields.Integer(string='Onayımı Bekleyen', compute='_compute_bekleyen_sayisi')
    talep_sayisi = fields.Integer(string='Taleplerim', compute='_compute_bekleyen_sayisi')

    _min_onay_pozitif = models.Constraint('CHECK(min_onay >= 1)', 'Gereken onay sayısı en az 1 olmalı.')

    def _compute_bekleyen_sayisi(self):
        bekleyen = dict(self.env['atlas.onay.satir'].sudo()._read_group(
            [('user_id', '=', self.env.uid), ('durum', '=', 'bekliyor'), ('talep_id.kategori_id', 'in', self.ids)],
            ['talep_id.kategori_id'], ['__count']))
        benim = dict(self.env['atlas.onay.talep']._read_group(
            [('talep_eden_id', '=', self.env.uid), ('durum', 'in', ('taslak', 'beklemede')), ('kategori_id', 'in', self.ids)],
            ['kategori_id'], ['__count']))
        for kategori in self:
            kategori.bekleyen_sayisi = bekleyen.get(kategori, 0)
            kategori.talep_sayisi = benim.get(kategori, 0)

    @api.constrains('onaylayici_ids', 'min_onay', 'yonetici_onayi')
    def _check_min_onay(self):
        for kategori in self:
            olasi = len(kategori.onaylayici_ids) + (1 if kategori.yonetici_onayi != 'yok' else 0)
            if olasi and kategori.min_onay > olasi:
                raise ValidationError(self.env._('%(kategori)s: gereken onay sayısı (%(min)s) onaylayıcı sayısından fazla olamaz.',
                                                 kategori=kategori.name, min=kategori.min_onay))

    def action_yeni_talep(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.onay.talep', 'view_mode': 'form',
                'context': {'default_kategori_id': self.id}, 'name': self.name}

    def action_bekleyenler(self):
        self.ensure_one()
        eylem = self.env['ir.actions.act_window']._for_xml_id('atlas_onay.action_atlas_onay_bekleyen')
        eylem['domain'] = [('kategori_id', '=', self.id)]
        return eylem


class AtlasOnayKategoriOnaylayici(models.Model):
    _name = 'atlas.onay.kategori.onaylayici'
    _description = 'Kategori Onaylayıcısı'
    _order = 'sira, id'

    kategori_id = fields.Many2one('atlas.onay.kategori', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Kullanıcı', required=True, domain=[('share', '=', False)])
    zorunlu = fields.Boolean(string='Zorunlu')
    sira = fields.Integer(string='Sıra', default=10)

    _kullanici_uniq = models.Constraint('UNIQUE(kategori_id, user_id)', 'Bir kullanıcı kategoride bir kez onaylayıcı olabilir.')


class AtlasOnayTalep(models.Model):
    _name = 'atlas.onay.talep'
    _description = 'Onay Talebi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Numara', required=True, copy=False, readonly=True, default='/')
    konu = fields.Char(string='Konu', required=True, tracking=True)
    kategori_id = fields.Many2one('atlas.onay.kategori', string='Kategori', required=True, tracking=True,
                                  index=True)
    talep_eden_id = fields.Many2one('res.users', string='Talep Eden', required=True, default=lambda self: self.env.user,
                                    tracking=True, index=True)
    durum = fields.Selection(TALEP_DURUMLARI, string='Durum', default='taslak', required=True, tracking=True, copy=False,
                             index=True)
    aciklama = fields.Html(string='Açıklama')
    tarih = fields.Datetime(string='Tarih')
    tarih_bas = fields.Datetime(string='Başlangıç')
    tarih_bit = fields.Datetime(string='Bitiş')
    tutar = fields.Monetary(string='Tutar', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Para Birimi', default=lambda self: self.env.company.currency_id)
    partner_id = fields.Many2one('res.partner', string='Cari')
    urun_id = fields.Many2one('product.product', string='Ürün')
    miktar = fields.Float(string='Miktar', digits='Product Unit')
    referans = fields.Char(string='Referans')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    onay_ids = fields.One2many('atlas.onay.satir', 'talep_id', string='Onaylar', copy=False)
    onaylayan_sayisi = fields.Integer(compute='_compute_ozet')
    gereken_onay = fields.Integer(compute='_compute_ozet')
    benim_durumum = fields.Selection(SATIR_DURUMLARI, compute='_compute_benim_durumum')
    benim_talebim = fields.Boolean(compute='_compute_benim_durumum')
    onay_tarihi = fields.Datetime(string='Sonuç Tarihi', readonly=True, copy=False)
    # Kayıt onayı (satın alma / satış / fatura)
    kural_id = fields.Many2one('atlas.onay.kural', string='Onay Kuralı', readonly=True, copy=False, index=True)
    res_model = fields.Char(string='İlgili Model', readonly=True, copy=False, index=True)
    res_id = fields.Many2oneReference(string='İlgili Kayıt', model_field='res_model', readonly=True, copy=False, index=True)

    alan_tarih = fields.Selection(related='kategori_id.alan_tarih', string='Alan: tarih')
    alan_donem = fields.Selection(related='kategori_id.alan_donem', string='Alan: donem')
    alan_tutar = fields.Selection(related='kategori_id.alan_tutar', string='Alan: tutar')
    alan_partner = fields.Selection(related='kategori_id.alan_partner', string='Alan: partner')
    alan_urun = fields.Selection(related='kategori_id.alan_urun', string='Alan: urun')
    alan_miktar = fields.Selection(related='kategori_id.alan_miktar', string='Alan: miktar')
    alan_referans = fields.Selection(related='kategori_id.alan_referans', string='Alan: referans')
    alan_ek = fields.Selection(related='kategori_id.alan_ek', string='Alan: ek')

    @api.depends('onay_ids.durum', 'kategori_id.min_onay')
    def _compute_ozet(self):
        for talep in self:
            talep.onaylayan_sayisi = len(talep.sudo().onay_ids.filtered(lambda s: s.durum == 'onayladi'))
            talep.gereken_onay = talep._gereken_onay()

    @api.depends_context('uid')
    @api.depends('onay_ids.durum', 'onay_ids.user_id')
    def _compute_benim_durumum(self):
        for talep in self:
            satir = talep.onay_ids.filtered(lambda s: s.user_id.id == self.env.uid)[:1]
            talep.benim_durumum = satir.durum or False
            talep.benim_talebim = talep.talep_eden_id.id == self.env.uid

    @api.constrains('tarih_bas', 'tarih_bit')
    def _check_donem(self):
        for talep in self:
            if talep.tarih_bas and talep.tarih_bit and talep.tarih_bit < talep.tarih_bas:
                raise ValidationError(self.env._('Bitiş tarihi başlangıçtan önce olamaz.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.onay.talep') or '/'
        return super().create(vals_list)

    def unlink(self):
        if any(t.durum not in ('taslak', 'iptal') for t in self):
            raise UserError(self.env._('Yalnızca taslak veya iptal edilmiş talepler silinebilir.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Yardımcılar
    # -------------------------------------------------------------------------

    def _gereken_onay(self):
        self.ensure_one()
        # zorunlu onaylayıcıların hepsi ayrıca aranır (_sonucu_degerlendir)
        return min(self.kategori_id.min_onay, len(self.sudo().onay_ids)) or self.kategori_id.min_onay

    def _yonetici(self):
        self.ensure_one()
        if 'hr.employee' not in self.env:
            return self.env['res.users']
        calisan = self.env['hr.employee'].sudo().search([('user_id', '=', self.talep_eden_id.id),
                                                         ('company_id', 'in', (self.company_id.id, False))], limit=1)
        return calisan.parent_id.user_id

    def _eksik_alanlar(self):
        self.ensure_one()
        k = self.kategori_id
        kontrol = {
            'alan_tarih': ('tarih', self.tarih), 'alan_donem': ('tarih aralığı', self.tarih_bas and self.tarih_bit),
            'alan_tutar': ('tutar', self.tutar), 'alan_partner': ('cari', self.partner_id),
            'alan_urun': ('ürün', self.urun_id), 'alan_miktar': ('miktar', self.miktar),
            'alan_referans': ('referans', self.referans), 'alan_ek': ('belge eki', self.message_attachment_count),
        }
        return [ad for alan, (ad, deger) in kontrol.items() if k[alan] == 'zorunlu' and not deger]

    def _onay_satirlari_olustur(self):
        """Kategori onaylayıcılarından (ve yöneticiden) onay satırlarını kurar."""
        self.ensure_one()
        satirlar = [{'user_id': o.user_id.id, 'zorunlu': o.zorunlu, 'sira': o.sira}
                    for o in self.kategori_id.onaylayici_ids if o.user_id.active]
        yonetici = self._yonetici() if self.kategori_id.yonetici_onayi != 'yok' else self.env['res.users']
        if yonetici:
            zorunlu = self.kategori_id.yonetici_onayi == 'zorunlu'
            mevcut = next((s for s in satirlar if s['user_id'] == yonetici.id), None)
            if mevcut:
                mevcut['zorunlu'] = mevcut['zorunlu'] or zorunlu
            else:
                satirlar.insert(0, {'user_id': yonetici.id, 'zorunlu': zorunlu, 'sira': 0})
        elif self.kategori_id.yonetici_onayi == 'zorunlu':
            raise UserError(self.env._('Bu kategori yönetici onayı gerektiriyor; %s için çalışan kaydında yönetici tanımlı değil.',
                                       self.talep_eden_id.name))
        mevcut_kullanicilar = set(self.onay_ids.user_id.ids)
        yeni = [dict(s, talep_id=self.id) for s in satirlar if s['user_id'] not in mevcut_kullanicilar]
        self.env['atlas.onay.satir'].sudo().create(yeni)

    def _sira_aktif_et(self):
        """Sıralı onayda sırası gelen satırları, değilse tümünü bekliyor yapar."""
        self.ensure_one()
        yeniler = self.sudo().onay_ids.filtered(lambda s: s.durum == 'yeni')
        if not yeniler:
            return
        if self.kategori_id.sirali:
            if self.sudo().onay_ids.filtered(lambda s: s.durum == 'bekliyor'):
                return
            ilk_sira = min(yeniler.mapped('sira'))
            yeniler = yeniler.filtered(lambda s: s.sira == ilk_sira)
        for satir in yeniler:
            satir.sudo().durum = 'bekliyor'
            self.sudo().activity_schedule(
                'atlas_onay.mail_activity_onay', user_id=satir.user_id.id,
                summary=self.env._('Onayınız bekleniyor: %s', self.konu))

    def _aktiviteleri_kapat(self, kullanicilar=None, iptal=False):
        tur = self.env.ref('atlas_onay.mail_activity_onay')
        aktiviteler = self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == tur and (kullanicilar is None or a.user_id in kullanicilar))
        if iptal:
            aktiviteler.unlink()
        else:
            aktiviteler.action_feedback()

    def _sonucu_degerlendir(self):
        self.ensure_one()
        satirlar = self.sudo().onay_ids
        if satirlar.filtered(lambda s: s.durum == 'reddetti'):
            self._sonuclandir('reddedildi')
            return
        onaylayan = satirlar.filtered(lambda s: s.durum == 'onayladi')
        zorunlular_tamam = all(s.durum == 'onayladi' for s in satirlar.filtered('zorunlu'))
        if zorunlular_tamam and len(onaylayan) >= self._gereken_onay():
            self._sonuclandir('onaylandi')
        else:
            self._sira_aktif_et()

    def _sonuclandir(self, durum):
        self.ensure_one()
        self.sudo().onay_ids.filtered(lambda s: s.durum in ('yeni', 'bekliyor')).write({'durum': 'iptal'})
        self._aktiviteleri_kapat(iptal=True)
        self.sudo().write({'durum': durum, 'onay_tarihi': fields.Datetime.now()})
        mesaj = (self.env._('Talebiniz onaylandı.') if durum == 'onaylandi'
                 else self.env._('Talebiniz reddedildi.'))
        self.sudo().message_post(body=mesaj, partner_ids=self.talep_eden_id.partner_id.ids,
                                 subtype_xmlid='mail.mt_comment')
        kayit = self._ilgili_kayit()
        if kayit:
            kayit.message_post(body=self.env._('%(talep)s onay talebi sonucu: %(durum)s',
                                               talep=self.name, durum=dict(TALEP_DURUMLARI)[durum]))
            if durum == 'onaylandi':
                kayit.activity_schedule('mail.mail_activity_data_todo', user_id=self.talep_eden_id.id,
                                        summary=self.env._('Onaylandı, işleme devam edebilirsiniz'))

    def _ilgili_kayit(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            return self.env[self.res_model].sudo().browse(self.res_id).exists()
        return None

    def _benim_satirim(self):
        self.ensure_one()
        satir = self.sudo().onay_ids.filtered(lambda s: s.user_id.id == self.env.uid and s.durum == 'bekliyor')
        if not satir:
            raise AccessError(self.env._('%s için onayınız beklenmiyor.', self.name))
        return satir

    # -------------------------------------------------------------------------
    # Düğmeler
    # -------------------------------------------------------------------------

    def action_gonder(self):
        for talep in self:
            if talep.durum != 'taslak':
                continue
            eksik = talep._eksik_alanlar()
            if eksik:
                raise UserError(self.env._('%(talep)s için zorunlu alanlar eksik: %(alanlar)s',
                                           talep=talep.name, alanlar=', '.join(eksik)))
            talep._onay_satirlari_olustur()
            if not talep.onay_ids:
                raise UserError(self.env._('%s kategorisinde onaylayıcı tanımlı değil.', talep.kategori_id.name))
            talep.write({'durum': 'beklemede'})
            talep._sira_aktif_et()
        return True

    def action_onayla(self, aciklama=None):
        for talep in self:
            if talep.durum != 'beklemede':
                raise UserError(self.env._('%s onay beklemiyor.', talep.name))
            satir = talep._benim_satirim()
            satir.write({'durum': 'onayladi', 'tarih': fields.Datetime.now(), 'aciklama': aciklama})
            talep._aktiviteleri_kapat(self.env.user)
            talep.sudo().message_post(body=self.env._('%s onayladı.', self.env.user.name) + (f' — {aciklama}' if aciklama else ''),
                                      author_id=self.env.user.partner_id.id, subtype_xmlid='mail.mt_note')
            talep._sonucu_degerlendir()
        return True

    def action_reddet_sihirbaz(self):
        self.ensure_one()
        self._benim_satirim()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.onay.red', 'view_mode': 'form', 'target': 'new',
                'context': {'default_talep_id': self.id}, 'name': self.env._('Reddet')}

    def action_reddet(self, neden):
        for talep in self:
            if talep.durum != 'beklemede':
                raise UserError(self.env._('%s onay beklemiyor.', talep.name))
            if not (neden or '').strip():
                raise UserError(self.env._('Red nedenini yazın.'))
            satir = talep._benim_satirim()
            satir.write({'durum': 'reddetti', 'tarih': fields.Datetime.now(), 'aciklama': neden})
            talep.sudo().message_post(body=self.env._('%(kisi)s reddetti: %(neden)s', kisi=self.env.user.name, neden=neden),
                                      author_id=self.env.user.partner_id.id, subtype_xmlid='mail.mt_note')
            talep._sonucu_degerlendir()
        return True

    def action_geri_cek(self):
        """Talep eden, sonuçlanmamış talebi taslağa geri çeker."""
        for talep in self.filtered(lambda t: t.durum in ('beklemede', 'reddedildi', 'iptal')):
            if not talep.benim_talebim and not self.env.user.has_group('atlas_onay.group_onay_manager'):
                raise AccessError(self.env._('Talebi yalnızca talep eden geri çekebilir.'))
            talep._aktiviteleri_kapat(iptal=True)
            talep.sudo().onay_ids.unlink()
            talep.write({'durum': 'taslak', 'onay_tarihi': False})
        return True

    def action_iptal(self):
        for talep in self.filtered(lambda t: t.durum in ('taslak', 'beklemede')):
            talep._aktiviteleri_kapat(iptal=True)
            talep.sudo().onay_ids.filtered(lambda s: s.durum in ('yeni', 'bekliyor')).write({'durum': 'iptal'})
            talep.write({'durum': 'iptal'})
        return True

    def action_ilgili_kayit(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}


class AtlasOnaySatir(models.Model):
    _name = 'atlas.onay.satir'
    _description = 'Onay Satırı'
    _order = 'sira, id'
    _rec_name = 'user_id'

    talep_id = fields.Many2one('atlas.onay.talep', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Onaylayıcı', required=True, index=True)
    zorunlu = fields.Boolean(string='Zorunlu')
    sira = fields.Integer(string='Sıra', default=10)
    durum = fields.Selection(SATIR_DURUMLARI, string='Durum', default='yeni', required=True)
    tarih = fields.Datetime(string='Tarih', readonly=True)
    aciklama = fields.Char(string='Not', readonly=True)
    talep_durum = fields.Selection(related='talep_id.durum', string='Talep Durumu')
    kategori_id = fields.Many2one(related='talep_id.kategori_id', store=True)
    talep_eden_id = fields.Many2one(related='talep_id.talep_eden_id', store=True)


class AtlasOnayKural(models.Model):
    _name = 'atlas.onay.kural'
    _description = 'Kayıt Onay Kuralı'
    _order = 'sequence, id'

    name = fields.Char(string='Kural', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model = fields.Selection(ONAY_MODELLERI, string='Belge Türü', required=True)
    domain = fields.Char(string='Koşul', default='[]',
                         help='Bu koşula uyan kayıtlar onaylanmadan onaylanamaz / işlenemez.')
    kategori_id = fields.Many2one('atlas.onay.kategori', string='Onay Kategorisi', required=True,
                                  help='Onaylayıcılar ve onay sayısı bu kategoriden alınır.')
    company_id = fields.Many2one('res.company', string='Şirket')

    @api.constrains('domain', 'model')
    def _check_domain(self):
        for kural in self:
            try:
                self.env[kural.model].search_count(kural._domain())
            except Exception as hata:  # noqa: BLE001
                raise ValidationError(self.env._('%(kural)s: koşul geçersiz (%(hata)s).', kural=kural.name, hata=hata)) from hata

    def _domain(self):
        self.ensure_one()
        return safe_eval(self.domain or '[]', {'uid': self.env.uid})

    def _uygun_mu(self, kayit):
        self.ensure_one()
        if self.company_id and kayit.company_id and kayit.company_id != self.company_id:
            return False
        return bool(kayit.sudo().filtered_domain(self._domain()))


class AtlasOnayMixin(models.AbstractModel):
    _name = 'atlas.onay.mixin'
    _description = 'Kayıt Onayı Desteği'

    atlas_onay_durumu = fields.Selection(
        [('gerekmez', 'Gerekmez'), ('gerekli', 'Onay Gerekli'), ('beklemede', 'Onay Bekliyor'),
         ('onaylandi', 'Onaylandı'), ('reddedildi', 'Reddedildi')],
        string='Onay Durumu', compute='_compute_atlas_onay_durumu')
    atlas_onay_talep_sayisi = fields.Integer(compute='_compute_atlas_onay_durumu')

    def _atlas_onay_tutar(self):
        return self.amount_total if 'amount_total' in self._fields else 0.0

    def _atlas_onay_talepleri(self):
        self.ensure_one()
        if not self.id:
            return self.env['atlas.onay.talep']
        return self.env['atlas.onay.talep'].sudo().search([('res_model', '=', self._name), ('res_id', '=', self.id)])

    def _atlas_onay_eksik_kurallar(self):
        """Uygun olup henüz (güncel tutarla) onaylanmamış kurallar ve son talepleri."""
        self.ensure_one()
        kurallar = self.env['atlas.onay.kural'].sudo().search([('model', '=', self._name)])
        kurallar = kurallar.filtered(lambda k: k._uygun_mu(self))
        if not kurallar:
            return {}
        talepler = self._atlas_onay_talepleri()
        tutar = self._atlas_onay_tutar()
        eksik = {}
        for kural in kurallar:
            son = talepler.filtered(lambda t: t.kural_id == kural and t.durum != 'iptal').sorted('id', reverse=True)[:1]
            gecerli = son.durum == 'onaylandi'
            if gecerli and tutar and 'currency_id' in self._fields:
                # onaydan sonra tutar arttıysa yeniden onay gerekir
                gecerli = self.currency_id.compare_amounts(tutar, son.tutar) <= 0
            if not gecerli:
                eksik[kural] = son
        return eksik

    def _compute_atlas_onay_durumu(self):
        for kayit in self:
            talepler = kayit._atlas_onay_talepleri()
            kayit.atlas_onay_talep_sayisi = len(talepler)
            eksik = kayit._atlas_onay_eksik_kurallar()
            if not eksik:
                kayit.atlas_onay_durumu = 'onaylandi' if talepler.filtered(lambda t: t.durum == 'onaylandi') else 'gerekmez'
                continue
            durumlar = {t.durum for t in eksik.values() if t}
            if 'reddedildi' in durumlar:
                kayit.atlas_onay_durumu = 'reddedildi'
            elif 'beklemede' in durumlar:
                kayit.atlas_onay_durumu = 'beklemede'
            else:
                kayit.atlas_onay_durumu = 'gerekli'

    def _atlas_onay_kontrol(self):
        for kayit in self:
            eksik = kayit._atlas_onay_eksik_kurallar()
            if eksik:
                raise UserError(self.env._(
                    '%(kayit)s onay gerektiriyor (%(kurallar)s). "Onaya Gönder" düğmesiyle talep oluşturun; '
                    'onaylandıktan sonra işleme devam edebilirsiniz.',
                    kayit=kayit.display_name, kurallar=', '.join(k.name for k in eksik)))

    def action_atlas_onaya_gonder(self):
        self.ensure_one()
        eksik = self._atlas_onay_eksik_kurallar()
        if not eksik:
            raise UserError(self.env._('Bu kayıt için bekleyen bir onay gereksinimi yok.'))
        Talep = self.env['atlas.onay.talep'].sudo()
        for kural, son in eksik.items():
            if son and son.durum == 'beklemede':
                continue
            talep = Talep.create({
                'konu': f'{kural.name}: {self.display_name}', 'kategori_id': kural.kategori_id.id, 'kural_id': kural.id,
                'talep_eden_id': self.env.uid, 'res_model': self._name, 'res_id': self.id,
                'tutar': self._atlas_onay_tutar(), 'company_id': self.company_id.id or self.env.company.id,
                'currency_id': self.currency_id.id if 'currency_id' in self._fields else False,
                'partner_id': self.partner_id.id if 'partner_id' in self._fields else False,
                'referans': self.name if 'name' in self._fields else False,
            })
            # Kategorinin form alanı zorunlulukları kayıt onayında aranmaz
            talep._onay_satirlari_olustur()
            if not talep.onay_ids:
                raise UserError(self.env._('%s kategorisinde onaylayıcı tanımlı değil.', kural.kategori_id.name))
            talep.write({'durum': 'beklemede'})
            talep._sira_aktif_et()
        self.message_post(body=self.env._('Onaya gönderildi.'))
        return self.action_atlas_onay_talepleri()

    def action_atlas_onay_talepleri(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.onay.talep', 'view_mode': 'list,form',
                'name': self.env._('Onay Talepleri'),
                'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)]}


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'atlas.onay.mixin']

    def button_confirm(self):
        self._atlas_onay_kontrol()
        return super().button_confirm()


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'atlas.onay.mixin']

    def action_confirm(self):
        self._atlas_onay_kontrol()
        return super().action_confirm()


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'atlas.onay.mixin']

    def action_post(self):
        self._atlas_onay_kontrol()
        return super().action_post()
