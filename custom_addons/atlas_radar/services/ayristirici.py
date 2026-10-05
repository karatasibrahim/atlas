"""Ayrıştırıcılar: indirilen içerikten öğe listesi çıkarır.

Her öğe: {'kimlik', 'baslik', 'url', 'tarih', 'icerik'}  (kimlik: kaynak içinde benzersiz anahtar, genelde URL)
"""
import json
import re
from urllib.parse import urljoin, urldefrag

from lxml import etree
from lxml import html as lxml_html

from .metin import html_metin, tarih_bul, url_tarih


class AyristirmaHatasi(Exception):
    pass


def _oge(kimlik, baslik, url, tarih=None, icerik=''):
    return {'kimlik': str(kimlik)[:500], 'baslik': ' '.join((baslik or '').split())[:500] or url, 'url': url,
            'tarih': tarih, 'icerik': icerik or ''}


def html_liste(metin, taban_url, xpath='//a[@href]', desen=None, en_az_uzunluk=15, en_fazla=100):
    """Bağlantı listesi: xpath ile seçilen <a> öğeleri (desen: href'in uyması gereken düzenli ifade)."""
    try:
        doc = lxml_html.fromstring(metin)
    except (etree.ParserError, ValueError) as e:
        raise AyristirmaHatasi(f'HTML ayrıştırılamadı: {e}') from e
    try:
        secilen = doc.xpath(xpath or '//a[@href]')
    except etree.XPathError as e:
        raise AyristirmaHatasi(f'Geçersiz XPath: {xpath} ({e})') from e
    derli = re.compile(desen) if desen else None
    ogeler, gorulen = [], set()
    for a in secilen:
        if not isinstance(a, etree._Element):
            continue
        if a.tag != 'a':
            a = next(iter(a.xpath('.//a[@href]')), None)
            if a is None:
                continue
        href = (a.get('href') or '').strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        url = urldefrag(urljoin(taban_url, href))[0]
        if derli and not derli.search(url):
            continue
        baslik = ' '.join(a.text_content().split()).lstrip('–—-•· ')
        if len(baslik) < en_az_uzunluk or url in gorulen:
            continue
        gorulen.add(url)
        # Tarih: bağlantı metni → üst öğe metni → URL
        ust = a.getparent()
        ust_metin = ' '.join(' '.join(ust.itertext()).split()) if ust is not None else ''
        tarih = tarih_bul(baslik) or tarih_bul(ust_metin[:300]) or url_tarih(url)
        ogeler.append(_oge(url, baslik, url, tarih))
        if len(ogeler) >= en_fazla:
            break
    return ogeler


def rss(metin, taban_url, en_fazla=100):
    """RSS 2.0 ve Atom beslemeleri."""
    try:
        kok = etree.fromstring(metin.encode('utf-8') if isinstance(metin, str) else metin,
                               parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=True))
    except etree.XMLSyntaxError as e:
        raise AyristirmaHatasi(f'XML ayrıştırılamadı: {e}') from e
    if kok is None:
        raise AyristirmaHatasi('Boş besleme')
    ogeler = []
    yerel = lambda el, ad: next((c for c in el if isinstance(c.tag, str) and etree.QName(c).localname == ad), None)
    for item in kok.iter():
        if not isinstance(item.tag, str) or etree.QName(item).localname not in ('item', 'entry'):
            continue
        baslik_el = yerel(item, 'title')
        link_el = yerel(item, 'link')
        url = ''
        if link_el is not None:
            url = (link_el.get('href') or link_el.text or '').strip()
        url = urljoin(taban_url, url) if url else ''
        kimlik_el = yerel(item, 'guid') if yerel(item, 'guid') is not None else yerel(item, 'id')
        icerik_el = next((e for e in (yerel(item, 'description'), yerel(item, 'summary'), yerel(item, 'content')) if e is not None), None)
        tarih_el = next((e for e in (yerel(item, 'pubDate'), yerel(item, 'published'), yerel(item, 'updated'),
                                     yerel(item, 'date')) if e is not None), None)
        tarih = None
        if tarih_el is not None and tarih_el.text:
            from email.utils import parsedate_to_datetime
            try:
                tarih = parsedate_to_datetime(tarih_el.text.strip()).date()
            except (TypeError, ValueError):
                tarih = tarih_bul(tarih_el.text)
        kimlik = (kimlik_el.text or '').strip() if kimlik_el is not None and kimlik_el.text else url
        baslik = baslik_el.text if baslik_el is not None else ''
        if not (kimlik or baslik):
            continue
        ogeler.append(_oge(kimlik or baslik, baslik, url or taban_url, tarih,
                           html_metin(icerik_el.text) if icerik_el is not None else ''))
        if len(ogeler) >= en_fazla:
            break
    return ogeler


