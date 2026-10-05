import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from ..services import ai
from ..services.metin import benzerlik, fark, tarih_bul, yururluk_bul
from ..services.siniflandirici import ONEM_SIRA, siniflandir
from .temel import ONEMLER

_logger = logging.getLogger(__name__)

DURUMLAR = [('yeni', 'Yeni'), ('inceleniyor', 'İnceleniyor'), ('onaylandi', 'Aksiyon Gerekli'), ('uygulandi', 'Uygulandı'),
            ('reddedildi', 'İlgisiz / Reddedildi'), ('mukerrer', 'Mükerrer')]
ACIK_DURUMLAR = ('yeni', 'inceleniyor', 'onaylandi')


class AtlasMevzuatDegisiklik(models.Model):
    _name = 'atlas.mevzuat.degisiklik'
    _inherit = ['atlas.mevzuat.denetim.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Mevzuat Değişikliği'
    _order = 'tespit_tarihi desc, id desc'
    _denetim_alanlari = ('durum', 'onem', 'kategori_id', 'yururluk_tarihi', 'modul_ids', 'company_ids', 'kirici',
                         'gelistirme_gerekli', 'ayar_gerekli', 'kullanici_aksiyonu', 'inceleme_notu')

    name = fields.Char(string='Başlık', required=True, tracking=True)
    belge_id = fields.Many2one('atlas.mevzuat.belge', string='Belge', ondelete='restrict', index=True)
    kaynak_id = fields.Many2one('atlas.mevzuat.kaynak', string='Kaynak', related='belge_id.kaynak_id', store=True, index=True)
    kurum = fields.Char(related='kaynak_id.kurum', store=True)
    ulke_id = fields.Many2one(related='kaynak_id.ulke_id', store=True)
    url = fields.Char(related='belge_id.url')
    tur = fields.Selection([('yeni', 'Yeni Yayın'), ('guncelleme', 'İçerik Güncellendi')], string='Tür', default='yeni', required=True)
    durum = fields.Selection(DURUMLAR, string='Durum', default='yeni', required=True, tracking=True, index=True)
    onem = fields.Selection(ONEMLER, string='Önem', default='dusuk', required=True, tracking=True, index=True)
    kategori_id = fields.Many2one('atlas.mevzuat.kategori', string='Kategori', tracking=True)
    etiket_ids = fields.Many2many('atlas.mevzuat.etiket', string='Etiketler')
    yayim_tarihi = fields.Date(string='Yayım Tarihi')
    tespit_tarihi = fields.Datetime(string='Tespit Tarihi', default=fields.Datetime.now, readonly=True, index=True)
    yururluk_tarihi = fields.Date(string='Yürürlük Tarihi', tracking=True, index=True)
    ozet = fields.Text(string='Özet / Değerlendirme')
    icerik = fields.Text(related='belge_id.icerik', string='İçerik')
    fark = fields.Text(string='Fark (önceki sürüme göre)', readonly=True)
    # Sınıflandırma
    siniflandirma = fields.Selection([('yok', 'Sınıflandırılmadı'), ('kural', 'Kural'), ('ai', 'AI önerisi (kabul edildi)'),
                                      ('manuel', 'Manuel')], string='Sınıflandırma', default='yok', readonly=True)
    guven = fields.Float(string='Güven (%)', readonly=True, aggregator='avg')
    kural_ids = fields.Many2many('atlas.mevzuat.kural', string='Eşleşen Kurallar', readonly=True)
    kural_aciklama = fields.Char(string='Eşleşmeler', readonly=True)
    kirici = fields.Boolean(string='Kırıcı Değişiklik', tracking=True)
    gelistirme_gerekli = fields.Boolean(string='Geliştirme Gerekli')
    ayar_gerekli = fields.Boolean(string='Ayar/Parametre Gerekli')
    kullanici_aksiyonu = fields.Boolean(string='Kullanıcı Aksiyonu')
    # AI
    ai_durum = fields.Selection([('yok', '—'), ('bekliyor', 'Kuyrukta'), ('tamam', 'Öneri hazır'), ('hata', 'Hata')],
                                string='AI', default='yok', readonly=True, copy=False)
    ai_onerisi = fields.Boolean(string='AI Önerisi', readonly=True, help='Sınıflandırma yapay zekâ önerisiyle yapıldı; insan onayı gerekir.')
    ai_guven = fields.Float(string='AI Güveni (%)', readonly=True)
    ai_ozet = fields.Text(string='AI Özeti', readonly=True)
    ai_onem = fields.Selection(ONEMLER, string='AI Önemi', readonly=True)
    ai_kategori_id = fields.Many2one('atlas.mevzuat.kategori', string='AI Kategorisi', readonly=True)
    ai_modul_ids = fields.Many2many('atlas.mevzuat.modul', 'atlas_mevzuat_degisiklik_ai_modul_rel', string='AI Modülleri', readonly=True)
    ai_yururluk = fields.Date(string='AI Yürürlük', readonly=True)
    ai_ilgisiz = fields.Boolean(string='AI: İlgisiz', readonly=True)
    ai_hata = fields.Char(string='AI Hatası', readonly=True)
    # Etki
    modul_ids = fields.Many2many('atlas.mevzuat.modul', string='Etkilenen Modüller', tracking=True)
    company_ids = fields.Many2many('res.company', string='Etkilenen Şirketler', help='Boşsa tüm şirketler.')
    etki_ids = fields.One2many('atlas.mevzuat.etki', 'degisiklik_id', string='Etki Analizi')
    task_ids = fields.One2many('project.task', 'atlas_mevzuat_degisiklik_id', string='Görevler')
    task_sayisi = fields.Integer(compute='_compute_task_sayisi')
    sorumlu_id = fields.Many2one('res.users', string='Sorumlu', tracking=True, domain=[('share', '=', False)])
    # İnceleme
    inceleyen_id = fields.Many2one('res.users', string='İnceleyen', readonly=True)
    inceleme_tarihi = fields.Datetime(string='İnceleme Tarihi', readonly=True)
    inceleme_notu = fields.Text(string='İnceleme Notu')
    mukerrer_id = fields.Many2one('atlas.mevzuat.degisiklik', string='Aynısı', readonly=True, index=True)
    renk = fields.Integer(compute='_compute_renk')
    gecikti = fields.Boolean(string='Yürürlük Yaklaştı/Geçti', compute='_compute_gecikti', search='_search_gecikti')

    def _compute_task_sayisi(self):
        for d in self:
            d.task_sayisi = len(d.task_ids)

    def _compute_renk(self):
        renk = {'dusuk': 0, 'orta': 3, 'yuksek': 2, 'kritik': 1}
        for d in self:
            d.renk = renk.get(d.onem, 0)

    def _compute_gecikti(self):
        sinir = fields.Date.context_today(self) + timedelta(days=14)
        for d in self:
            d.gecikti = bool(d.yururluk_tarihi and d.yururluk_tarihi <= sinir and d.durum in ACIK_DURUMLAR)

    def _search_gecikti(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        alan = [('yururluk_tarihi', '<=', fields.Date.context_today(self) + timedelta(days=14)), ('durum', 'in', ACIK_DURUMLAR)]
        return alan if (operator == '=') == value else ['!', '&'] + alan

    # ------------------------------------------------------------------ oluşturma ve sınıflandırma
    @api.model
    def _belgeden_olustur(self, belge, tur, onceki_metin=None, zorla=False):
        kaynak = belge.kaynak_id
        metin = belge.icerik or ''
        sonuc = siniflandir(belge.name, metin, self.env['atlas.mevzuat.kural']._motor_kurallari(kaynak))
        if not sonuc and kaynak.sadece_eslesenler and not zorla:
            belge.durum = 'ilgisiz'
            return self.browse()
        vals = {
            'name': belge.name[:500], 'belge_id': belge.id, 'tur': tur,
            'yayim_tarihi': belge.yayim_tarihi or tarih_bul(belge.name),
            'yururluk_tarihi': yururluk_bul(belge.name + ' ' + metin),
            'kategori_id': kaynak.kategori_id.id, 'etiket_ids': [Command.set(kaynak.etiket_ids.ids)],
            'sorumlu_id': self.env['atlas.mevzuat.ayar']._ayar('sorumlu').id or False,
        }
        if tur == 'guncelleme' and onceki_metin is not None:
            vals['fark'] = fark(onceki_metin, belge.name + '\n' + metin)
        vals.update(self._siniflandirma_degerleri(sonuc))
        if self.env['atlas.mevzuat.ayar']._ayar('ai_otomatik'):
            vals['ai_durum'] = 'bekliyor'
        degisiklik = self.create(vals)
        degisiklik._mukerrer_kontrol()
        degisiklik._etkileri_guncelle()
        if degisiklik.durum != 'mukerrer':
            degisiklik._bildir()
        return degisiklik

    @api.model
    def _siniflandirma_degerleri(self, sonuc):
        if not sonuc:
            return {'siniflandirma': 'yok', 'guven': 0, 'kural_ids': [Command.clear()], 'kural_aciklama': False}
        vals = {
            'siniflandirma': 'kural', 'guven': sonuc['guven'], 'onem': sonuc['onem'],
            'kural_ids': [Command.set(sonuc['kural_ids'])], 'kural_aciklama': sonuc['aciklama'][:250],
            'modul_ids': [Command.set(sonuc['modul_ids'])], 'gelistirme_gerekli': sonuc['gelistirme'],
            'ayar_gerekli': sonuc['ayar'], 'kullanici_aksiyonu': sonuc['kullanici'], 'kirici': sonuc['kirici'],
        }
        if sonuc['kategori_id']:
            vals['kategori_id'] = sonuc['kategori_id']
        return vals

    def _mukerrer_kontrol(self):
        """Aynı içerik özeti ya da 30 gün içinde başka kaynakta çok benzer başlık (ör. GİB ve Resmî Gazete'de aynı karar) → mükerrer."""
        for d in self:
            once = fields.Datetime.now() - timedelta(days=30)
            adaylar = self.search([('id', '!=', d.id), ('tespit_tarihi', '>=', once), ('durum', '!=', 'mukerrer'),
                                   ('tur', '=', 'yeni')], limit=300)
            for a in adaylar:
                ayni_ozet = d.belge_id.icerik_ozeti and a.belge_id.icerik_ozeti == d.belge_id.icerik_ozeti
                # Aynı kaynakta benzer başlık mükerrer sayılmaz (ör. GİB'in her ay yayımladığı ÖTV tutarı duyuruları)
                if ayni_ozet or (a.kaynak_id != d.kaynak_id and benzerlik(a.name, d.name) >= 0.92):
                    d.write({'durum': 'mukerrer', 'mukerrer_id': a.id})
                    a.message_post(body=self.env._('Mükerrer kayıt bulundu: %(ad)s (%(kaynak)s)', ad=d.name, kaynak=d.kaynak_id.name))
                    break

    def _etkileri_guncelle(self):
        """Etkilenen modüller için etki satırı açar (varsa dokunmaz); modülden çıkanlar açıksa silinir."""
        Etki = self.env['atlas.mevzuat.etki']
        for d in self:
            mevcut = d.etki_ids.mapped('modul_id')
            for m in d.modul_ids - mevcut:
                Etki.create({'degisiklik_id': d.id, 'modul_id': m.id, 'sorumlu_id': m.sorumlu_id.id or d.sorumlu_id.id,
                             'aciklama': m.aciklama})
            d.etki_ids.filtered(lambda e: e.modul_id not in d.modul_ids and e.durum == 'acik' and not e.task_id).unlink()

    def _bildir(self):
        """Ayarlardaki eşik ve üzerindeki önemde: modül sorumlularına ve mevzuat sorumlusuna aktivite."""
        Ayar = self.env['atlas.mevzuat.ayar']
        esik = ONEM_SIRA.get(Ayar._ayar('bildirim_onem'), 3)
        for d in self:
            if ONEM_SIRA.get(d.onem, 0) < esik:
                continue
            kullanicilar = d.etki_ids.mapped('sorumlu_id') | d.sorumlu_id
            for u in kullanicilar:
                d.activity_schedule('mail.mail_activity_data_todo', user_id=u.id,
                                    date_deadline=min(d.yururluk_tarihi or fields.Date.today() + timedelta(days=3),
                                                      fields.Date.today() + timedelta(days=3)),
                                    summary=self.env._('Mevzuat: %(onem)s önemde mevzuat değişikliği', onem=dict(ONEMLER)[d.onem]))
            if kullanicilar:
                self.env['atlas.mevzuat.denetim'].kaydet(d, 'bildirim', self.env._('Aktivite: %s', ', '.join(kullanicilar.mapped('name'))))

    # ------------------------------------------------------------------ inceleme akışı
    def _inceleme(self, durum, aciklama):
        for d in self:
            d.write({'durum': durum, 'inceleyen_id': self.env.uid, 'inceleme_tarihi': fields.Datetime.now()})
            self.env['atlas.mevzuat.denetim'].kaydet(d, 'inceleme', aciklama)
            d.activity_ids.filtered(lambda a: a.activity_type_id == self.env.ref('mail.mail_activity_data_todo')).action_feedback(
                feedback=aciklama)

    def action_incele(self):
        self.filtered(lambda d: d.durum == 'yeni')._inceleme('inceleniyor', self.env._('İncelemeye alındı'))

    def action_onayla(self):
        for d in self:
            if d.durum not in ('yeni', 'inceleniyor'):
                raise UserError(self.env._('Yalnız yeni veya incelenen değişiklik onaylanabilir.'))
            if d.siniflandirma == 'yok' and not d.modul_ids:
                raise UserError(self.env._('"%s": onaylamadan önce etkilenen modülleri belirleyin.', d.name))
        self._inceleme('onaylandi', self.env._('Onaylandı: ERP etkisi var, aksiyon gerekli'))
        if self.env['atlas.mevzuat.ayar']._ayar('otomatik_gorev'):
            self.filtered(lambda d: not d.task_ids).action_gorev_olustur()

    def action_reddet(self):
        if any(d.durum not in ACIK_DURUMLAR for d in self):
            raise UserError(self.env._('Bu değişiklik zaten sonuçlanmış.'))
        self._inceleme('reddedildi', self.env._('İlgisiz/reddedildi. Not: %s', self.inceleme_notu or '-' if len(self) == 1 else '-'))
        self.etki_ids.filtered(lambda e: e.durum == 'acik').write({'durum': 'ilgisiz'})

    def action_uygulandi(self):
        acik = self.task_ids.filtered(lambda t: not t.is_closed)
        if acik:
            raise UserError(self.env._('Kapanmamış görevler var: %s', ', '.join(acik.mapped('name'))))
        self._inceleme('uygulandi', self.env._('ERP uyumu tamamlandı'))
        self.etki_ids.filtered(lambda e: e.durum == 'acik').write({'durum': 'tamam'})

    def action_yeniden_ac(self):
        self._inceleme('yeni', self.env._('Yeniden açıldı'))
        self.write({'mukerrer_id': False})

    def action_kurallari_uygula(self):
        """Kuralları yeniden çalıştırır (yerel işlem, dış bağlantı yok)."""
        for d in self:
            sonuc = siniflandir(d.name, d.icerik or '', self.env['atlas.mevzuat.kural']._motor_kurallari(d.kaynak_id))
            d.write(d._siniflandirma_degerleri(sonuc) | {'ai_onerisi': False})
            d._etkileri_guncelle()

    def action_ai_iste(self):
        if not self.env['atlas.mevzuat.ayar']._ayar('ai_etkin'):
            raise UserError(self.env._('Yapay zekâ önerisi Mevzuat Takip ayarlarında kapalı.'))
        self.write({'ai_durum': 'bekliyor', 'ai_hata': False})
        self.env.ref('atlas_mevzuat.ir_cron_mevzuat_ai')._trigger()

    def action_ai_kabul(self):
        for d in self.filtered(lambda d: d.ai_durum == 'tamam'):
            vals = {'onem': d.ai_onem or d.onem, 'siniflandirma': 'ai', 'ai_onerisi': True, 'guven': d.ai_guven}
            if d.ai_kategori_id:
                vals['kategori_id'] = d.ai_kategori_id.id
            if d.ai_modul_ids:
                vals['modul_ids'] = [Command.set(d.ai_modul_ids.ids)]
            if d.ai_yururluk:
                vals['yururluk_tarihi'] = d.ai_yururluk
            if d.ai_ozet and not d.ozet:
                vals['ozet'] = d.ai_ozet
            d.write(vals)
            d._etkileri_guncelle()
            self.env['atlas.mevzuat.denetim'].kaydet(d, 'ai', self.env._('AI önerisi kabul edildi (güven %%%s)', round(d.ai_guven)))

    def action_gorev_olustur(self):
        """Açık her etki için (etki yoksa değişiklik için) proje görevi açar."""
        proje = self.env['atlas.mevzuat.ayar']._ayar('proje')
        if not proje:
            raise UserError(self.env._('Mevzuat Takip ayarlarında görev projesi seçilmemiş.'))
        Task = self.env['project.task']
        for d in self:
            aciklama = (f'<p>{d.ozet or d.ai_ozet or ""}</p><p><a href="{d.url or ""}">{d.kurum or ""} — kaynak</a></p>'
                        f'<p>Yürürlük: {d.yururluk_tarihi or "-"}</p>')
            ortak = {'project_id': proje.id, 'atlas_mevzuat_degisiklik_id': d.id, 'date_deadline': d.yururluk_tarihi,
                     'priority': '1' if d.onem in ('yuksek', 'kritik') else '0'}
            etkiler = d.etki_ids.filtered(lambda e: e.durum == 'acik' and not e.task_id)
            if not etkiler and not d.task_ids:
                Task.create(dict(ortak, name=f'[Mevzuat] {d.name}'[:250], description=aciklama,
                                 user_ids=[Command.set((d.sorumlu_id or self.env.user).ids)]))
            for e in etkiler:
                e.task_id = Task.create(dict(ortak, name=f'[Mevzuat · {e.modul_id.name}] {d.name}'[:250],
                                             description=aciklama + (f'<p>{e.aciklama}</p>' if e.aciklama else ''),
                                             atlas_mevzuat_etki_id=e.id,
                                             user_ids=[Command.set((e.sorumlu_id or d.sorumlu_id or self.env.user).ids)]))
            self.env['atlas.mevzuat.denetim'].kaydet(d, 'gorev', self.env._('Görevler oluşturuldu (%s)', len(d.task_ids)))
        return self.action_gorevler() if len(self) == 1 else True

    def action_gorevler(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Mevzuat Görevleri'), 'res_model': 'project.task',
                'view_mode': 'list,form', 'domain': [('atlas_mevzuat_degisiklik_id', 'in', self.ids)]}

    def action_kaynagi_ac(self):
        self.ensure_one()
        if not self.url:
            raise UserError(self.env._('Bu değişikliğin adresi yok.'))
        return {'type': 'ir.actions.act_url', 'url': self.url, 'target': 'new'}

    # ------------------------------------------------------------------ yapay zekâ
    @api.model
    def _ai_isle(self, limit=10, oturum=None):
        Ayar = self.env['atlas.mevzuat.ayar']
        bekleyen = self.search([('ai_durum', '=', 'bekliyor')], limit=limit, order='id')
        if not bekleyen:
            return
        if not Ayar._ayar('ai_etkin') or not Ayar._ayar('ai_anahtar'):
            bekleyen.write({'ai_durum': 'hata', 'ai_hata': self.env._('Yapay zekâ kapalı veya API anahtarı yok')})
            return
        kategoriler = {k.kod: k.name for k in self.env['atlas.mevzuat.kategori'].search([])}
        Modul = self.env['atlas.mevzuat.modul']
        moduller = {m.teknik_ad: m.aciklama or m.name for m in Modul.search([])}
        for d in bekleyen:
            istem = ai.istem_olustur(d.name, d.icerik or '', f'{d.kurum} — {d.kaynak_id.name}', kategoriler, moduller)
            try:
                s = ai.sor(Ayar._ayar('ai_anahtar'), Ayar._ayar('ai_model'), istem, oturum=oturum)
            except Exception as e:  # ağ, kota, ayrıştırma …
                _logger.warning('Mevzuat AI hatası (%s): %s', d.id, e)
                d.write({'ai_durum': 'hata', 'ai_hata': str(e)[:250]})
                continue
            kategori = self.env['atlas.mevzuat.kategori'].search([('kod', '=', s['kategori'])], limit=1) if s['kategori'] else None
            d.write({
                'ai_durum': 'tamam', 'ai_hata': False, 'ai_guven': s['guven'], 'ai_ozet': s['ozet'], 'ai_onem': s['onem'],
                'ai_kategori_id': kategori.id if kategori else False, 'ai_ilgisiz': s['ilgisiz'],
                'ai_modul_ids': [Command.set(Modul.search([('teknik_ad', 'in', s['moduller'])]).ids)],
                'ai_yururluk': tarih_bul(s['yururluk_tarihi']) if s['yururluk_tarihi'] else False,
            })
            self.env['atlas.mevzuat.denetim'].kaydet(d, 'ai', self.env._('AI önerisi alındı (güven %%%s)', round(s['guven'])),
                                                   {k: v for k, v in s.items() if k != 'ozet'})

    @api.model
    def _cron_ai(self):
        self._ai_isle()

    # ------------------------------------------------------------------ özet e-postası ve panel
    @api.model
    def _ozet_verisi(self, saat=24):
        bugun = fields.Date.context_today(self)
        return {
            'yeniler': self.search([('tespit_tarihi', '>=', fields.Datetime.now() - timedelta(hours=saat)), ('durum', '!=', 'mukerrer')],
                                   order='onem desc, id desc'),
            'yaklasan': self.search([('yururluk_tarihi', '>=', bugun), ('yururluk_tarihi', '<=', bugun + timedelta(days=14)),
                                     ('durum', 'in', ACIK_DURUMLAR)], order='yururluk_tarihi'),
            'bekleyen': self.search_count([('durum', 'in', ('yeni', 'inceleniyor'))]),
            'sorunlu': self.env['atlas.mevzuat.kaynak'].search([('saglik', 'in', ('hata', 'robots'))]),
        }

    @api.model
    def _ozet_gonder(self):
        alicilar = self.env['atlas.mevzuat.ayar']._ayar('ozet_alicilar').filtered('email')
        veri = self._ozet_verisi()
        if not alicilar or not (veri['yeniler'] or veri['yaklasan'] or veri['sorunlu']):
            return False
        govde = self.env['ir.qweb']._render('atlas_mevzuat.ozet_eposta', dict(veri, onemler=dict(ONEMLER),
                                                                           taban=self.env['ir.config_parameter'].sudo().get_str('web.base.url')))
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.env._('Mevzuat Takip günlük özet: %(yeni)s yeni değişiklik, %(bekleyen)s inceleme bekliyor',
                                  yeni=len(veri['yeniler']), bekleyen=veri['bekleyen']),
            'body_html': govde,
            'email_to': ','.join(alicilar.mapped('email_formatted')),
            'auto_delete': True,
        })
        self.env['atlas.mevzuat.denetim'].kaydet(None, 'bildirim', self.env._('Günlük özet: %s alıcı', len(alicilar)))
        return mail

    @api.model
    def _cron_ozet(self):
        self._ozet_gonder()

    @api.model
    def panel_verisi(self):
        bugun = fields.Date.context_today(self)
        say = lambda alan: self.search_count(alan)
        son = self.search([('durum', '!=', 'mukerrer')], limit=12)
        yaklasan = self.search([('yururluk_tarihi', '>=', bugun - timedelta(days=7)), ('durum', 'in', ACIK_DURUMLAR)],
                               order='yururluk_tarihi', limit=10)
        kaynaklar = self.env['atlas.mevzuat.kaynak'].with_context(active_test=False).search([])
        ozet = lambda d: {'id': d.id, 'ad': d.name, 'onem': d.onem, 'onem_ad': dict(ONEMLER)[d.onem], 'durum': d.durum,
                          'durum_ad': dict(DURUMLAR)[d.durum], 'kurum': d.kurum or '', 'kategori': d.kategori_id.name or '',
                          'tarih': fields.Datetime.to_string(d.tespit_tarihi), 'yururluk': fields.Date.to_string(d.yururluk_tarihi) if d.yururluk_tarihi else '',
                          'kirici': d.kirici, 'ai': d.ai_durum == 'tamam'}
        kategori = self._read_group([('durum', 'in', ACIK_DURUMLAR)], ['kategori_id'], ['__count'])
        return {
            'kpi': {
                'yeni': say([('durum', '=', 'yeni')]),
                'inceleniyor': say([('durum', '=', 'inceleniyor')]),
                'aksiyon': say([('durum', '=', 'onaylandi')]),
                'kritik': say([('durum', 'in', ACIK_DURUMLAR), ('onem', 'in', ('yuksek', 'kritik'))]),
                'kirici': say([('durum', 'in', ACIK_DURUMLAR), ('kirici', '=', True)]),
                'yaklasan': say([('yururluk_tarihi', '>=', bugun), ('yururluk_tarihi', '<=', bugun + timedelta(days=30)),
                                 ('durum', 'in', ACIK_DURUMLAR)]),
                'hafta': say([('tespit_tarihi', '>=', fields.Datetime.now() - timedelta(days=7)), ('durum', '!=', 'mukerrer')]),
                'sorunlu_kaynak': len(kaynaklar.filtered(lambda k: k.saglik in ('hata', 'robots', 'uyari'))),
            },
            'son': [ozet(d) for d in son],
            'yaklasan': [ozet(d) for d in yaklasan],
            'kategoriler': [{'id': k.id, 'ad': k.name if k else 'Kategorisiz', 'sayi': n} for k, n in kategori],
            'kaynaklar': [{'id': k.id, 'ad': k.name, 'kurum': k.kurum, 'saglik': k.saglik,
                           'saglik_ad': dict(k._fields['saglik']._description_selection(self.env)).get(k.saglik, ''),
                           'son_basari': fields.Datetime.to_string(k.son_basari) if k.son_basari else '',
                           'sure': k.yanit_suresi, 'hata': (k.son_hata or '')[:160], 'oge': k.son_oge_sayisi} for k in kaynaklar],
        }

    @api.ondelete(at_uninstall=False)
    def _unlink_kontrol(self):
        if any(d.durum in ('onaylandi', 'uygulandi') for d in self):
            raise UserError(self.env._('Onaylanmış/uygulanmış değişiklik silinemez; denetim izi korunur.'))


