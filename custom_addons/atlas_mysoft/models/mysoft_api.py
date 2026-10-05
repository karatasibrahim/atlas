"""MySoft e-Belge API (edocumentapi) bağlantı katmanı.

Kimlik doğrulama: OAuth 2.0 client_credentials (Erişim Anahtarı: Client Id / Client Secret), token 5 dakika geçerli.
İş ortağı anahtarında belge sahibinin VKN'si her istekte ``tenantIdentifierNumber`` ile gönderilir.
Yanıt biçimleri dokümanda örneklenmediği için ayrıştırma esnektir ve her istek/yanıt günlüğe yazılır.
"""
import io
import json
import logging
import re
import time
import zipfile

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

API_ADRESLERI = {'test': 'https://edocumentapi.mytest.tr', 'canli': 'https://edocumentapi.mysoft.com.tr'}
TOKEN_ONBELLEK = {}  # (veritabanı, şirket, ortam, client_id) → (token, bitiş)
GIZLI_ANAHTARLAR = ('client_secret', 'access_token', 'Authorization', 'invoiceTypeUblString')


def sadece_rakam(deger):
    return re.sub(r'\D', '', deger or '')


def anahtar_bul(veri, desenler):
    """İç içe sözlük/listede adı desene uyan ilk dolu değeri döndürür (büyük/küçük harf duyarsız).
    Desenler öncelik sırasıyla denenir; her desen için önce üst düzey, sonra iç düzeyler taranır."""
    for desen in desenler:
        ifade = re.compile(desen, re.I)
        yigin = [veri]
        while yigin:
            oge = yigin.pop(0)
            if isinstance(oge, dict):
                for k, v in oge.items():
                    if v not in (None, '', [], {}) and not isinstance(v, (dict, list)) and ifade.fullmatch(k):
                        return v
                yigin.extend(v for v in oge.values() if isinstance(v, (dict, list)))
            elif isinstance(oge, list):
                yigin.extend(oge)
    return None


