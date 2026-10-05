"""Metin yardımcıları: Türkçe normalleştirme, içerik özeti (SHA-256), fark, tarih ayıklama."""
import difflib
import hashlib
import html as html_lib
import re
from datetime import date

from lxml import html as lxml_html

AYLAR = {'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5, 'haziran': 6,
         'temmuz': 7, 'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9, 'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12,
         'aralik': 12}
_AY_DESEN = '|'.join(sorted(AYLAR, key=len, reverse=True))
RE_SAYISAL = re.compile(r'\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b')
RE_ISO = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})')
RE_YAZILI = re.compile(r'\b(\d{1,2})\s+(' + _AY_DESEN + r')\s+(\d{4})\b')
RE_URL_TARIH = re.compile(r'(20\d{2})(\d{2})(\d{2})')
# "… tarihinden itibaren / tarihinde yürürlüğe girer" gibi ifadelerin önündeki tarih
RE_YURURLUK = re.compile(r'(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{1,2}\s+(?:' + _AY_DESEN + r')\s+\d{4})'
                         r'[^.;\n]{0,40}?(?:tarihinden\s+(?:itibaren|sonra)|tarihinde\s+yürürlüğe|itibar[ıi]yla|'
                         r'tarihinden\s+geçerli|tarihi\s+itibar)', re.IGNORECASE)


def kucult(metin):
    """Türkçe kurallarına uygun küçük harf (İ→i, I→ı) ve boşluk sadeleştirme."""
    metin = (metin or '').replace('İ', 'i').replace('I', 'ı').lower()
    return ' '.join(metin.split())


def html_metin(icerik):
    """HTML parçasını düz metne çevirir (script/style atılır)."""
    if not icerik:
        return ''
    if '<' not in icerik:
        return ' '.join(html_lib.unescape(icerik).split())
    try:
        doc = lxml_html.fromstring(icerik)
    except Exception:  # bozuk HTML
        return ' '.join(re.sub(r'<[^>]+>', ' ', icerik).split())
    for el in doc.xpath('//script|//style|//noscript'):
        el.drop_tree()
    return ' '.join(doc.text_content().split())


def normallestir(metin):
    """Özet için kararlı biçim: boşluklar tek, satır başı/sonu boşluğu yok."""
    return '\n'.join(' '.join(s.split()) for s in (metin or '').splitlines() if s.strip())


def ozet(metin):
    return hashlib.sha256(normallestir(metin).encode('utf-8')).hexdigest()


def fark(eski, yeni, en_fazla=400):
    """Satır bazlı birleşik fark (unified diff)."""
    eski_s = normallestir(eski).splitlines() or ['']
    yeni_s = normallestir(yeni).splitlines() or ['']
    if len(eski_s) == 1 and len(yeni_s) == 1:
        # tek satırlık metinler: cümle bazında karşılaştır
        eski_s = re.split(r'(?<=[.!?])\s+', eski_s[0])
        yeni_s = re.split(r'(?<=[.!?])\s+', yeni_s[0])
    satirlar = list(difflib.unified_diff(eski_s, yeni_s, 'önceki', 'yeni', lineterm='', n=1))
    if len(satirlar) > en_fazla:
        satirlar = satirlar[:en_fazla] + ['… (fark kısaltıldı)']
    return '\n'.join(satirlar)


def benzerlik(a, b):
    return difflib.SequenceMatcher(None, kucult(a), kucult(b)).ratio()


def _tarih(g, a, y):
    try:
        return date(int(y), int(a), int(g))
    except ValueError:
        return None


def tarih_bul(metin):
    """Metindeki ilk geçerli tarihi döndürür (gg.aa.yyyy, yyyy-aa-gg, '5 Ekim 2026')."""
    if not metin:
        return None
    m = RE_ISO.search(metin)
    if m:
        t = _tarih(m.group(3), m.group(2), m.group(1))
        if t:
            return t
    for m in RE_SAYISAL.finditer(metin):
        t = _tarih(*m.groups())
        if t:
            return t
    for m in RE_YAZILI.finditer(kucult(metin)):
        t = _tarih(m.group(1), AYLAR[m.group(2)], m.group(3))
        if t:
            return t
    return None


def url_tarih(url):
    m = RE_URL_TARIH.search(url or '')
    return _tarih(m.group(3), m.group(2), m.group(1)) if m else None


def yururluk_bul(metin):
    """'01.01.2027 tarihinden itibaren' gibi ifadelerden yürürlük tarihi."""
    m = RE_YURURLUK.search(kucult(metin))
    return tarih_bul(m.group(1)) if m else None
