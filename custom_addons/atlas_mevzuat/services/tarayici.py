"""Güvenli HTTP tarayıcı: robots.txt, zaman aşımı, yeniden deneme, hız sınırı, boyut sınırı, yönlendirme doğrulaması.

Yalnızca zamanlanmış görevden çağrılır; kullanıcı isteği içinde dış siteye bağlanılmaz.
"""
import logging
import threading
import time
import urllib.robotparser
from urllib.parse import urljoin, urlsplit

import requests

from .guvenlik import GuvenlikHatasi, cozumle, url_dogrula

_logger = logging.getLogger(__name__)

KULLANICI_AJANI = 'AtlasMevzuat/1.0 (ERP regulatory change monitor)'  # yalnız ASCII: bazı sunucular aksi halde yanıt vermiyor
EN_FAZLA_BOYUT = 5 * 1024 * 1024
EN_FAZLA_YONLENDIRME = 5
TEKRAR_DURUMLARI = {429, 500, 502, 503, 504}

_son_istek = {}
_kilit = threading.Lock()


class TaramaHatasi(Exception):
    pass


class RobotsEngeli(TaramaHatasi):
    pass


class Yanit:
    def __init__(self, url, durum, icerik, tur, sure_ms):
        self.url, self.durum, self.icerik, self.tur, self.sure_ms = url, durum, icerik, tur, sure_ms

    @property
    def metin(self):
        for kod in ('utf-8', 'windows-1254', 'iso-8859-9'):
            try:
                return self.icerik.decode(kod)
            except UnicodeDecodeError:
                continue
        return self.icerik.decode('utf-8', 'replace')


class Tarayici:
    """Kaynak başına bir örnek. `oturum` testlerde sahte oturumla değiştirilebilir."""

    def __init__(self, izinliler, zaman_asimi=20, deneme=3, bekleme=2.0, ssl_dogrula=True, robots=True,
                 oturum=None, cozumleyici=cozumle, uyku=time.sleep):
        self.izinliler = izinliler
        self.zaman_asimi = zaman_asimi
        self.deneme = max(1, deneme)
        self.bekleme = bekleme
        self.ssl_dogrula = ssl_dogrula
        self.robots = robots
        self.oturum = oturum or requests.Session()
        self.cozumleyici = cozumleyici
        self.uyku = uyku
        self._robots = {}

    # Hız sınırı: aynı alan adına iki istek arasında en az `bekleme` saniye
    def _hiz_siniri(self, host):
        with _kilit:
            gecen = time.monotonic() - _son_istek.get(host, 0)
            kalan = self.bekleme - gecen
            _son_istek[host] = time.monotonic() + max(kalan, 0)
        if kalan > 0:
            self.uyku(kalan)

    def robots_izinli(self, url):
        if not self.robots:
            return True
        parca = urlsplit(url)
        kok = f'{parca.scheme}://{parca.netloc}'
        if kok not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                y = self._getir(kok + '/robots.txt', robots_kontrol=False, deneme=1)
                if y.durum in (401, 403):
                    rp.disallow_all = True
                elif y.durum >= 400 or 'html' in (y.tur or ''):
                    rp.allow_all = True  # robots.txt yok (ya da hata sayfası): kısıt tanımlanmamış
                else:
                    rp.parse(y.metin.splitlines())
            except (TaramaHatasi, GuvenlikHatasi) as e:
                _logger.info('robots.txt okunamadı (%s): %s', kok, e)
                rp.allow_all = True
            self._robots[kok] = rp
        return self._robots[kok].can_fetch(KULLANICI_AJANI, url)

    def getir(self, url, metot='GET', govde=None, basliklar=None):
        return self._getir(url, metot=metot, govde=govde, basliklar=basliklar)

    def _getir(self, url, metot='GET', govde=None, basliklar=None, robots_kontrol=True, deneme=None):
        if robots_kontrol and not self.robots_izinli(url):
            raise RobotsEngeli(f'robots.txt bu adresin taranmasına izin vermiyor: {url}')
        hdr = {'User-Agent': KULLANICI_AJANI, 'Accept': '*/*', 'Accept-Language': 'tr-TR,tr;q=0.9'}
        hdr.update(basliklar or {})
        son_hata = None
        for sira in range(deneme or self.deneme):
            if sira:
                self.uyku(min(2 ** sira, 30))
            try:
                return self._tek_istek(url, metot, govde, hdr)
            except GuvenlikHatasi:
                raise
            except TaramaHatasi as e:
                son_hata = e
                if not getattr(e, 'tekrar', False):
                    raise
            except requests.RequestException as e:
                son_hata = TaramaHatasi(f'Bağlantı hatası: {e}')
        raise son_hata

    def _tek_istek(self, url, metot, govde, hdr):
        mevcut = url
        for _ in range(EN_FAZLA_YONLENDIRME + 1):
            parca = url_dogrula(mevcut, self.izinliler, self.cozumleyici)
            self._hiz_siniri(parca.hostname)
            bas = time.monotonic()
            r = self.oturum.request(metot, mevcut, data=govde, headers=hdr, timeout=self.zaman_asimi,
                                    verify=self.ssl_dogrula, allow_redirects=False, stream=True)
            try:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get('Location'):
                    mevcut = urljoin(mevcut, r.headers['Location'])
                    if r.status_code == 303 or (r.status_code in (301, 302) and metot == 'POST'):
                        metot, govde = 'GET', None
                    continue
                parcalar, boyut = [], 0
                for p in r.iter_content(65536):
                    boyut += len(p)
                    if boyut > EN_FAZLA_BOYUT:
                        raise TaramaHatasi(f'Yanıt boyutu sınırı aşıldı ({EN_FAZLA_BOYUT // 1024 // 1024} MB)')
                    parcalar.append(p)
                sure = int((time.monotonic() - bas) * 1000)
                yanit = Yanit(mevcut, r.status_code, b''.join(parcalar), r.headers.get('Content-Type', ''), sure)
            finally:
                r.close()
            if yanit.durum in TEKRAR_DURUMLARI:
                hata = TaramaHatasi(f'HTTP {yanit.durum}: {mevcut}')
                hata.tekrar = True
                raise hata
            return yanit
        raise TaramaHatasi('Çok fazla yönlendirme')
