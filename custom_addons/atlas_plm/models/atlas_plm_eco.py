from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .atlas_plm_tanim import ONAY_TIPLERI

DURUMLAR = [('taslak', 'Yapılacak'), ('islemde', 'İşlemde'), ('bitti', 'Uygulandı'), ('iptal', 'İptal')]
ONCELIKLER = [('0', 'Normal'), ('1', 'Düşük'), ('2', 'Yüksek'), ('3', 'Acil')]


def _bool_arama(operator, value):
    """Boolean hesaplanmış alan araması: Odoo 20 '=' True'yu 'in' [True] olarak da iletebilir."""
    if operator in ('in', 'not in'):
        degerler = {value} if isinstance(value, (bool, int, str)) or value is None else set(value)
        sonuc = True in degerler
        return sonuc if operator == 'in' else not sonuc
    if operator in ('=', '!='):
        return bool(value) if operator == '=' else not bool(value)
    raise ValueError(operator)


class AtlasPlmEco(models.Model):
    """Mühendislik Değişiklik Emri (ECO)."""
    _name = 'atlas.plm.eco'
    _description = 'Mühendislik Değişiklik Emri'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'oncelik desc, id desc'

    name = fields.Char(string='ECO No', required=True, copy=False, readonly=True, default='/', index='trigram')
    baslik = fields.Char(string='Başlık', required=True, tracking=True)
    tip_id = fields.Many2one('atlas.plm.tip', string='Tip', required=True, tracking=True,
                             default=lambda self: self.env['atlas.plm.tip'].search([], limit=1))
    asama_id = fields.Many2one('atlas.plm.asama', string='Aşama', tracking=True, copy=False, index=True,
                               group_expand='_read_group_asama_ids',
                               compute='_compute_asama_id', store=True, readonly=False,
                               domain="['|', ('tip_ids', '=', False), ('tip_ids', 'in', tip_id)]")
    durum = fields.Selection(DURUMLAR, string='Durum', default='taslak', required=True, tracking=True, copy=False)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Sorumlu', default=lambda self: self.env.user, tracking=True)
    oncelik = fields.Selection(ONCELIKLER, string='Öncelik', default='0')
    etiket_ids = fields.Many2many('atlas.plm.etiket', string='Etiketler')
    color = fields.Integer(string='Renk')
    aciklama = fields.Html(string='Değişiklik Açıklaması')

    uygulama = fields.Selection([('bom', 'Ürün Reçetesi'), ('urun', 'Yalnızca Ürün (doküman)')],
                                string='Uygulanacağı Yer', required=True, default='bom')
    product_tmpl_id = fields.Many2one('product.template', string='Ürün', required=True, tracking=True, index=True)
    bom_id = fields.Many2one('mrp.bom', string='Mevcut Reçete', tracking=True, index=True,
                             domain="[('product_tmpl_id', '=', product_tmpl_id)]")
    yeni_bom_id = fields.Many2one('mrp.bom', string='Yeni Revizyon', copy=False, readonly=True, index=True)
    mevcut_versiyon = fields.Integer(string='Mevcut Sürüm', compute='_compute_versiyon')
    yeni_versiyon = fields.Integer(string='Yeni Sürüm', compute='_compute_versiyon')

    yururluk = fields.Selection([('hemen', 'Onaylanınca'), ('tarih', 'Belirli tarihte')], string='Yürürlük',
                                required=True, default='hemen')
    yururluk_tarihi = fields.Datetime(string='Yürürlük Tarihi')
    uygulama_tarihi = fields.Datetime(string='Uygulama Tarihi', readonly=True, copy=False)
    zamanlandi = fields.Boolean(string='Yürürlük Bekliyor', readonly=True, copy=False)

    onay_ids = fields.One2many('atlas.plm.eco.onay', 'eco_id', string='Onaylar', copy=False)
    onay_durumu = fields.Selection([('yok', 'Onay gerekmiyor'), ('bekliyor', 'Onay bekliyor'),
                                    ('onaylandi', 'Onaylandı'), ('reddedildi', 'Reddedildi')],
                                   string='Onay Durumu', compute='_compute_onay')
    onayimi_bekliyor = fields.Boolean(string='Onayımı Bekliyor', compute='_compute_onay', search='_search_onayimi_bekliyor')
    bom_degisiklik_ids = fields.One2many('atlas.plm.eco.bom.degisiklik', 'eco_id', string='Bileşen Değişiklikleri', copy=False)
    rota_degisiklik_ids = fields.One2many('atlas.plm.eco.rota.degisiklik', 'eco_id', string='Operasyon Değişiklikleri', copy=False)
    degisiklik_sayisi = fields.Integer(compute='_compute_degisiklik_sayisi', string='Değişiklik Sayısı')
    dokuman_ids = fields.Many2many('ir.attachment', 'atlas_plm_eco_dokuman_rel', 'eco_id', 'attachment_id',
                                   string='Teknik Dokümanlar',
                                   help='Değişiklik uygulandığında ürünün dokümanlarına eklenir.')
    yeni_bom_satir_ids = fields.One2many(related='yeni_bom_id.bom_line_ids', string='Yeni Bileşenler')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('atlas.plm.eco') or '/'
        ecolar = super().create(vals_list)
        for eco in ecolar:
            eco._onaylari_olustur()
        return ecolar

    def write(self, vals):
        if 'asama_id' in vals:
            yeni = self.env['atlas.plm.asama'].browse(vals['asama_id'])
            for eco in self:
                eco._asama_gecis_kontrol(yeni)
        res = super().write(vals)
        if 'asama_id' in vals:
            for eco in self:
                eco._onaylari_olustur()
                if eco.asama_id.son_asama and eco.durum != 'bitti':
                    eco._son_asamaya_geldi()
        return res

    @api.model
    def _read_group_asama_ids(self, stages, domain):
        tip_id = self.env.context.get('default_tip_id')
        alan = [('tip_ids', '=', False)] if not tip_id else ['|', ('tip_ids', '=', False), ('tip_ids', 'in', tip_id)]
        return stages.search(alan)

    @api.depends('tip_id')
    def _compute_asama_id(self):
        for eco in self:
            if not eco.asama_id or (eco.asama_id.tip_ids and eco.tip_id not in eco.asama_id.tip_ids):
                eco.asama_id = self.env['atlas.plm.asama'].search(
                    ['|', ('tip_ids', '=', False), ('tip_ids', 'in', eco.tip_id.ids)], limit=1)

    @api.depends('bom_id.atlas_versiyon', 'yeni_bom_id.atlas_versiyon', 'product_tmpl_id.atlas_versiyon', 'uygulama')
    def _compute_versiyon(self):
        for eco in self:
            if eco.uygulama == 'bom':
                eco.mevcut_versiyon = eco.bom_id.atlas_versiyon if eco.bom_id else 0
                eco.yeni_versiyon = eco.yeni_bom_id.atlas_versiyon or eco.mevcut_versiyon + 1
            else:
                eco.mevcut_versiyon = eco.product_tmpl_id.atlas_versiyon
                eco.yeni_versiyon = eco.mevcut_versiyon + 1

    @api.depends('onay_ids.durum', 'asama_id')
    def _compute_onay(self):
        user = self.env.user
        for eco in self:
            onaylar = eco.onay_ids.filtered(lambda o: o.asama_id == eco.asama_id)
            zorunlu = onaylar.filtered(lambda o: o.onay_tipi == 'zorunlu')
            if any(o.durum == 'reddedildi' for o in onaylar):
                eco.onay_durumu = 'reddedildi'
            elif any(o.durum == 'bekliyor' for o in zorunlu):
                eco.onay_durumu = 'bekliyor'
            elif onaylar:
                eco.onay_durumu = 'onaylandi'
            else:
                eco.onay_durumu = 'yok'
            eco.onayimi_bekliyor = eco.durum in ('taslak', 'islemde') and any(
                o.durum == 'bekliyor' and o.onay_tipi != 'yorum' and o.sablon_id._onaylayabilir(user) for o in onaylar)

    def _search_onayimi_bekliyor(self, operator, value):
        adaylar = self.search([('durum', 'in', ('taslak', 'islemde')), ('onay_ids.durum', '=', 'bekliyor')])
        ids = adaylar.filtered('onayimi_bekliyor').ids
        return [('id', 'in' if _bool_arama(operator, value) else 'not in', ids)]

    @api.depends('bom_degisiklik_ids', 'rota_degisiklik_ids')
    def _compute_degisiklik_sayisi(self):
        for eco in self:
            eco.degisiklik_sayisi = len(eco.bom_degisiklik_ids) + len(eco.rota_degisiklik_ids)

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        if self.product_tmpl_id and self.bom_id.product_tmpl_id != self.product_tmpl_id:
            self.bom_id = self.env['mrp.bom'].search([('product_tmpl_id', '=', self.product_tmpl_id.id)], limit=1)

    @api.depends('name', 'baslik')
    def _compute_display_name(self):
        for eco in self:
            eco.display_name = f'{eco.name} {eco.baslik or ""}'.strip()

    # -------------------------------------------------------------------------
    # Onaylar ve aşama geçişi
    # -------------------------------------------------------------------------

    def _onaylari_olustur(self):
        """Bulunulan aşamanın onay şablonları için onay satırı açar ve onaylayacaklara aktivite atar."""
        self.ensure_one()
        if self.durum in ('bitti', 'iptal'):
            return
        mevcut = self.onay_ids.filtered(lambda o: o.asama_id == self.asama_id).sablon_id
        for sablon in self.asama_id.onay_sablon_ids - mevcut:
            self.env['atlas.plm.eco.onay'].create({'eco_id': self.id, 'sablon_id': sablon.id})
            if sablon.onay_tipi != 'yorum':
                for user in sablon._bildirilecekler():
                    self.activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                                           summary=self.env._('ECO onayı: %s', sablon.name))

    def _asama_gecis_kontrol(self, yeni):
        self.ensure_one()
        if self.durum == 'bitti':
            raise UserError(self.env._('%s uygulandı; aşaması değiştirilemez.', self.name))
        if self.durum == 'iptal':
            raise UserError(self.env._('%s iptal edildi.', self.name))
        if yeni.sequence > self.asama_id.sequence or (yeni.sequence == self.asama_id.sequence and yeni.id > self.asama_id.id):
            if self.onay_durumu == 'reddedildi':
                raise UserError(self.env._('%s reddedildi; ilerletmek için ret kaldırılmalı.', self.name))
            if self.onay_durumu == 'bekliyor':
                bekleyen = self.onay_ids.filtered(
                    lambda o: o.asama_id == self.asama_id and o.onay_tipi == 'zorunlu' and o.durum == 'bekliyor')
                raise UserError(self.env._('%(eco)s için bekleyen zorunlu onaylar var: %(onay)s',
                                           eco=self.name, onay=', '.join(bekleyen.mapped('name'))))
            if yeni.son_asama and self.uygulama == 'bom' and not self.yeni_bom_id:
                raise UserError(self.env._('%s: önce reçete revizyonunu başlatın.', self.name))

    def action_sonraki_asama(self):
        for eco in self:
            sonraki = self.env['atlas.plm.asama'].search(
                ['|', ('tip_ids', '=', False), ('tip_ids', 'in', eco.tip_id.ids),
                 '|', ('sequence', '>', eco.asama_id.sequence),
                 '&', ('sequence', '=', eco.asama_id.sequence), ('id', '>', eco.asama_id.id)], limit=1)
            if not sonraki:
                raise UserError(self.env._('%s son aşamada.', eco.name))
            eco.asama_id = sonraki
        return True

    def _onaylarim(self):
        user = self.env.user
        return self.onay_ids.filtered(lambda o: o.asama_id == o.eco_id.asama_id and o.durum == 'bekliyor'
                                      and o.onay_tipi != 'yorum' and o.sablon_id._onaylayabilir(user))

    def action_onayla(self):
        onaylar = self._onaylarim()
        if not onaylar:
            raise UserError(self.env._('Bu aşamada onayınızı bekleyen bir onay yok.'))
        onaylar._karar('onaylandi')
        return True

    def action_reddet(self):
        onaylar = self._onaylarim() or self.onay_ids.filtered(
            lambda o: o.asama_id == o.eco_id.asama_id and o.durum == 'onaylandi' and o.sablon_id._onaylayabilir(self.env.user))
        if not onaylar:
            raise UserError(self.env._('Bu aşamada reddedebileceğiniz bir onay yok.'))
        onaylar._karar('reddedildi')
        return True

    # -------------------------------------------------------------------------
    # Revizyon
    # -------------------------------------------------------------------------

    def action_revizyon_baslat(self):
        self.ensure_one()
        if self.durum != 'taslak':
            raise UserError(self.env._('Revizyon zaten başlatıldı.'))
        if self.uygulama == 'bom':
            if self.bom_id:
                if not self.bom_id.active:
                    raise UserError(self.env._('%s arşivlenmiş bir reçete; güncel reçeteyi seçin.', self.bom_id.display_name))
                yeni = self.bom_id._atlas_revizyon_kopyala()
            else:
                # Yeni ürün girişi: boş taslak reçete
                yeni = self.env['mrp.bom'].create({
                    'product_tmpl_id': self.product_tmpl_id.id, 'active': False, 'company_id': self.company_id.id,
                    'atlas_versiyon': 1})
            self.yeni_bom_id = yeni
        self.durum = 'islemde'
        self._degisiklik_hesapla()
        self.message_post(body=self.env._('Revizyon başlatıldı (sürüm %s).', self.yeni_versiyon))
        return self.action_revizyon_ac() if self.yeni_bom_id else True

    def action_revizyon_ac(self):
        self.ensure_one()
        if not self.yeni_bom_id:
            raise UserError(self.env._('Önce revizyonu başlatın.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'mrp.bom', 'res_id': self.yeni_bom_id.id,
            'view_mode': 'form', 'target': 'current', 'name': self.env._('Revizyon: %s', self.name),
            'context': {'active_test': False},
        }

    def _son_asamaya_geldi(self):
        self.ensure_one()
        if self.durum == 'taslak' and self.uygulama == 'urun':
            self.durum = 'islemde'
        if self.yururluk == 'tarih' and self.yururluk_tarihi and self.yururluk_tarihi > fields.Datetime.now():
            self.zamanlandi = True
            self.message_post(body=self.env._('Onaylandı; %s tarihinde yürürlüğe girecek.',
                                              fields.Datetime.to_string(self.yururluk_tarihi)))
            return
        self._uygula()

    def _uygula(self):
        self.ensure_one()
        if self.durum == 'bitti':
            return
        tmpl = self.product_tmpl_id
        if self.uygulama == 'bom':
            if not self.yeni_bom_id:
                raise UserError(self.env._('%s: uygulanacak revizyon yok.', self.name))
            if self.bom_id and not self.bom_id.active:
                raise UserError(self.env._(
                    '%(eco)s: %(bom)s başka bir değişiklikle güncellenmiş. Bu değişikliği iptal edip güncel reçeteden yeniden başlatın.',
                    eco=self.name, bom=self.bom_id.display_name))
            self._degisiklik_hesapla()
            self.yeni_bom_id.active = True
            if self.bom_id:
                self.bom_id.action_archive()
                self.yeni_bom_id._atlas_bagli_kayitlari_tasi(self.bom_id)
            tmpl.atlas_versiyon = self.yeni_bom_id.atlas_versiyon
        else:
            tmpl.atlas_versiyon = tmpl.atlas_versiyon + 1
        for ek in self.dokuman_ids:
            # Ürüne bağlanan ek dosyadan product modülü ürün dokümanını kendisi oluşturur
            ek.copy({'res_model': 'product.template', 'res_id': tmpl.id})
        self.write({'durum': 'bitti', 'zamanlandi': False, 'uygulama_tarihi': fields.Datetime.now()})
        self.activity_ids.unlink()
        self.message_post(body=self.env._('Değişiklik uygulandı: %(urun)s sürüm %(ver)s.',
                                          urun=tmpl.display_name, ver=tmpl.atlas_versiyon))

    @api.model
    def _cron_yururluk(self):
        for eco in self.search([('zamanlandi', '=', True), ('durum', '=', 'islemde'),
                                ('yururluk_tarihi', '<=', fields.Datetime.now())]):
            try:
                with self.env.cr.savepoint():
                    eco._uygula()
            except UserError as hata:
                eco.message_post(body=self.env._('Yürürlük uygulaması başarısız: %s', hata))

    def action_simdi_uygula(self):
        for eco in self.filtered('zamanlandi'):
            eco._uygula()
        return True

    def action_iptal(self):
        for eco in self:
            if eco.durum == 'bitti':
                raise UserError(self.env._('%s uygulandı; iptal edilemez.', eco.name))
            if eco.yeni_bom_id and not eco.yeni_bom_id.active:
                yeni = eco.yeni_bom_id
                eco.yeni_bom_id = False
                yeni.unlink()
            eco.write({'durum': 'iptal', 'zamanlandi': False})
            eco.activity_ids.unlink()
        return True

    def action_taslaga_al(self):
        self.filtered(lambda e: e.durum == 'iptal').write({'durum': 'taslak'})
        return True

    # -------------------------------------------------------------------------
    # Değişiklik özeti
    # -------------------------------------------------------------------------

    @api.model
    def _bilesen_ozet(self, bom):
        ozet = {}
        for line in bom.bom_line_ids:
            qty = line.uom_id._compute_quantity(line.product_qty, line.product_id.uom_id)
            ozet[line.product_id] = ozet.get(line.product_id, 0.0) + qty
        return ozet

    @api.model
    def _operasyon_ozet(self, bom):
        return {op.name: op for op in bom.with_context(active_test=False).operation_ids}

    def _degisiklik_hesapla(self):
        """Mevcut ve yeni reçete arasındaki bileşen / operasyon farklarını yeniden yazar."""
        for eco in self:
            if eco.durum == 'bitti' or eco.uygulama != 'bom':
                continue
            eski, yeni = eco._bilesen_ozet(eco.bom_id), eco._bilesen_ozet(eco.yeni_bom_id)
            bilesenler = []
            for product in dict.fromkeys(list(eski) + list(yeni)):
                e, y = eski.get(product, 0.0), yeni.get(product, 0.0)
                if product.uom_id.compare(e, y) == 0:
                    continue
                tip = 'ekle' if product not in eski else 'sil' if product not in yeni else 'guncelle'
                bilesenler.append(Command.create({'tip': tip, 'product_id': product.id, 'eski_miktar': e, 'yeni_miktar': y}))
            eski_op, yeni_op = eco._operasyon_ozet(eco.bom_id), eco._operasyon_ozet(eco.yeni_bom_id)
            rotalar = []
            for ad in dict.fromkeys(list(eski_op) + list(yeni_op)):
                e, y = eski_op.get(ad), yeni_op.get(ad)
                if e and y and e.workcenter_id == y.workcenter_id and e.time_cycle_manual == y.time_cycle_manual:
                    continue
                rotalar.append(Command.create({
                    'tip': 'ekle' if not e else 'sil' if not y else 'guncelle', 'operasyon': ad,
                    'eski_workcenter_id': e.workcenter_id.id if e else False,
                    'yeni_workcenter_id': y.workcenter_id.id if y else False,
                    'eski_sure': e.time_cycle_manual if e else 0.0, 'yeni_sure': y.time_cycle_manual if y else 0.0}))
            eco.with_context(atlas_plm_hesapla=True).write({
                'bom_degisiklik_ids': [Command.clear()] + bilesenler,
                'rota_degisiklik_ids': [Command.clear()] + rotalar})

    def action_degisiklik_hesapla(self):
        self._degisiklik_hesapla()
        return True

    def action_yazdir(self):
        return self.env.ref('atlas_plm.action_report_eco').report_action(self)


class AtlasPlmEcoOnay(models.Model):
    _name = 'atlas.plm.eco.onay'
    _description = 'ECO Onayı'
    _order = 'id'

    eco_id = fields.Many2one('atlas.plm.eco', required=True, ondelete='cascade', index=True)
    sablon_id = fields.Many2one('atlas.plm.onay.sablon', string='Şablon', required=True, ondelete='restrict')
    name = fields.Char(related='sablon_id.name', string='Onay')
    asama_id = fields.Many2one(related='sablon_id.asama_id', store=True, string='Aşama')
    onay_tipi = fields.Selection(related='sablon_id.onay_tipi', string='Onay Tipi')
    durum = fields.Selection([('bekliyor', 'Bekliyor'), ('onaylandi', 'Onaylandı'), ('reddedildi', 'Reddedildi'), ('yorum', 'Yorum')],
                             string='Durum', default='bekliyor', required=True)
    user_id = fields.Many2one('res.users', string='Karar Veren', readonly=True)
    tarih = fields.Datetime(string='Tarih', readonly=True)
    onaylayabilir = fields.Boolean(compute='_compute_onaylayabilir')

    def _compute_onaylayabilir(self):
        for onay in self:
            onay.onaylayabilir = onay.onay_tipi != 'yorum' and onay.sablon_id._onaylayabilir(self.env.user) \
                and onay.eco_id.durum in ('taslak', 'islemde') and onay.asama_id == onay.eco_id.asama_id

    def _karar(self, durum):
        for onay in self:
            if not onay.sablon_id._onaylayabilir(self.env.user):
                raise UserError(self.env._('"%s" onayını vermeye yetkiniz yok.', onay.name))
            onay.write({'durum': durum, 'user_id': self.env.uid, 'tarih': fields.Datetime.now()})
            eco = onay.eco_id
            # Bu onay için açılan aktiviteler (tüm onaylayıcılarda) kapanır
            ozet = self.env._('ECO onayı: %s', onay.name)
            eco.activity_ids.filtered(lambda a: a.summary == ozet).action_feedback(
                feedback=dict(self._fields['durum'].selection)[durum])
            eco.message_post(body=self.env._('%(onay)s: %(karar)s', onay=onay.name,
                                             karar=dict(self._fields['durum'].selection)[durum]))

    def action_onayla(self):
        self._karar('onaylandi')
        return True

    def action_reddet(self):
        self._karar('reddedildi')
        return True


class AtlasPlmEcoBomDegisiklik(models.Model):
    _name = 'atlas.plm.eco.bom.degisiklik'
    _description = 'ECO Bileşen Değişikliği'
    _order = 'id'

    eco_id = fields.Many2one('atlas.plm.eco', required=True, ondelete='cascade', index=True)
    tip = fields.Selection([('ekle', 'Eklendi'), ('sil', 'Çıkarıldı'), ('guncelle', 'Miktar değişti')], string='Değişiklik', required=True)
    product_id = fields.Many2one('product.product', string='Bileşen', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='Birim')
    eski_miktar = fields.Float(string='Eski Miktar', digits='Product Unit')
    yeni_miktar = fields.Float(string='Yeni Miktar', digits='Product Unit')
    fark = fields.Float(string='Fark', compute='_compute_fark', digits='Product Unit')

    @api.depends('eski_miktar', 'yeni_miktar')
    def _compute_fark(self):
        for satir in self:
            satir.fark = satir.yeni_miktar - satir.eski_miktar


class AtlasPlmEcoRotaDegisiklik(models.Model):
    _name = 'atlas.plm.eco.rota.degisiklik'
    _description = 'ECO Operasyon Değişikliği'
    _order = 'id'

    eco_id = fields.Many2one('atlas.plm.eco', required=True, ondelete='cascade', index=True)
    tip = fields.Selection([('ekle', 'Eklendi'), ('sil', 'Çıkarıldı'), ('guncelle', 'Güncellendi')], string='Değişiklik', required=True)
    operasyon = fields.Char(string='Operasyon', required=True)
    eski_workcenter_id = fields.Many2one('mrp.workcenter', string='Eski İş Merkezi')
    yeni_workcenter_id = fields.Many2one('mrp.workcenter', string='Yeni İş Merkezi')
    eski_sure = fields.Float(string='Eski Süre (dk)')
    yeni_sure = fields.Float(string='Yeni Süre (dk)')
