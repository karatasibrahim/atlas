import csv
import functools
import io

from odoo.tools import file_open


# l10n_tr şablonunda Türkçe adı bulunmayan veya 3 haneli olarak yer almayan TDHP hesapları
TDHP_EKSIK = {
    '100': 'KASA',
    '102': 'BANKALAR',
    '111': 'ÖZEL KESİM TAHVİL, SENET VE BONOLARI',
    '112': 'KAMU KESİMİ TAHVİL, SENET VE BONOLARI',
    '221': 'ALACAK SENETLERİ',
    '295': 'PEŞİN ÖDENEN VERGİLER VE FONLAR',
    '540': 'YASAL YEDEKLER',
    '612': 'DİĞER İNDİRİMLER (-)',
    '671': 'ÖNCEKİ DÖNEM GELİR VE KÂRLARI',
    '772': 'GENEL YÖNETİM GİDERLERİ FARK HESABI',
}


@functools.cache
def tdhp_names():
    """TDHP 1/2/3 haneli hesap adları (l10n_tr hesap planı şablonundan): {'1': 'DÖNEN VARLIKLAR', '10': ..., '100': ...}."""
    names = {}
    with file_open('l10n_tr/data/template/account.account-tr.csv', 'rb') as f:
        content = f.read().decode('utf-8')
    for row in csv.DictReader(io.StringIO(content)):
        code = row.get('code', '')
        if code.isdigit() and len(code) <= 3:
            names[code] = (row.get('name@tr') or TDHP_EKSIK.get(code, ''), row.get('name') or '')
    for code, name in TDHP_EKSIK.items():
        names.setdefault(code, (name, ''))
    return names


def tdhp_name(code, fallback=''):
    """Türkçe TDHP adı; şablonda Türkçesi yoksa verilen ad (sistemdeki hesap adı), o da yoksa İngilizcesi."""
    tr, en = tdhp_names().get(code, ('', ''))
    return tr or fallback or en
