import ast
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

ONCELIKLER = [('0', 'Düşük'), ('1', 'Normal'), ('2', 'Yüksek'), ('3', 'Acil')]


class AtlasDestekEkip(models.Model):
    _name = 'atlas.destek.ekip'
    _description = 'Destek Ekibi'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _order = 'sequence, id'

    name = fields.Char(string='Ekip', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    color = fields.Integer(string='Renk')
    user_ids = fields.Many2many('res.users', string='Üyeler', domain=[('share', '=', False)])
    atama = fields.Selection([('yok', 'Atama yok'), ('sirayla', 'Sırayla'), ('yuk', 'En az açık talebi olana')],
                             string='Otomatik Atama', default='yuk', required=True)
    calendar_id = fields.Many2one('resource.calendar', string='Çalışma Takvimi', default=lambda self: self.env.company.resource_calendar_id,
                                  help='SLA süreleri bu takvimin çalışma saatleriyle hesaplanır.')
    portal_gorunur = fields.Boolean(string='Portalda Talep Açılabilir', default=True)
    memnuniyet = fields.Boolean(string='Kapanışta Memnuniyet Anketi', default=True)
    son_atanan_id = fields.Many2one('res.users', string='Son Atanan', readonly=True)
    talep_ids = fields.One2many('atlas.destek.talep', 'ekip_id', string='Talepler')
    acik_sayisi = fields.Integer(compute='_compute_sayilar', string='Açık')
    atanmamis_sayisi = fields.Integer(compute='_compute_sayilar', string='Atanmamış')
    acil_sayisi = fields.Integer(compute='_compute_sayilar', string='Acil')
    sla_ihlal_sayisi = fields.Integer(compute='_compute_sayilar', string='SLA İhlali')

    def _compute_sayilar(self):
        Talep = self.env['atlas.destek.talep']
        for ekip in self:
            acik = Talep.search([('ekip_id', '=', ekip.id), ('kapali', '=', False)])
            ekip.acik_sayisi = len(acik)
            ekip.atanmamis_sayisi = len(acik.filtered(lambda t: not t.user_id))
            ekip.acil_sayisi = len(acik.filtered(lambda t: t.oncelik == '3'))
            ekip.sla_ihlal_sayisi = len(acik.filtered('sla_ihlal'))

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('atlas.destek.talep').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or '{}')
            defaults['ekip_id'] = self.id
        return values

    def _atanacak(self):
        """Otomatik atama: sırayla veya en az açık talebi olan üye."""
        self.ensure_one()
        uyeler = self.user_ids.sorted('id')
        if self.atama == 'yok' or not uyeler:
            return self.env['res.users']
        if self.atama == 'sirayla':
            sonraki = uyeler.filtered(lambda u: u.id > self.son_atanan_id.id)[:1] or uyeler[:1]
            self.sudo().son_atanan_id = sonraki
            return sonraki
        yuk = dict(self.env['atlas.destek.talep']._read_group(
            [('ekip_id', '=', self.id), ('kapali', '=', False), ('user_id', 'in', uyeler.ids)], ['user_id'], ['__count']))
        return min(uyeler, key=lambda u: (yuk.get(u, 0), u.id))

    def action_talepler(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_destek.action_atlas_destek_talep')
        action['domain'] = [('ekip_id', '=', self.id)]
        action['context'] = {'default_ekip_id': self.id, 'search_default_acik': 1}
        return action


class AtlasDestekAsama(models.Model):
    _name = 'atlas.destek.asama'
    _description = 'Destek Aşaması'
    _order = 'sequence, id'

    name = fields.Char(string='Aşama', required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string="Kanban'da Katla")
    kapali = fields.Boolean(string='Kapanış Aşaması')
    ekip_ids = fields.Many2many('atlas.destek.ekip', string='Ekipler', help='Boşsa tüm ekiplerde.')
    template_id = fields.Many2one('mail.template', string='Müşteriye E-posta', domain="[('model', '=', 'atlas.destek.talep')]",
                                  help='Talep bu aşamaya gelince müşteriye gönderilir.')


class AtlasDestekTip(models.Model):
    _name = 'atlas.destek.tip'
    _description = 'Talep Tipi'
    _order = 'sequence, id'

    name = fields.Char(string='Tip', required=True)
    sequence = fields.Integer(default=10)


class AtlasDestekEtiket(models.Model):
    _name = 'atlas.destek.etiket'
    _description = 'Destek Etiketi'

    name = fields.Char(string='Etiket', required=True)
    color = fields.Integer(string='Renk')


class AtlasDestekSla(models.Model):
    _name = 'atlas.destek.sla'
    _description = 'SLA Politikası'
    _order = 'sequence, id'

    name = fields.Char(string='Politika', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    ekip_id = fields.Many2one('atlas.destek.ekip', string='Ekip', required=True)
    tip_ids = fields.Many2many('atlas.destek.tip', string='Tipler', help='Boşsa tüm tipler.')
    oncelik = fields.Selection(ONCELIKLER, string='En Az Öncelik', default='0', required=True)
    hedef_asama_id = fields.Many2one('atlas.destek.asama', string='Hedef Aşama', required=True,
                                     help='Talep bu aşamaya (veya sonrasına) süre içinde gelmeli.')
    sure_saat = fields.Float(string='Süre (çalışma saati)', required=True, default=8.0)

    def _uygun(self, talep):
        self.ensure_one()
        return (self.ekip_id == talep.ekip_id and talep.oncelik >= self.oncelik
                and (not self.tip_ids or talep.tip_id in self.tip_ids))


class AtlasDestekSlaDurum(models.Model):
    _name = 'atlas.destek.sla.durum'
    _description = 'Talep SLA Durumu'
    _order = 'deadline'

    talep_id = fields.Many2one('atlas.destek.talep', required=True, ondelete='cascade', index=True)
    sla_id = fields.Many2one('atlas.destek.sla', string='SLA', required=True, ondelete='cascade')
    hedef_asama_id = fields.Many2one(related='sla_id.hedef_asama_id', string='Hedef Aşama')
    deadline = fields.Datetime(string='Son Tarih')
    ulasildi = fields.Datetime(string='Ulaşıldı')
    durum = fields.Selection([('devam', 'Devam ediyor'), ('basarili', 'Zamanında'), ('ihlal', 'İhlal')], string='Durum',
                             compute='_compute_durum', store=True)
    ekip_id = fields.Many2one(related='talep_id.ekip_id', store=True, string='Ekip')
    user_id = fields.Many2one(related='talep_id.user_id', store=True, string='Sorumlu')

    @api.depends('deadline', 'ulasildi')
    def _compute_durum(self):
        simdi = fields.Datetime.now()
        for d in self:
            if d.ulasildi:
                d.durum = 'basarili' if not d.deadline or d.ulasildi <= d.deadline else 'ihlal'
            else:
                d.durum = 'ihlal' if d.deadline and d.deadline < simdi else 'devam'


class AtlasDestekTalep(models.Model):
    _name = 'atlas.destek.talep'
    _description = 'Destek Talebi'
    _inherit = ['portal.mixin', 'mail.activity.mixin', 'rating.mixin']
    _order = 'oncelik desc, id desc'
    _primary_email = 'email'
    _mail_post_access = 'read'

    name = fields.Char(string='Talep No', required=True, copy=False, readonly=True, default='/')
    baslik = fields.Char(string='Konu', required=True, tracking=True)
    aciklama = fields.Html(string='Açıklama')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    ekip_id = fields.Many2one('atlas.destek.ekip', string='Ekip', required=True, tracking=True, index=True,
                              default=lambda self: self.env['atlas.destek.ekip'].search([], limit=1))
    user_id = fields.Many2one('res.users', string='Sorumlu', tracking=True, index=True, domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', string='Müşteri', tracking=True, index=True)
    email = fields.Char(string='E-posta', compute='_compute_iletisim', store=True, readonly=False)
    telefon = fields.Char(string='Telefon', compute='_compute_iletisim', store=True, readonly=False)
    asama_id = fields.Many2one('atlas.destek.asama', string='Aşama', tracking=True, index=True, copy=False,
                               group_expand='_read_group_asama_ids', compute='_compute_asama_id', store=True, readonly=False,
                               domain="['|', ('ekip_ids', '=', False), ('ekip_ids', 'in', ekip_id)]")
    kapali = fields.Boolean(related='asama_id.kapali', store=True, string='Kapalı')
    kapanis_tarihi = fields.Datetime(string='Kapanış', readonly=True, copy=False)
    ilk_yanit = fields.Datetime(string='İlk Yanıt', readonly=True, copy=False)
    oncelik = fields.Selection(ONCELIKLER, string='Öncelik', default='1', tracking=True, index=True)
    tip_id = fields.Many2one('atlas.destek.tip', string='Tip')
    etiket_ids = fields.Many2many('atlas.destek.etiket', string='Etiketler')
    color = fields.Integer(string='Renk')
    kanal = fields.Selection([('eposta', 'E-posta'), ('portal', 'Portal'), ('telefon', 'Telefon'), ('elle', 'Elle')],
                             string='Kanal', default='elle')
    sla_durum_ids = fields.One2many('atlas.destek.sla.durum', 'talep_id', string='SLA')
    sla_deadline = fields.Datetime(string='SLA Son Tarih', compute='_compute_sla', store=True)
    sla_ihlal = fields.Boolean(string='SLA İhlali', compute='_compute_sla', store=True)
    cozum_saat = fields.Float(string='Çözüm Süresi (saat)', compute='_compute_cozum_saat', store=True, aggregator='avg')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.destek.talep') or '/'
        talepler = super().create(vals_list)
        for talep in talepler:
            if not talep.user_id and talep.ekip_id:
                talep.user_id = talep.ekip_id._atanacak()
            if talep.partner_id:
                talep.message_subscribe(partner_ids=talep.partner_id.ids)
            talep._sla_uygula()
        return talepler

    def write(self, vals):
        if 'asama_id' in vals:
            asama = self.env['atlas.destek.asama'].browse(vals['asama_id'])
            vals['kapanis_tarihi'] = fields.Datetime.now() if asama.kapali else False
        res = super().write(vals)
        if 'asama_id' in vals:
            for talep in self:
                talep._sla_asama_kontrol()
                if talep.asama_id.template_id:
                    talep.message_post_with_source(talep.asama_id.template_id, subtype_xmlid='mail.mt_comment')
                if talep.kapali and talep.ekip_id.memnuniyet and talep.partner_id:
                    talep._memnuniyet_iste()
        if vals.keys() & {'ekip_id', 'oncelik', 'tip_id'}:
            self._sla_uygula()
        return res

    @api.model
    def _read_group_asama_ids(self, stages, domain):
        return stages.search([])

    @api.depends('ekip_id')
    def _compute_asama_id(self):
        for talep in self:
            if not talep.asama_id or (talep.asama_id.ekip_ids and talep.ekip_id not in talep.asama_id.ekip_ids):
                talep.asama_id = self.env['atlas.destek.asama'].search(
                    ['|', ('ekip_ids', '=', False), ('ekip_ids', 'in', talep.ekip_id.ids)], limit=1)

    @api.depends('partner_id')
    def _compute_iletisim(self):
        for talep in self:
            if talep.partner_id:
                talep.email = talep.partner_id.email or talep.email
                talep.telefon = talep.partner_id.phone or talep.telefon

    @api.depends('sla_durum_ids.deadline', 'sla_durum_ids.durum')
    def _compute_sla(self):
        for talep in self:
            devam = talep.sla_durum_ids.filtered(lambda d: d.durum == 'devam')
            talep.sla_deadline = min(devam.mapped('deadline')) if devam and all(devam.mapped('deadline')) else False
            talep.sla_ihlal = any(d.durum == 'ihlal' for d in talep.sla_durum_ids)

    @api.depends('create_date', 'kapanis_tarihi')
    def _compute_cozum_saat(self):
        for talep in self:
            talep.cozum_saat = ((talep.kapanis_tarihi - talep.create_date).total_seconds() / 3600
                                if talep.kapanis_tarihi and talep.create_date else 0.0)

    def _compute_access_url(self):
        super()._compute_access_url()
        for talep in self:
            talep.access_url = f'/my/destek/{talep.id}'

    def _compute_display_name(self):
        for talep in self:
            talep.display_name = f'{talep.name} {talep.baslik or ""}'.strip()

    # -------------------------------------------------------------------------
    # SLA
    # -------------------------------------------------------------------------

    def _sla_son_tarih(self, sla, baslangic):
        takvim = self.ekip_id.calendar_id
        if takvim:
            son = takvim.plan_hours(sla.sure_saat, baslangic, compute_leaves=True)
            if son:
                return son.replace(tzinfo=None) if son.tzinfo else son
        return baslangic + timedelta(hours=sla.sure_saat)

    def _sla_uygula(self):
        """Talebe uyan SLA politikalarını ekler (uymayanlar, ulaşılmamışsa kaldırılır)."""
        Durum = self.env['atlas.destek.sla.durum']
        for talep in self:
            uygun = self.env['atlas.destek.sla'].search([('ekip_id', '=', talep.ekip_id.id)]).filtered(lambda s: s._uygun(talep))
            talep.sla_durum_ids.filtered(lambda d: d.sla_id not in uygun and not d.ulasildi).unlink()
            baslangic = talep.create_date or fields.Datetime.now()
            for sla in uygun - talep.sla_durum_ids.sla_id:
                Durum.create({'talep_id': talep.id, 'sla_id': sla.id, 'deadline': talep._sla_son_tarih(sla, baslangic)})
            talep._sla_asama_kontrol()

    def _sla_asama_kontrol(self):
        simdi = fields.Datetime.now()
        for talep in self:
            for durum in talep.sla_durum_ids.filtered(lambda d: not d.ulasildi):
                if talep.asama_id.sequence >= durum.hedef_asama_id.sequence:
                    durum.ulasildi = simdi

    @api.model
    def _cron_sla(self):
        """Süresi geçen SLA durumlarını 'ihlal' olarak günceller."""
        durumlar = self.env['atlas.destek.sla.durum'].search([('durum', '=', 'devam'), ('deadline', '<', fields.Datetime.now())])
        durumlar._compute_durum()
        durumlar.talep_id._compute_sla()

    # -------------------------------------------------------------------------
    # E-posta ve memnuniyet
    # -------------------------------------------------------------------------

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        custom_values = dict(custom_values or {})
        if not msg_dict.get('author_id') and msg_dict.get('email_from'):
            yazar = self.env['mail.thread']._partner_find_from_emails_single([msg_dict['email_from']], no_create=False)
            msg_dict['author_id'] = yazar.id
        custom_values.setdefault('baslik', msg_dict.get('subject') or self.env._('(Konusuz)'))
        custom_values.setdefault('partner_id', msg_dict.get('author_id'))
        custom_values.setdefault('aciklama', msg_dict.get('body'))
        custom_values.setdefault('kanal', 'eposta')
        return super(AtlasDestekTalep, self.with_context(mail_create_nolog=True)).message_new(msg_dict, custom_values)

    def _message_post_after_hook(self, message):
        # Personelin müşteriye ilk yanıtı
        if not self.ilk_yanit and message.message_type == 'comment' and message.author_id.user_ids.filtered(lambda u: not u.share):
            if message.subtype_id == self.env.ref('mail.mt_comment'):
                self.sudo().ilk_yanit = fields.Datetime.now()
        return super()._message_post_after_hook(message)

    def _rating_get_partner(self):
        return self.partner_id

    def _rating_get_operator(self):
        return self.user_id.partner_id

    def _memnuniyet_iste(self):
        self.ensure_one()
        template = self.env.ref('atlas_destek.mail_template_memnuniyet', raise_if_not_found=False)
        if template:
            self.with_context(force_send=False).message_post_with_source(template, subtype_xmlid='mail.mt_comment')

    def action_ata_bana(self):
        self.write({'user_id': self.env.uid})
        return True