def yol_al(veri, yol):
    """'resultContainer.content' ya da 'items.0.title' biçiminde nokta yolu."""
    if not yol:
        return veri
    for parca in yol.split('.'):
        if isinstance(veri, dict):
            veri = veri.get(parca)
        elif isinstance(veri, list) and parca.isdigit() and int(parca) < len(veri):
            veri = veri[int(parca)]
        else:
            return None
        if veri is None:
            return None
    return veri


def json_api(metin, taban_url, liste_yolu='', kimlik='id', baslik='title', tarih='', icerik='', url_alani='',
             link_sablonu='', en_fazla=100):
    """JSON yanıtı: liste_yolu ile kayıt listesi, alan adları ile öğe. link_sablonu: '…/{slug}' gibi."""
    try:
        veri = json.loads(metin)
    except ValueError as e:
        raise AyristirmaHatasi(f'JSON ayrıştırılamadı: {e}') from e
    liste = yol_al(veri, liste_yolu)
    if not isinstance(liste, list):
        raise AyristirmaHatasi(f'"{liste_yolu or "kök"}" yolunda liste bulunamadı')
    ogeler = []
    for kayit in liste[:en_fazla]:
        if not isinstance(kayit, dict):
            continue
        k = yol_al(kayit, kimlik)
        b = yol_al(kayit, baslik)
        if k in (None, '') or not b:
            continue
        url = yol_al(kayit, url_alani) if url_alani else None
        if not url and link_sablonu:
            try:
                url = link_sablonu.format_map(_Sozluk(kayit))
            except (ValueError, IndexError):
                url = None
        url = urljoin(taban_url, url) if url else taban_url
        t = yol_al(kayit, tarih) if tarih else None
        ic = yol_al(kayit, icerik) if icerik else ''
        ogeler.append(_oge(k, html_metin(str(b)), url, tarih_bul(str(t)) if t else None, html_metin(str(ic or ''))))
    return ogeler


class _Sozluk(dict):
    def __missing__(self, anahtar):
        return ''


def sayfa(metin, taban_url, xpath=''):
    """Tek sayfa: (isteğe bağlı xpath ile seçilen bölümün) metni tek öğe olarak izlenir."""
    try:
        doc = lxml_html.fromstring(metin)
    except (etree.ParserError, ValueError) as e:
        raise AyristirmaHatasi(f'HTML ayrıştırılamadı: {e}') from e
    for el in doc.xpath('//script|//style|//noscript'):
        el.drop_tree()
    bolum = doc.xpath(xpath) if xpath else [doc]
    if not bolum:
        raise AyristirmaHatasi(f'Seçici sayfada bulunamadı: {xpath}')
    govde = '\n'.join(' '.join(b.text_content().split()) if hasattr(b, 'text_content') else str(b) for b in bolum)
    baslik = doc.findtext('.//title') or taban_url
    return [_oge(taban_url, baslik, taban_url, None, govde)]


def detay_metni(metin, xpath=''):
    """Detay sayfasından ana metin (xpath yoksa <main>/<article>/body)."""
    try:
        doc = lxml_html.fromstring(metin)
    except (etree.ParserError, ValueError):
        return ''
    for el in doc.xpath('//script|//style|//noscript|//nav|//header|//footer'):
        el.drop_tree()
    for secici in ([xpath] if xpath else []) + ['//main', '//article', '//body']:
        try:
            bulunan = doc.xpath(secici)
        except etree.XPathError:
            continue
        if bulunan:
            return ' '.join(' '.join(b.text_content().split()) for b in bulunan if hasattr(b, 'text_content'))[:20000]
    return ''