class AtlasMevzuatEtki(models.Model):
    _name = 'atlas.mevzuat.etki'
    _inherit = ['atlas.mevzuat.denetim.mixin']
    _description = 'Mevzuat Etki Analizi'
    _order = 'degisiklik_id desc, id'
    _denetim_alanlari = ('durum', 'sorumlu_id', 'company_id')

    degisiklik_id = fields.Many2one('atlas.mevzuat.degisiklik', string='Değişiklik', required=True, ondelete='cascade', index=True)
    modul_id = fields.Many2one('atlas.mevzuat.modul', string='Modül', required=True)
    company_id = fields.Many2one('res.company', string='Şirket', help='Boşsa tüm şirketler')
    aciklama = fields.Text(string='Etki')
    sorumlu_id = fields.Many2one('res.users', string='Sorumlu', domain=[('share', '=', False)])
    durum = fields.Selection([('acik', 'Açık'), ('tamam', 'Tamamlandı'), ('ilgisiz', 'Etkilemiyor')], string='Durum',
                             default='acik', required=True)
    task_id = fields.Many2one('project.task', string='Görev', readonly=True)
    onem = fields.Selection(related='degisiklik_id.onem', store=True)
    yururluk_tarihi = fields.Date(related='degisiklik_id.yururluk_tarihi', store=True)
    degisiklik_durum = fields.Selection(related='degisiklik_id.durum', string='Değişiklik Durumu')


class ProjectTask(models.Model):
    _inherit = 'project.task'

    atlas_mevzuat_degisiklik_id = fields.Many2one('atlas.mevzuat.degisiklik', string='Mevzuat Değişikliği', index='btree_not_null',
                                                ondelete='set null', groups='base.group_system')
    atlas_mevzuat_etki_id = fields.Many2one('atlas.mevzuat.etki', string='Mevzuat Etkisi', ondelete='set null', groups='base.group_system')

    def write(self, vals):
        sonuc = super().write(vals)
        if 'state' in vals:
            gorevler = self.sudo().filtered('atlas_mevzuat_etki_id')
            for t in gorevler.filtered('is_closed'):
                if t.atlas_mevzuat_etki_id.durum == 'acik':
                    t.atlas_mevzuat_etki_id.durum = 'tamam'
        return sonuc
