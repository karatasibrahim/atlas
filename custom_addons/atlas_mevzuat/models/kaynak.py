import logging
from datetime import timedelta
from urllib.parse import urlsplit

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..services import ayristirici
from ..services.ayristirici import AyristirmaHatasi
from ..services.guvenlik import GuvenlikHatasi, alan_adlari, alan_izinli
from ..services.metin import ozet
from ..services.tarayici import RobotsEngeli, TaramaHatasi, Tarayici

_logger = logging.getLogger(__name__)

TARAMA_HATALARI = (TaramaHatasi, GuvenlikHatasi, AyristirmaHatasi, requests.RequestException)


class AtlasMevzuatKaynak(models.Model):
    _name = 'atlas.mevzuat.kaynak'
    _inherit = ['atlas.mevzuat.denetim.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Mevzuat Kaynağı'
    _order = 'oncelik desc, sira, name'
    _denetim_alanlari = ('url', 'active', 'tur', 'izinli_alanlar', 'kontrol_araligi', 'xpath', 'link_deseni', 'http_metot',
                         'istek_govdesi', 'json_liste_yolu', 'sadece_eslesenler')

    name = fields.Char(string='Kaynak', required=True, tracking=True)
    kurum = fields.Char(string='Kurum', required=True, help='ör. Gelir İdaresi Başkanlığı')
    sira = fields.Integer(default=10)
    active = fields.Boolean(string='Etkin', default=True, tracking=True)
    ulke_id = fields.Many2one('res.country', string='Ülke', default=lambda self: self.env.ref('base.tr', raise_if_not_found=False))
    yetki_alani = fields.Selection([('ulusal', 'Ulusal'), ('yerel', 'Yerel / İl'), ('ab', 'Avrupa Birliği'),
                                    ('uluslararasi', 'Uluslararası')], string='Yetki Alanı', default='ulusal', required=True)
    url = fields.Char(string='Adres', required=True, tracking=True)
    tur = fields.Selection([('html_liste', 'HTML bağlantı listesi'), ('rss', 'RSS / Atom'), ('json_api', 'JSON API'),
                            ('sayfa', 'Tek sayfa (içerik değişimi)')], string='Ayrıştırıcı', default='html_liste', required=True)
    oncelik = fields.Selection([('0', 'Normal'), ('1', 'Yüksek'), ('2', 'Kritik')], string='Öncelik', default='0')
    kontrol_araligi = fields.Integer(string='Kontrol Aralığı (Saat)', default=6, required=True)
    izinli_alanlar = fields.Char(string='İzinli Alan Adları', required=True,
                                 help='Virgülle ayırın. Tarayıcı yalnız bu alan adlarına (ve alt alan adlarına) bağlanır; '
                                      'yönlendirmeler de bu listeye göre doğrulanır.')
    kategori_id = fields.Many2one('atlas.mevzuat.kategori', string='Varsayılan Kategori')
    etiket_ids = fields.Many2many('atlas.mevzuat.etiket', string='Etiketler')
    sadece_eslesenler = fields.Boolean(string='Yalnız Kurala Uyanlar Değişiklik Olsun',
                                       help='Kurallarla eşleşmeyen öğeler belge olarak saklanır ama değişiklik kaydı açılmaz '
                                            '(Resmî Gazete gibi her gün çok sayıda ilgisiz ilan yayımlayan kaynaklar için).')
    # İstek
    http_metot = fields.Selection([('GET', 'GET'), ('POST', 'POST')], string='HTTP Metodu', default='GET', required=True)
    istek_govdesi = fields.Text(string='İstek Gövdesi (JSON)')
    # HTML liste
    xpath = fields.Char(string='XPath Seçici', help='Bağlantı listesi için ör. //a[contains(@href, "/duyuru/detay/")]; '
                                                   'tek sayfada izlenecek bölüm, ör. //main')
    link_deseni = fields.Char(string='Bağlantı Deseni', help='Bağlantı adresinin uyması gereken düzenli ifade')
    en_az_uzunluk = fields.Integer(string='En Kısa Başlık', default=15)
    # JSON
    json_liste_yolu = fields.Char(string='Liste Yolu', help='ör. resultContainer.content')
    json_kimlik = fields.Char(string='Kimlik Alanı', default='id')
    json_baslik = fields.Char(string='Başlık Alanı', default='title')
    json_tarih = fields.Char(string='Tarih Alanı')
    json_icerik = fields.Char(string='İçerik Alanı')
    json_url = fields.Char(string='Adres Alanı')
    link_sablonu = fields.Char(string='Bağlantı Şablonu', help='Adres alanı boşsa, ör. https://www.gib.gov.tr/duyuru-arsivi/gib-duyurulari/{slug}')
    # Detay
    detay_getir = fields.Boolean(string='Detay Sayfasını Oku', help='Yeni öğelerin detay sayfası indirilir; sınıflandırma ve '
                                                                     'yürürlük tarihi tespiti tam metinle yapılır.')
    detay_xpath = fields.Char(string='Detay XPath', help='Boşsa main/article/body')
    detay_sinir = fields.Integer(string='Tarama Başına En Fazla Detay', default=10)
    # Sağlık
    robots_durumu = fields.Selection([('bilinmiyor', 'Bilinmiyor'), ('izinli', 'İzinli'), ('engelli', 'robots.txt engelliyor')],
                                     string='robots.txt', default='bilinmiyor', readonly=True)
    ilk_tarama_tamam = fields.Boolean(string='Temel Alındı', readonly=True, copy=False,
                                      help='İlk taramada bulunan öğeler temel kabul edilir, değişiklik açılmaz.')
    son_kontrol = fields.Datetime(string='Son Kontrol', readonly=True, copy=False)
    son_basari = fields.Datetime(string='Son Başarılı', readonly=True, copy=False)
    son_hata = fields.Text(string='Son Hata', readonly=True, copy=False)
    ardisik_hata = fields.Integer(string='Ardışık Hata', readonly=True, copy=False)
    yanit_suresi = fields.Integer(string='Yanıt Süresi (ms)', readonly=True, copy=False)
    son_oge_sayisi = fields.Integer(string='Son Taramada Öğe', readonly=True, copy=False)
    sonraki_kontrol = fields.Datetime(string='Sonraki Kontrol', compute='_compute_sonraki_kontrol', store=True)
    saglik = fields.Selection([('iyi', 'Sağlıklı'), ('uyari', 'Uyarı'), ('hata', 'Hatalı'), ('robots', 'robots.txt engeli'),
                               ('bekliyor', 'Taranmadı'), ('pasif', 'Pasif')], string='Sağlık', compute='_compute_saglik', store=True)
    belge_ids = fields.One2many('atlas.mevzuat.belge', 'kaynak_id', string='Belgeler')
    belge_sayisi = fields.Integer(compute='_compute_sayilar')
    degisiklik_sayisi = fields.Integer(compute='_compute_sayilar')
    notlar = fields.Html(string='Notlar')

    @api.depends('son_kontrol', 'kontrol_araligi', 'active')
    def _compute_sonraki_kontrol(self):
        for k in self:
            k.sonraki_kontrol = (k.son_kontrol + timedelta(hours=max(k.kontrol_araligi, 1))) if k.son_kontrol else False

    @api.depends('active', 'robots_durumu', 'ardisik_hata', 'son_basari', 'son_kontrol')
    def _compute_saglik(self):
        for k in self:
            if not k.active:
                k.saglik = 'pasif'
            elif k.robots_durumu == 'engelli':
                k.saglik = 'robots'
            elif k.ardisik_hata >= 3:
                k.saglik = 'hata'
            elif k.ardisik_hata:
                k.saglik = 'uyari'
            elif k.son_basari:
                k.saglik = 'iyi'
            else:
                k.saglik = 'bekliyor'

    def _compute_sayilar(self):
        belge = dict(self.env['atlas.mevzuat.belge']._read_group([('kaynak_id', 'in', self.ids)], ['kaynak_id'], ['__count']))
        degisiklik = dict(self.env['atlas.mevzuat.degisiklik']._read_group([('kaynak_id', 'in', self.ids)], ['kaynak_id'], ['__count']))
        for k in self:
            k.belge_sayisi = belge.get(k, 0)
            k.degisiklik_sayisi = degisiklik.get(k, 0)

    @api.constrains('url', 'izinli_alanlar', 'link_sablonu')
    def _check_url(self):
        for k in self:
            parca = urlsplit(k.url or '')
            if parca.scheme not in ('http', 'https') or not parca.hostname:
                raise ValidationError(self.env._('Geçersiz adres: %s', k.url))
            izinli = alan_adlari(k.izinli_alanlar)
            if not alan_izinli(parca.hostname, izinli):
                raise ValidationError(self.env._('Kaynak adresinin alan adı (%(host)s) izinli alanlar arasında olmalı.',
                                                 host=parca.hostname))
            if k.link_sablonu and k.link_sablonu.startswith('http'):
                sablon_host = urlsplit(k.link_sablonu).hostname
                if sablon_host and not alan_izinli(sablon_host, izinli):
                    raise ValidationError(self.env._('Bağlantı şablonunun alan adı izinli alanlar arasında olmalı.'))

    @api.constrains('kontrol_araligi')
    def _check_aralik(self):
        if any(k.kontrol_araligi < 1 for k in self):
            raise ValidationError(self.env._('Kontrol aralığı en az 1 saat olmalı.'))

    # ------------------------------------------------------------------ tarama
    def _tarayici(self, **kw):
        return Tarayici(alan_adlari(self.izinli_alanlar), **kw)

    def _ayristir(self, yanit):
        metin = yanit.metin
        if self.tur == 'rss':
            return ayristirici.rss(metin, yanit.url)
        if self.tur == 'json_api':
            return ayristirici.json_api(metin, yanit.url, self.json_liste_yolu or '', self.json_kimlik or 'id',
                                        self.json_baslik or 'title', self.json_tarih or '', self.json_icerik or '',
                                        self.json_url or '', self.link_sablonu or '')
        if self.tur == 'sayfa':
            return ayristirici.sayfa(metin, yanit.url, self.xpath or '')
        return ayristirici.html_liste(metin, yanit.url, self.xpath or '//a[@href]', self.link_deseni or None,
                                      self.en_az_uzunluk or 0)

    def _tara(self, tarayici=None):
        """Kaynağı tarar; yeni/değişen öğeler için belge ve değişiklik kaydı oluşturur. Dönüş: oluşan değişiklikler."""
        self.ensure_one()
        tarayici = tarayici or self._tarayici()
        simdi = fields.Datetime.now()
        degisiklikler = self.env['atlas.mevzuat.degisiklik']
        vals = {'son_kontrol': simdi}
        try:
            basliklar = {'Content-Type': 'application/json'} if self.http_metot == 'POST' else {}
            yanit = tarayici.getir(self.url, self.http_metot, (self.istek_govdesi or '').encode('utf-8') or None, basliklar)
            if yanit.durum >= 400:
                raise TaramaHatasi(f'HTTP {yanit.durum}')
            ogeler = self._ayristir(yanit)
            if not ogeler:
                raise AyristirmaHatasi('Sayfada izlenecek öğe bulunamadı; sayfa yapısı değişmiş olabilir (seçiciyi kontrol edin).')
            degisiklikler = self._ogeleri_isle(ogeler, tarayici)
            vals.update(son_basari=simdi, son_hata=False, ardisik_hata=0, yanit_suresi=yanit.sure_ms, robots_durumu='izinli',
                        son_oge_sayisi=len(ogeler), ilk_tarama_tamam=True)
            ozet_metni = self.env._('%(oge)s öğe, %(yeni)s değişiklik', oge=len(ogeler), yeni=len(degisiklikler))
        except RobotsEngeli as e:
            vals.update(robots_durumu='engelli', son_hata=str(e), ardisik_hata=self.ardisik_hata + 1)
            ozet_metni = str(e)
        except TARAMA_HATALARI as e:
            vals.update(son_hata=str(e)[:2000], ardisik_hata=self.ardisik_hata + 1)
            ozet_metni = self.env._('Hata: %s', str(e)[:300])
        self.write(vals)
        self.env['atlas.mevzuat.denetim'].kaydet(self, 'tarama', ozet_metni)
        if vals.get('ardisik_hata') == 3:
            self._saglik_bildir()
        return degisiklikler

    def _ogeleri_isle(self, ogeler, tarayici):
        Belge = self.env['atlas.mevzuat.belge']
        mevcut = {b.dis_kimlik: b for b in Belge.with_context(active_test=False).search(
            [('kaynak_id', '=', self.id), ('dis_kimlik', 'in', [o['kimlik'] for o in ogeler])])}
        temel = not self.ilk_tarama_tamam
        detay_hakki = self.detay_sinir if self.detay_getir else 0
        degisiklikler = self.env['atlas.mevzuat.degisiklik']
        for oge in ogeler:
            oge_ozeti = ozet(oge['baslik'] + '\n' + oge['icerik'])
            belge = mevcut.get(oge['kimlik'])
            if belge and belge.oge_ozeti == oge_ozeti:
                continue
            icerik = oge['icerik']
            if detay_hakki > 0 and not temel and oge['url'] and oge['url'] != self.url:
                detay_hakki -= 1
                icerik = self._detay_oku(tarayici, oge['url']) or icerik
            tam = oge['baslik'] + '\n' + icerik
            if not belge:
                belge = Belge.create({
                    'kaynak_id': self.id, 'dis_kimlik': oge['kimlik'], 'name': oge['baslik'], 'url': oge['url'],
                    'yayim_tarihi': oge['tarih'], 'icerik': icerik, 'oge_ozeti': oge_ozeti, 'icerik_ozeti': ozet(tam),
                    'durum': 'temel' if temel else 'yeni',
                })
                if not temel:
                    degisiklikler |= belge._degisiklik_olustur('yeni')
                continue
            yeni_ozet = ozet(tam)
            if yeni_ozet == belge.icerik_ozeti:
                belge.oge_ozeti = oge_ozeti
                continue
            onceki = belge.name + '\n' + (belge.icerik or '')
            belge.write({'onceki_ozet': belge.icerik_ozeti, 'onceki_icerik': belge.icerik, 'icerik': icerik, 'name': oge['baslik'],
                         'oge_ozeti': oge_ozeti, 'icerik_ozeti': yeni_ozet, 'surum': belge.surum + 1,
                         'yayim_tarihi': oge['tarih'] or belge.yayim_tarihi, 'url': oge['url'] or belge.url})
            degisiklikler |= belge._degisiklik_olustur('guncelleme', onceki_metin=onceki)
        return degisiklikler

    def _detay_oku(self, tarayici, url):
        try:
            y = tarayici.getir(url)
        except TARAMA_HATALARI as e:
            _logger.info('Mevzuat detay okunamadı %s: %s', url, e)
            return ''
        if y.durum >= 400 or 'html' not in (y.tur or 'html'):
            return ''
        return ayristirici.detay_metni(y.metin, self.detay_xpath or '')

    def _saglik_bildir(self):
        sorumlu = self.env['atlas.mevzuat.ayar']._ayar('sorumlu')
        if sorumlu:
            self.activity_schedule('mail.mail_activity_data_todo', user_id=sorumlu.id,
                                   summary=self.env._('Mevzuat kaynağı 3 kez üst üste taranamadı'),
                                   note=self.son_hata)

    @api.model
    def _cron_tara(self):
        """Zamanı gelen kaynakları tarar; her kaynak ayrı kayıt noktasında, ilerleme kaydedilerek."""
        simdi = fields.Datetime.now()
        kaynaklar = self.search(['|', ('son_kontrol', '=', False), ('sonraki_kontrol', '<=', simdi)])
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(kaynaklar))
        for kaynak in kaynaklar:
            try:
                with self.env.cr.savepoint():
                    kaynak._tara()
            except Exception as e:  # beklenmeyen hata diğer kaynakları durdurmasın
                _logger.exception('Mevzuat kaynağı taranamadı: %s', kaynak.name)
                kaynak.write({'son_kontrol': simdi, 'son_hata': str(e)[:2000], 'ardisik_hata': kaynak.ardisik_hata + 1})
            if not Cron._commit_progress(1):
                break
        self.env['atlas.mevzuat.degisiklik']._ai_isle()

    def action_simdi_tara(self):
        """Taramayı kullanıcı isteği içinde yapmaz; zamanlanmış görevi hemen çalışmak üzere tetikler."""
        self.write({'son_kontrol': False})
        self.env.ref('atlas_mevzuat.ir_cron_mevzuat_tara')._trigger()
        self.env['atlas.mevzuat.denetim'].kaydet(self, 'tarama', self.env._('Tarama kuyruğa alındı'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'info', 'message': self.env._('Tarama arka planda başlatıldı; birkaç dakika içinde sonuçlanır.')}}

    def action_temeli_sifirla(self):
        """Sonraki taramada bulunanlar yeniden temel kabul edilir (değişiklik açılmaz)."""
        if self.env['atlas.mevzuat.degisiklik'].search_count([('kaynak_id', 'in', self.ids), ('durum', 'in', ('yeni', 'inceleniyor'))]):
            raise UserError(self.env._('Önce bu kaynağın incelenmemiş değişikliklerini sonuçlandırın.'))
        self.write({'ilk_tarama_tamam': False})

    def action_belgeler(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Belgeler'), 'res_model': 'atlas.mevzuat.belge',
                'view_mode': 'list,form', 'domain': [('kaynak_id', 'in', self.ids)], 'context': {'default_kaynak_id': self.id}}

    def action_degisiklikler(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Değişiklikler'), 'res_model': 'atlas.mevzuat.degisiklik',
                'view_mode': 'list,form,calendar', 'domain': [('kaynak_id', 'in', self.ids)]}