def liste_bul(veri):
    """Yanıttaki kayıt listesini bulur (data, data.items, items, result...)."""
    if isinstance(veri, list):
        return veri
    if isinstance(veri, dict):
        for k in ('data', 'Data', 'items', 'Items', 'result', 'Result', 'list', 'List', 'value'):
            if k in veri:
                bulunan = liste_bul(veri[k])
                if bulunan is not None:
                    return bulunan
        listeler = [v for v in veri.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        if listeler:
            return listeler[0]
    return None


def basari_mi(veri):
    """success / succeed / isSucceeded … alanlarından sonucu çıkarır; alan yoksa None."""
    if not isinstance(veri, dict):
        return None
    for k, v in veri.items():
        if k.lower() in ('success', 'succeed', 'succeeded', 'issucceeded', 'issuccess', 'issucceed', 'issuccessful', 'result') \
                and isinstance(v, bool):
            return v
    return None


def mesaj_bul(veri):
    if isinstance(veri, dict):
        for k in ('error_description', 'message', 'Message', 'errorMessage', 'ErrorMessage', 'resultMessage', 'error',
                  'messages', 'errors'):
            v = veri.get(k)
            if v:
                if isinstance(v, list):
                    return '; '.join(str(x.get('message', x) if isinstance(x, dict) else x) for x in v)
                if isinstance(v, dict):
                    return json.dumps(v, ensure_ascii=False)[:500]
                return str(v)
    return ''


def zipten_dosya(icerik, uzantilar):
    """ZIP içindeki ilk uygun dosyayı (ad, bayt) döndürür. ZIP değilse içeriğin kendisi."""
    try:
        with zipfile.ZipFile(io.BytesIO(icerik)) as z:
            for ad in z.namelist():
                if ad.lower().endswith(uzantilar):
                    return ad, z.read(ad)
            ad = z.namelist()[0]
            return ad, z.read(ad)
    except zipfile.BadZipFile:
        return None, icerik


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_mysoft_aktif = fields.Boolean(string='MySoft Entegrasyonu')
    atlas_mysoft_ortam = fields.Selection([('test', 'Test (edocumentapi.mytest.tr)'), ('canli', 'Canlı (edocumentapi.mysoft.com.tr)')],
                                          string='MySoft Ortamı', default='test')
    atlas_mysoft_client_id = fields.Char(string='Client Id', groups='base.group_system')
    atlas_mysoft_client_secret = fields.Char(string='Client Secret', groups='base.group_system')
    atlas_mysoft_anahtar_tipi = fields.Selection([('firma', 'Firma Erişim Anahtarı'), ('is_ortagi', 'İş Ortağı Erişim Anahtarı')],
                                                 string='Anahtar Tipi', default='firma',
                                                 help='İş ortağı anahtarında şirket VKN\'si her istekte belge sahibi olarak gönderilir.')
    atlas_mysoft_gb_etiket = fields.Char(string='Gönderici Birim Etiketi (GB)', help='ör. urn:mail:defaultgb@mysoft.com.tr')
    atlas_mysoft_gonderim = fields.Selection([('dogrudan', 'Doğrudan GİB\'e gönder'), ('taslak', 'MySoft\'ta taslak bırak')],
                                             string='Gönderim Şekli', default='dogrudan',
                                             help='Taslakta bırakılan faturalar "Taslağı GİB\'e Gönder" ile iletilir.')
    atlas_mysoft_numara = fields.Selection([('atlas', 'Atlas seri numarası gönderilir'), ('mysoft', 'Numarayı MySoft verir')],
                                           string='Belge Numarası', default='atlas')
    atlas_mysoft_efatura_onek = fields.Char(string='e-Fatura Ön Eki', size=3)
    atlas_mysoft_earsiv_onek = fields.Char(string='e-Arşiv Ön Eki', size=3)
    atlas_mysoft_eirsaliye_onek = fields.Char(string='e-İrsaliye Ön Eki', size=3)
    atlas_mysoft_otomatik = fields.Boolean(string='Onaylanınca Otomatik Gönder', default=True)
    atlas_mysoft_earsiv_teslim = fields.Selection([('ELEKTRONIK', 'Elektronik'), ('KAGIT', 'Kâğıt')], string='e-Arşiv Teslim Şekli',
                                                  default='ELEKTRONIK')
    atlas_mysoft_durum_kontrol = fields.Datetime(string='Son Durum Kontrolü', readonly=True)
    atlas_mysoft_gelen_imlec = fields.Integer(string='Gelen Fatura İmleci', readonly=True)
    atlas_mysoft_gelen_kontrol = fields.Datetime(string='Son Gelen Fatura Kontrolü', readonly=True)

    def _atlas_mysoft_tenant(self):
        self.ensure_one()
        if self.atlas_mysoft_anahtar_tipi != 'is_ortagi':
            return None
        return sadece_rakam(self.vat) or None

    def action_atlas_mysoft_test(self):
        self.ensure_one()
        bilgi = self.env['atlas.mysoft.api']._istek(self, 'GET', '/api/GeneralCard/getUserCompanyInfo', islem='Bağlantı testi')
        unvan = anahtar_bul(bilgi, [r'.*(title|name|unvan).*']) or ''
        vkn = anahtar_bul(bilgi, [r'.*(vkn|tckn|identifier).*']) or ''
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'title': self.env._('MySoft bağlantısı başarılı'),
                           'message': f'{unvan} {vkn}'.strip() or self.env._('Token alındı.')}}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_mysoft_aktif = fields.Boolean(related='company_id.atlas_mysoft_aktif', readonly=False)
    atlas_mysoft_ortam = fields.Selection(related='company_id.atlas_mysoft_ortam', readonly=False)
    atlas_mysoft_client_id = fields.Char(related='company_id.atlas_mysoft_client_id', readonly=False)
    atlas_mysoft_client_secret = fields.Char(related='company_id.atlas_mysoft_client_secret', readonly=False)
    atlas_mysoft_anahtar_tipi = fields.Selection(related='company_id.atlas_mysoft_anahtar_tipi', readonly=False)
    atlas_mysoft_gb_etiket = fields.Char(related='company_id.atlas_mysoft_gb_etiket', readonly=False)
    atlas_mysoft_gonderim = fields.Selection(related='company_id.atlas_mysoft_gonderim', readonly=False)
    atlas_mysoft_numara = fields.Selection(related='company_id.atlas_mysoft_numara', readonly=False)
    atlas_mysoft_efatura_onek = fields.Char(related='company_id.atlas_mysoft_efatura_onek', readonly=False)
    atlas_mysoft_earsiv_onek = fields.Char(related='company_id.atlas_mysoft_earsiv_onek', readonly=False)
    atlas_mysoft_eirsaliye_onek = fields.Char(related='company_id.atlas_mysoft_eirsaliye_onek', readonly=False)
    atlas_mysoft_otomatik = fields.Boolean(related='company_id.atlas_mysoft_otomatik', readonly=False)
    atlas_mysoft_earsiv_teslim = fields.Selection(related='company_id.atlas_mysoft_earsiv_teslim', readonly=False)

    def action_atlas_mysoft_test(self):
        self.execute()
        return self.company_id.action_atlas_mysoft_test()


