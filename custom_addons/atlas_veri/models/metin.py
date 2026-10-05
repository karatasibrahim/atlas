"""Türkçe metin yardımcıları."""
import re
import unicodedata

from markupsafe import Markup

UST = str.maketrans({'i': 'İ', 'ı': 'I'})
ALT = str.maketrans({'İ': 'i', 'I': 'ı'})


def tr_buyuk(s):
    return (s or '').translate(UST).upper()


def tr_kucuk(s):
    return (s or '').translate(ALT).lower()


def tr_baslik(s):
    """Her kelimenin ilk harfi büyük (Türkçe kurallarıyla); 've', 'ile' gibi bağlaçlar küçük."""
    kucukler = {'ve', 'ile', 'veya', 'de', 'da', 'ki'}
    kelimeler = tr_kucuk(s).split(' ')
    return ' '.join(k if (i and k in kucukler) else (tr_buyuk(k[:1]) + k[1:]) for i, k in enumerate(kelimeler))


def normal(s):
    """Eşleştirme anahtarı: büyük/küçük harf, aksan ve fazla boşluk duyarsız."""
    s = tr_kucuk(str(s or '')).replace('ı', 'i')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w@.+-]', ' ', s).split())


def bosluk_tum(s):
    return re.sub(r'\s+', '', s or '')


def bosluk_fazla(s):
    return ' '.join((s or '').split())


def html_temizle(s):
    from odoo.tools import html2plaintext
    return ' '.join(html2plaintext(Markup(s or '')).split()) if s and '<' in s else s
