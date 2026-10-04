import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

AKTIVITE_TURLERI = [('eposta', 'E-posta Gönder'), ('eylem', 'Sunucu Eylemi')]
TETIKLER = [
    ('baslangic', 'Kampanya başlangıcı'),
    ('sonra', 'Önceki adımdan sonra'),
    ('acildi', 'E-posta açıldı'),
    ('acilmadi', 'E-posta açılmadı'),
    ('tiklandi', 'Bağlantıya tıklandı'),
    ('tiklanmadi', 'Bağlantıya tıklanmadı'),
    ('yanitlandi', 'E-postaya yanıt verildi'),
    ('yanitlanmadi', 'E-postaya yanıt verilmedi'),
]
OLAY_TETIKLERI = {'acildi': 'open_datetime', 'tiklandi': 'links_click_datetime', 'yanitlandi': 'reply_datetime'}
OLUMSUZ_TETIKLER = {'acilmadi': 'open_datetime', 'tiklanmadi': 'links_click_datetime', 'yanitlanmadi': 'reply_datetime'}
OLAY_SURESI = timedelta(days=30)  # olay tetikleyicileri en fazla bu kadar beklenir
BIRIMLER = [('saat', 'Saat'), ('gun', 'Gün'), ('hafta', 'Hafta')]
IZ_DURUMLARI = [('bekliyor', 'Bekliyor'), ('yapildi', 'Yapıldı'), ('atlandi', 'Atlandı'), ('iptal', 'İptal'), ('hata', 'Hata')]