class AtlasMysoftLog(models.Model):
    _name = 'atlas.mysoft.log'
    _description = 'MySoft API Günlüğü'
    _order = 'id desc'

    company_id = fields.Many2one('res.company', string='Şirket', index=True)
    islem = fields.Char(string='İşlem')
    yontem = fields.Char(string='Yöntem')
    adres = fields.Char(string='Adres')
    istek = fields.Text(string='İstek')
    yanit = fields.Text(string='Yanıt')
    durum_kodu = fields.Integer(string='HTTP')
    basarili = fields.Boolean(string='Başarılı', index=True)
    sure_ms = fields.Integer(string='Süre (ms)')
    res_model = fields.Char(string='Model')
    res_id = fields.Many2oneReference(string='Kayıt', model_field='res_model')

    @api.autovacuum
    def _gc_eski(self):
        self.search([('create_date', '<', fields.Datetime.subtract(fields.Datetime.now(), days=90))], limit=20000).unlink()

    def action_kayit_ac(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}


class AtlasMysoftApi(models.AbstractModel):
    _name = 'atlas.mysoft.api'
    _description = 'MySoft API İstemcisi'

    @api.model
    def _ayar(self, company):
        company = company.sudo()
        if not company.atlas_mysoft_aktif:
            raise UserError(self.env._('%s için MySoft entegrasyonu açık değil (Ayarlar > Muhasebe > e-Fatura).', company.name))
        if not company.atlas_mysoft_client_id or not company.atlas_mysoft_client_secret:
            raise UserError(self.env._('MySoft erişim anahtarı (Client Id / Client Secret) girilmemiş.'))
        if not re.fullmatch(r'[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}', company.atlas_mysoft_client_id.strip()):
            raise UserError(self.env._('Client Id biçimi hatalı: MySoft Portal > Erişim Anahtarı ekranından indirilen dosyadaki '
                                       'GUID değerini girin (ör. 56d8a57f-1691-47da-850a-79b860a7011f).'))
        return company, API_ADRESLERI[company.atlas_mysoft_ortam or 'test']

    @api.model
    def _token(self, company, yenile=False):
        company, adres = self._ayar(company)
        anahtar = (self.env.cr.dbname, company.id, company.atlas_mysoft_ortam, company.atlas_mysoft_client_id)
        kayit = TOKEN_ONBELLEK.get(anahtar)
        if kayit and not yenile and kayit[1] > time.time() + 20:
            return kayit[0]
        veri = {'client_id': company.atlas_mysoft_client_id, 'client_secret': company.atlas_mysoft_client_secret,
                'grant_type': 'client_credentials'}
        baslangic = time.time()
        try:
            yanit = requests.post(f'{adres}/oauth/token', data=veri, timeout=30,
                                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
        except requests.RequestException as hata:
            self._gunluk(company, 'Token', 'POST', '/oauth/token', None, str(hata), 0, False, baslangic)
            raise UserError(self.env._('MySoft sunucusuna bağlanılamadı: %s', hata)) from hata
        try:
            icerik = yanit.json()
        except ValueError:
            icerik = {}
        token = icerik.get('access_token') if isinstance(icerik, dict) else None
        self._gunluk(company, 'Token', 'POST', '/oauth/token', {'client_id': company.atlas_mysoft_client_id},
                     {k: v for k, v in (icerik or {}).items() if k != 'access_token'} if isinstance(icerik, dict) else yanit.text[:500],
                     yanit.status_code, bool(token), baslangic)
        if not token:
            raise UserError(self.env._('MySoft token alınamadı (%(kod)s): %(mesaj)s', kod=yanit.status_code,
                                       mesaj=mesaj_bul(icerik) or yanit.text[:300]))
        TOKEN_ONBELLEK[anahtar] = (token, time.time() + int(icerik.get('expires_in') or 300))
        return token

    @api.model
    def _istek(self, company, yontem, yol, veri=None, params=None, ikili=False, islem=None, kayit=None):
        """API çağrısı. JSON yanıt (ikili=True ise bayt) döndürür; HTTP hatası veya success=false'ta UserError."""
        company, adres = self._ayar(company)
        tenant = company._atlas_mysoft_tenant()
        if tenant:
            if isinstance(veri, dict) and 'tenantIdentifierNumber' not in veri:
                veri = dict(veri, tenantIdentifierNumber=tenant)
            if yontem == 'GET':
                params = dict(params or {}, tenantIdentifierNumber=tenant)
        for deneme in range(2):
            token = self._token(company, yenile=deneme > 0)
            baslangic = time.time()
            try:
                yanit = requests.request(yontem, f'{adres}{yol}', json=veri if yontem != 'GET' else None, params=params, timeout=60,
                                         headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json, */*'})
            except requests.RequestException as hata:
                self._gunluk(company, islem or yol, yontem, yol, veri or params, str(hata), 0, False, baslangic, kayit)
                raise UserError(self.env._('MySoft sunucusuna bağlanılamadı: %s', hata)) from hata
            if yanit.status_code == 401 and deneme == 0:
                continue  # token süresi dolmuş olabilir: bir kez yenile
            break
        tur = (yanit.headers.get('Content-Type') or '').lower()
        if ikili and yanit.status_code < 400 and 'json' not in tur:
            self._gunluk(company, islem or yol, yontem, yol, veri or params, f'<{len(yanit.content)} bayt {tur}>',
                         yanit.status_code, True, baslangic, kayit)
            return yanit.content
        try:
            icerik = yanit.json()
        except ValueError:
            icerik = {'_metin': yanit.text[:2000]}
        basari = basari_mi(icerik)
        tamam = yanit.status_code < 400 and basari is not False
        self._gunluk(company, islem or yol, yontem, yol, veri or params, icerik, yanit.status_code, tamam, baslangic, kayit)
        if not tamam:
            raise UserError(self.env._('MySoft hatası (%(kod)s): %(mesaj)s', kod=yanit.status_code,
                                       mesaj=mesaj_bul(icerik) or yanit.text[:400] or self.env._('ayrıntı yok')))
        if ikili:
            # Bazı uçlar dosyayı JSON içinde base64 döndürür
            import base64
            b64 = anahtar_bul(icerik, [r'.*(zip|pdf|xml|html|content|file|data|base64).*'])
            if isinstance(b64, str):
                try:
                    return base64.b64decode(b64)
                except ValueError:
                    pass
            raise UserError(self.env._('MySoft dosya yanıtı tanınamadı; ayrıntı için MySoft günlüğüne bakın.'))
        return icerik

    @api.model
    def _gunluk(self, company, islem, yontem, yol, istek, yanit, kod, basarili, baslangic, kayit=None):
        def gizle(v):
            if isinstance(v, dict):
                return {k: ('***' if k in GIZLI_ANAHTARLAR else gizle(x)) for k, x in v.items()}
            if isinstance(v, list):
                return [gizle(x) for x in v]
            return v
        metin = lambda v: v if isinstance(v, str) else json.dumps(gizle(v), ensure_ascii=False, indent=1, default=str)  # noqa: E731
        try:
            degerler = {
                    'company_id': company.id, 'islem': islem, 'yontem': yontem, 'adres': yol,
                    'istek': metin(istek)[:50000] if istek is not None else False, 'yanit': metin(yanit)[:50000] if yanit is not None else False,
                    'durum_kodu': kod, 'basarili': basarili, 'sure_ms': int((time.time() - baslangic) * 1000),
                    'res_model': kayit._name if kayit else False, 'res_id': kayit.id if kayit else False,
            }
            if self.env.context.get('atlas_mysoft_ayni_islem'):
                self.env['atlas.mysoft.log'].sudo().create(degerler)
            else:
                # günlük, ana işlem geri alınsa da (hata durumunda) kalsın
                with self.env.registry.cursor() as cr:
                    self.env(cr=cr, su=True)['atlas.mysoft.log'].create(degerler)
        except Exception:  # noqa: BLE001
            _logger.exception('MySoft günlüğü yazılamadı')