class AtlasPazarlamaKampanya(models.Model):
    _name = 'atlas.pazarlama.kampanya'
    _description = 'Pazarlama Otomasyonu Kampanyası'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(string='Kampanya', required=True, tracking=True)
    model_id = fields.Many2one('ir.model', string='Hedef', required=True, ondelete='cascade',
                               domain=[('is_mailing_enabled', '=', True)],
                               default=lambda self: self.env.ref('base.model_res_partner', raise_if_not_found=False))
    model_name = fields.Char(related='model_id.model', string='Model Adı')
    domain = fields.Char(string='Kitle Filtresi', default='[]', help='Kampanyaya girecek kayıtlar.')
    benzersiz_alan_id = fields.Many2one('ir.model.fields', string='Tekil Alan', ondelete='set null',
                                        domain="[('model_id', '=', model_id), ('ttype', 'in', ('char', 'many2one'))]",
                                        help='Bu alanın değeri aynı olan kayıtlardan yalnız biri kampanyaya girer (ör. e-posta).')
    durum = fields.Selection([('taslak', 'Taslak'), ('calisiyor', 'Çalışıyor'), ('durduruldu', 'Durduruldu')],
                             string='Durum', default='taslak', required=True, tracking=True, copy=False)
    user_id = fields.Many2one('res.users', string='Sorumlu', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    aktivite_ids = fields.One2many('atlas.pazarlama.aktivite', 'kampanya_id', string='Adımlar', copy=True)
    katilimci_ids = fields.One2many('atlas.pazarlama.katilimci', 'kampanya_id', string='Katılımcılar')
    son_senkron = fields.Datetime(string='Son Kitle Güncellemesi', readonly=True, copy=False)
    katilimci_sayisi = fields.Integer(compute='_compute_sayilar')
    aktif_sayisi = fields.Integer(compute='_compute_sayilar')
    tamamlanan_sayisi = fields.Integer(compute='_compute_sayilar')
    gonderilen_sayisi = fields.Integer(compute='_compute_sayilar', string='Gönderilen E-posta')
    acilan_orani = fields.Integer(compute='_compute_sayilar', string='Açılma %')
    tiklanan_orani = fields.Integer(compute='_compute_sayilar', string='Tıklama %')

    @api.depends('katilimci_ids.durum', 'aktivite_ids.gonderilen')
    def _compute_sayilar(self):
        for k in self:
            k.katilimci_sayisi = len(k.katilimci_ids)
            k.aktif_sayisi = len(k.katilimci_ids.filtered(lambda p: p.durum == 'aktif'))
            k.tamamlanan_sayisi = len(k.katilimci_ids.filtered(lambda p: p.durum == 'tamamlandi'))
            gonderilen = sum(k.aktivite_ids.mapped('gonderilen'))
            k.gonderilen_sayisi = gonderilen
            k.acilan_orani = round(100.0 * sum(k.aktivite_ids.mapped('acilan')) / gonderilen) if gonderilen else 0
            k.tiklanan_orani = round(100.0 * sum(k.aktivite_ids.mapped('tiklanan')) / gonderilen) if gonderilen else 0

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for k in self:
            try:
                self.env[k.model_id.model].search_count(k._kitle_domain(), limit=1)
            except Exception as hata:  # noqa: BLE001
                raise ValidationError(self.env._('Kitle filtresi geçersiz: %s', hata)) from hata

    def _kitle_domain(self):
        self.ensure_one()
        return safe_eval(self.domain or '[]', {'uid': self.env.uid})

    def write(self, vals):
        if 'model_id' in vals and any(k.katilimci_ids for k in self):
            raise UserError(self.env._('Katılımcısı olan kampanyanın hedef modeli değiştirilemez.'))
        return super().write(vals)

    # -------------------------------------------------------------------------
    # Durum
    # -------------------------------------------------------------------------

    def action_baslat(self):
        for k in self:
            if not k.aktivite_ids.filtered(lambda a: not a.parent_id):
                raise UserError(self.env._('%s kampanyasında başlangıç adımı yok.', k.name))
            for aktivite in k.aktivite_ids.filtered(lambda a: a.tur == 'eposta'):
                aktivite._mailing_hazirla()
            k.durum = 'calisiyor'
        return True

    def action_durdur(self):
        self.write({'durum': 'durduruldu'})
        return True

    def action_simdi_calistir(self):
        for k in self:
            if k.durum != 'calisiyor':
                raise UserError(self.env._('Önce kampanyayı başlatın.'))
            k._kitle_senkron()
            k._izleri_isle()
        return True

    # -------------------------------------------------------------------------
    # Motor
    # -------------------------------------------------------------------------

    def _kitle_senkron(self):
        """Filtreye uyan yeni kayıtları katılımcı yapar ve başlangıç adımlarını planlar."""
        self.ensure_one()
        Model = self.env[self.model_id.model]
        mevcut = set(self.katilimci_ids.mapped('res_id'))
        kayitlar = Model.search(self._kitle_domain())
        yeni = kayitlar.filtered(lambda r: r.id not in mevcut)
        if self.benzersiz_alan_id and yeni:
            alan = self.benzersiz_alan_id.name
            gorulen = {self._benzersiz_deger(r, alan) for r in Model.browse(list(mevcut)).exists()}
            secilen = Model
            for kayit in yeni:
                deger = self._benzersiz_deger(kayit, alan)
                if deger and deger in gorulen:
                    continue
                gorulen.add(deger)
                secilen |= kayit
            yeni = secilen
        simdi = fields.Datetime.now()
        koklar = self.aktivite_ids.filtered(lambda a: not a.parent_id)
        Katilimci = self.env['atlas.pazarlama.katilimci']
        for kayit in yeni:
            katilimci = Katilimci.create({'kampanya_id': self.id, 'res_id': kayit.id, 'model_name': self.model_id.model})
            self.env['atlas.pazarlama.iz'].create([
                {'katilimci_id': katilimci.id, 'aktivite_id': a.id, 'planlanan': simdi + a._bekleme()} for a in koklar])
        self.son_senkron = simdi
        return len(yeni)

    @staticmethod
    def _benzersiz_deger(kayit, alan):
        deger = kayit[alan]
        if isinstance(deger, models.BaseModel):
            return deger.id or False
        return (deger or '').strip().lower() or False

    def _izleri_isle(self):
        self.ensure_one()
        Iz = self.env['atlas.pazarlama.iz']
        simdi = fields.Datetime.now()
        bekleyen = Iz.search([('kampanya_id', '=', self.id), ('durum', '=', 'bekliyor')])
        # Olay bekleyen adımlar: olay gerçekleştiyse planlanan zamanı belirlenir
        for iz in bekleyen.filtered(lambda i: i.aktivite_id.tetik in OLAY_TETIKLERI and not i.planlanan):
            olay = iz.parent_iz_id.mailing_trace_id[OLAY_TETIKLERI[iz.aktivite_id.tetik]]
            if olay:
                iz.planlanan = olay + iz.aktivite_id._bekleme()
            elif iz.parent_iz_id.yapilma and iz.parent_iz_id.yapilma + OLAY_SURESI < simdi:
                iz.write({'durum': 'iptal', 'sonuc': self.env._('Olay gerçekleşmedi'), 'yapilma': simdi})
        vadesi = bekleyen.filtered(lambda i: i.planlanan and i.planlanan <= simdi and i.katilimci_id.durum == 'aktif')
        for aktivite, izler in vadesi.grouped('aktivite_id').items():
            try:
                with self.env.cr.savepoint():
                    aktivite._calistir(izler)
            except Exception as hata:  # noqa: BLE001
                _logger.exception('Pazarlama adımı çalıştırılamadı: %s', aktivite.display_name)
                izler.write({'durum': 'hata', 'sonuc': str(hata)[:500], 'yapilma': fields.Datetime.now()})
        self.katilimci_ids.filtered(lambda p: p.durum == 'aktif')._bitis_kontrol()

    @api.model
    def _cron_calistir(self):
        for kampanya in self.search([('durum', '=', 'calisiyor')]):
            try:
                with self.env.cr.savepoint():
                    kampanya._kitle_senkron()
                    kampanya._izleri_isle()
            except Exception:  # noqa: BLE001
                _logger.exception('Pazarlama kampanyası işlenemedi: %s', kampanya.name)

    def action_katilimcilar(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.pazarlama.katilimci', 'view_mode': 'list,form',
                'domain': [('kampanya_id', '=', self.id)], 'name': self.env._('Katılımcılar'),
                'context': {'default_kampanya_id': self.id}}


class AtlasPazarlamaAktivite(models.Model):
    _name = 'atlas.pazarlama.aktivite'
    _description = 'Pazarlama Otomasyonu Adımı'
    _order = 'kampanya_id, sequence, id'
    _parent_store = True

    kampanya_id = fields.Many2one('atlas.pazarlama.kampanya', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Adım', required=True)
    tur = fields.Selection(AKTIVITE_TURLERI, string='Tür', required=True, default='eposta')
    parent_id = fields.Many2one('atlas.pazarlama.aktivite', string='Önceki Adım', ondelete='cascade', index=True,
                                domain="[('kampanya_id', '=', kampanya_id), ('id', '!=', id)]")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('atlas.pazarlama.aktivite', 'parent_id', string='Sonraki Adımlar')
    tetik = fields.Selection(TETIKLER, string='Tetikleyici', required=True, default='baslangic')
    bekleme = fields.Integer(string='Bekleme', default=0)
    bekleme_birim = fields.Selection(BIRIMLER, string='Birim', default='gun', required=True)
    filtre = fields.Char(string='Adım Filtresi', default='[]', help='Çalışma anında bu filtreye uymayan katılımcı için adım atlanır.')
    konu = fields.Char(string='Konu')
    govde = fields.Html(string='E-posta İçeriği', sanitize=False)
    mailing_id = fields.Many2one('mailing.mailing', string='Toplu E-posta', readonly=True, copy=False, ondelete='set null')
    eylem_id = fields.Many2one('ir.actions.server', string='Sunucu Eylemi', domain="[('model_id', '=', model_id)]")
    model_id = fields.Many2one(related='kampanya_id.model_id')
    model_name = fields.Char(related='kampanya_id.model_id.model', string='Model Adı')
    iz_ids = fields.One2many('atlas.pazarlama.iz', 'aktivite_id', string='İzler')
    bekleyen = fields.Integer(compute='_compute_istatistik', string='Bekleyen')
    yapilan = fields.Integer(compute='_compute_istatistik', string='Yapılan')
    atlanan = fields.Integer(compute='_compute_istatistik', string='Atlanan')
    gonderilen = fields.Integer(compute='_compute_istatistik', string='Gönderilen')
    acilan = fields.Integer(compute='_compute_istatistik', string='Açılan')
    tiklanan = fields.Integer(compute='_compute_istatistik', string='Tıklanan')
    yanitlanan = fields.Integer(compute='_compute_istatistik', string='Yanıtlanan')

    @api.depends('iz_ids.durum', 'iz_ids.mailing_trace_id.trace_status')
    def _compute_istatistik(self):
        for a in self:
            izler = a.iz_ids
            a.bekleyen = len(izler.filtered(lambda i: i.durum == 'bekliyor'))
            a.yapilan = len(izler.filtered(lambda i: i.durum == 'yapildi'))
            a.atlanan = len(izler.filtered(lambda i: i.durum == 'atlandi'))
            izlemeler = izler.mailing_trace_id
            a.gonderilen = len(izlemeler.filtered(lambda t: t.trace_status not in ('error', 'cancel', 'bounce')))
            a.acilan = len(izlemeler.filtered('open_datetime'))
            a.tiklanan = len(izlemeler.filtered('links_click_datetime'))
            a.yanitlanan = len(izlemeler.filtered('reply_datetime'))

    @api.constrains('parent_id', 'tetik', 'tur')
    def _check_tetik(self):
        for a in self:
            if not a.parent_id and a.tetik != 'baslangic':
                raise ValidationError(self.env._('"%s": önceki adımı olmayan adım kampanya başlangıcında çalışır.', a.name))
            if a.parent_id and a.tetik == 'baslangic':
                raise ValidationError(self.env._('"%s": önceki adımı olan adımın tetikleyicisi "Kampanya başlangıcı" olamaz.', a.name))
            if a.tetik in OLAY_TETIKLERI or a.tetik in OLUMSUZ_TETIKLER:
                if a.parent_id.tur != 'eposta':
                    raise ValidationError(self.env._('"%s": e-posta olayı tetikleyicisi yalnız e-posta adımından sonra kullanılabilir.', a.name))
            if a.parent_id and a.parent_id.kampanya_id != a.kampanya_id:
                raise ValidationError(self.env._('Önceki adım aynı kampanyada olmalı.'))
            if a.tur == 'eylem' and not a.eylem_id:
                raise ValidationError(self.env._('"%s" için sunucu eylemi seçin.', a.name))
        if self._has_cycle():
            raise ValidationError(self.env._('Adımlar döngü oluşturamaz.'))

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id and self.tetik == 'baslangic':
            self.tetik = 'sonra'
        elif not self.parent_id:
            self.tetik = 'baslangic'

    def _bekleme(self):
        self.ensure_one()
        return {'saat': timedelta(hours=self.bekleme), 'gun': timedelta(days=self.bekleme),
                'hafta': timedelta(weeks=self.bekleme)}[self.bekleme_birim]

    def _mailing_hazirla(self):
        """E-posta adımı için takipli toplu e-posta kaydını oluşturur/günceller."""
        self.ensure_one()
        if not self.konu or not self.govde:
            raise UserError(self.env._('"%s" adımının konusu ve içeriği olmalı.', self.name))
        vals = {'subject': self.konu, 'body_html': self.govde, 'mailing_model_id': self.kampanya_id.model_id.id,
                'mailing_domain': '[]', 'user_id': self.kampanya_id.user_id.id or self.env.uid,
                'mailing_type': 'mail', 'keep_archives': True}
        if self.mailing_id:
            self.mailing_id.sudo().write(vals)
        else:
            self.mailing_id = self.env['mailing.mailing'].sudo().create(
                vals).id
        return self.mailing_id

    def write(self, vals):
        res = super().write(vals)
        if {'konu', 'govde'} & set(vals):
            for a in self.filtered(lambda x: x.mailing_id and x.konu and x.govde):
                a.mailing_id.sudo().write({'subject': a.konu, 'body_html': a.govde})
        return res

    def _uygun_kayitlar(self, kayitlar):
        domain = safe_eval(self.filtre or '[]', {'uid': self.env.uid})
        return kayitlar.filtered_domain(domain) if domain else kayitlar

    def _calistir(self, izler):
        """Vadesi gelen izleri çalıştırır; sonraki adımları planlar."""
        self.ensure_one()
        Model = self.env[self.kampanya_id.model_id.model]
        simdi = fields.Datetime.now()
        # Olumsuz tetik: olay gerçekleştiyse adım atlanır
        if self.tetik in OLUMSUZ_TETIKLER:
            olan = izler.filtered(lambda i: i.parent_iz_id.mailing_trace_id[OLUMSUZ_TETIKLER[self.tetik]])
            olan.write({'durum': 'atlandi', 'sonuc': self.env._('Olay gerçekleşti'), 'yapilma': simdi})
            izler -= olan
        kayitlar = Model.browse(izler.mapped('katilimci_id.res_id')).exists()
        uygun = self._uygun_kayitlar(kayitlar)
        atlanan = izler.filtered(lambda i: i.katilimci_id.res_id not in uygun.ids)
        atlanan.write({'durum': 'atlandi', 'sonuc': self.env._('Adım filtresine uymuyor veya kayıt silinmiş'), 'yapilma': simdi})
        izler -= atlanan
        if not izler:
            return
        if self.tur == 'eposta':
            self._eposta_gonder(izler, uygun)
        else:
            self.eylem_id.with_context(active_model=Model._name, active_ids=uygun.ids, active_id=uygun[:1].id).run()
        izler.write({'durum': 'yapildi', 'yapilma': simdi})
        self._sonrakileri_planla(izler)

    def _eposta_gonder(self, izler, kayitlar):
        mailing = self.mailing_id or self._mailing_hazirla()
        mailing = mailing.sudo()
        composer = self.env['mail.compose.message'].sudo().with_context(
            active_ids=kayitlar.ids, default_composition_mode='mass_mail', **mailing._get_mass_mailing_context()
        ).create({
            # her zaman e-posta kuyruğu: gönderim posta cron'unda yapılır
            'auto_delete': False, 'force_send': False, 'body': mailing.body_html, 'composition_mode': 'mass_mail',
            'email_from': mailing.email_from, 'mass_mailing_id': mailing.id, 'model': mailing.mailing_model_real,
            'subject': mailing.subject, 'template_id': False, 'use_exclusion_list': mailing.use_exclusion_list,
            'author_id': self.kampanya_id.user_id.partner_id.id or self.env.user.partner_id.id,
        })
        composer._action_send_mail(auto_commit=False)
        izlemeler = self.env['mailing.trace'].sudo().search([('mass_mailing_id', '=', mailing.id), ('res_id', 'in', kayitlar.ids),
                                                             ('model', '=', mailing.mailing_model_real)], order='id desc')
        trace_by_res = {}
        for t in izlemeler:
            trace_by_res.setdefault(t.res_id, t)
        for iz in izler:
            iz.mailing_trace_id = trace_by_res.get(iz.katilimci_id.res_id)
        if mailing.state != 'done':
            mailing.write({'state': 'done', 'sent_date': fields.Datetime.now()})

    def _sonrakileri_planla(self, izler):
        Iz = self.env['atlas.pazarlama.iz']
        simdi = fields.Datetime.now()
        degerler = []
        for cocuk in self.child_ids:
            for iz in izler:
                planlanan = False if cocuk.tetik in OLAY_TETIKLERI else simdi + cocuk._bekleme()
                degerler.append({'katilimci_id': iz.katilimci_id.id, 'aktivite_id': cocuk.id, 'parent_iz_id': iz.id,
                                 'planlanan': planlanan})
        if degerler:
            Iz.create(degerler)


class AtlasPazarlamaKatilimci(models.Model):
    _name = 'atlas.pazarlama.katilimci'
    _description = 'Pazarlama Otomasyonu Katılımcısı'
    _order = 'id desc'
    _rec_name = 'kayit_adi'

    kampanya_id = fields.Many2one('atlas.pazarlama.kampanya', required=True, ondelete='cascade', index=True)
    model_name = fields.Char(required=True)
    res_id = fields.Many2oneReference(string='Kayıt No', model_field='model_name', required=True, index=True)
    kayit_adi = fields.Char(string='Kayıt', compute='_compute_kayit_adi')
    durum = fields.Selection([('aktif', 'Devam Ediyor'), ('tamamlandi', 'Tamamlandı'), ('cikarildi', 'Çıkarıldı')],
                             string='Durum', default='aktif', required=True, index=True)
    iz_ids = fields.One2many('atlas.pazarlama.iz', 'katilimci_id', string='Adımlar')

    _kayit_uniq = models.Constraint('UNIQUE(kampanya_id, res_id)', 'Bir kayıt kampanyaya bir kez girer.')

    def _compute_kayit_adi(self):
        for p in self:
            kayit = self.env[p.model_name].browse(p.res_id).exists() if p.model_name in self.env else None
            p.kayit_adi = kayit.display_name if kayit else f'#{p.res_id}'

    def _bitis_kontrol(self):
        for p in self:
            if not p.iz_ids.filtered(lambda i: i.durum == 'bekliyor'):
                p.durum = 'tamamlandi'

    def action_cikar(self):
        self.write({'durum': 'cikarildi'})
        self.iz_ids.filtered(lambda i: i.durum == 'bekliyor').write({'durum': 'iptal'})
        return True


class AtlasPazarlamaIz(models.Model):
    _name = 'atlas.pazarlama.iz'
    _description = 'Pazarlama Otomasyonu Adım Kaydı'
    _order = 'planlanan, id'

    katilimci_id = fields.Many2one('atlas.pazarlama.katilimci', required=True, ondelete='cascade', index=True)
    kampanya_id = fields.Many2one(related='katilimci_id.kampanya_id', store=True, index=True)
    aktivite_id = fields.Many2one('atlas.pazarlama.aktivite', required=True, ondelete='cascade', index=True)
    parent_iz_id = fields.Many2one('atlas.pazarlama.iz', string='Önceki', ondelete='cascade')
    planlanan = fields.Datetime(string='Planlanan', index=True)
    yapilma = fields.Datetime(string='Yapıldı')
    durum = fields.Selection(IZ_DURUMLARI, string='Durum', default='bekliyor', required=True, index=True)
    sonuc = fields.Char(string='Sonuç')
    mailing_trace_id = fields.Many2one('mailing.trace', string='E-posta İzi', ondelete='set null')
    eposta_durumu = fields.Selection(related='mailing_trace_id.trace_status', string='E-posta Durumu')
