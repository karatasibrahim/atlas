import re
from datetime import date, datetime, timedelta

from odoo import fields, models
from odoo.exceptions import UserError

TR_TRANSLATE = str.maketrans('çğıöşüâîûÇĞIÖŞÜÂÎÛ', 'cgiosuaiuCGIOSUAIU')

# Otomatik algılamada başlık metinleri (normalize edilmiş, "içerir" karşılaştırması; ilk eşleşen kazanır)
COLUMN_KEYWORDS = {
    'tarih': (['islem tarihi', 'tarih'], ['valor']),
    'aciklama': (['aciklama', 'islem detayi', 'detay'], []),
    'tutar': (['islem tutari', 'tutar', 'miktar'], ['bakiye']),
    'borc': (['borc'], ['alacak']),
    'alacak': (['alacak'], ['borc']),
    'bakiye': (['bakiye'], []),
    'referans': (['dekont no', 'fis no', 'referans', 'islem no', 'dekont'], []),
}
COLUMN_KEYS = ['tarih', 'aciklama', 'tutar', 'borc', 'alacak', 'bakiye', 'referans']
DATE_FORMATS = ('%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%y', '%Y.%m.%d')
HEADER_SCAN_ROWS = 40


def normalize_text(value):
    """Küçük harf, Türkçe karakterler sadeleştirilmiş, tek boşluklu metin."""
    text = str(value or '').replace('İ', 'i').replace('I', 'ı').lower().replace('i̇', 'i')
    return re.sub(r'\s+', ' ', text.translate(TR_TRANSLATE)).strip()


def parse_amount(value):
    if value is None or value == '':
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r'(TRY|TL|USD|EUR|GBP|₺|\$|€|\s|\xa0)', '', str(value), flags=re.I)
    if not text:
        return 0.0
    negative = False
    if text.startswith('(') and text.endswith(')'):
        negative, text = True, text[1:-1]
    if text.endswith('-'):
        negative, text = True, text[:-1]
    if text.startswith('-'):
        negative, text = True, text[1:]
    text = text.lstrip('+')
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')  # 1.234,56
        else:
            text = text.replace(',', '')  # 1,234.56
    elif ',' in text:
        text = text.replace(',', '.')  # 1234,56
    elif text.count('.') > 1:
        text = text.replace('.', '')  # 1.234.567
    try:
        amount = float(text)
    except ValueError as e:
        raise UserError(f'Tutar okunamadı: {value}') from e
    return -amount if negative else amount


def parse_date(value, date_format=None):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 20000 < value < 80000:  # Excel seri tarih
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value).strip().split(' ')[0]
    for fmt in ([date_format] if date_format else []) + list(DATE_FORMATS):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def column_index(spec):
    """'A' -> 0, 'AB' -> 27; harf değilse None."""
    if spec and re.fullmatch(r'[A-Za-z]{1,2}', spec.strip()):
        index = 0
        for char in spec.strip().upper():
            index = index * 26 + ord(char) - 64
        return index - 1
    return None


class AtlasBankaEkstreSablon(models.Model):
    """Bankaya özel Excel ekstre şablonu. Alanlar boş bırakılırsa başlıklardan otomatik algılanır."""
    _name = 'atlas.banka.ekstre.sablon'
    _description = 'Banka Ekstre Şablonu'
    _order = 'name'

    name = fields.Char(string='Şablon Adı', required=True)
    banka_id = fields.Many2one('atlas.banka', string='Banka')
    baslik_satiri = fields.Integer(string='Başlık Satırı', help='Sütun başlıklarının bulunduğu satır no (1\'den başlar). 0 = otomatik bul.')
    col_tarih = fields.Char(string='Tarih Sütunu', help='Sütun harfi (ör. A) veya başlık metni (ör. İşlem Tarihi).')
    col_aciklama = fields.Char(string='Açıklama Sütunu')
    col_tutar = fields.Char(string='Tutar Sütunu', help='Tek tutar sütunu varsa (çıkışlar eksi). Borç/Alacak sütunları varsa boş bırakın.')
    col_borc = fields.Char(string='Borç (Çıkış) Sütunu')
    col_alacak = fields.Char(string='Alacak (Giriş) Sütunu')
    col_bakiye = fields.Char(string='Bakiye Sütunu')
    col_referans = fields.Char(string='Dekont / Referans Sütunu')
    tarih_formati = fields.Char(string='Tarih Biçimi', help='Metin tarihler için, ör. %d.%m.%Y. Boşsa yaygın biçimler denenir.')
    tutar_ters = fields.Boolean(string='Tutar İşaretini Ters Çevir', help='Bankanız çıkışları artı, girişleri eksi veriyorsa işaretleyin.')

    def _get_column_specs(self):
        return {key: self[f'col_{key}'] for key in COLUMN_KEYS} if self else {}

    # -------------------------------------------------------------------------
    # Ayrıştırma
    # -------------------------------------------------------------------------

    def _parse_rows(self, rows):
        """Excel satırlarından ekstre hareketlerini çıkarır.

        :param rows: satır değerleri listesi (openpyxl values_only)
        :return: tarih sırasına dizilmiş [{'date', 'aciklama', 'amount', 'bakiye', 'referans'}]
        """
        header_index, columns = self._detect_columns(rows)
        if 'tarih' not in columns or not ({'tutar', 'borc', 'alacak'} & columns.keys()):
            raise UserError(
                'Ekstrede tarih ve tutar (veya borç/alacak) sütunları bulunamadı. '
                'Bu banka için bir ekstre şablonu tanımlayıp sütunları belirtin.')

        def cell(row, key):
            index = columns.get(key)
            return row[index] if index is not None and index < len(row) else None

        date_format = self.tarih_formati if self else None
        transactions = []
        for row in rows[header_index + 1:]:
            row_date = parse_date(cell(row, 'tarih'), date_format)
            if not row_date:
                continue
            if 'tutar' in columns:
                amount = parse_amount(cell(row, 'tutar'))
                if self and self.tutar_ters:
                    amount = -amount
            else:
                amount = abs(parse_amount(cell(row, 'alacak'))) - abs(parse_amount(cell(row, 'borc')))
            if not amount:
                continue
            bakiye = cell(row, 'bakiye')
            transactions.append({
                'date': row_date,
                'aciklama': str(cell(row, 'aciklama') or '').strip(),
                'amount': round(amount, 2),
                'bakiye': parse_amount(bakiye) if bakiye not in (None, '') else None,
                'referans': str(cell(row, 'referans') or '').strip(),
            })
        if len(transactions) > 1 and transactions[0]['date'] > transactions[-1]['date']:
            transactions.reverse()  # yeniden eskiye sıralı ekstreler
        return transactions

    def _detect_columns(self, rows):
        specs = self._get_column_specs()
        header_index = self.baslik_satiri - 1 if self and self.baslik_satiri else self._find_header_row(rows)
        if header_index is None or header_index >= len(rows):
            raise UserError('Ekstrede başlık satırı bulunamadı (Tarih, Tutar/Borç/Alacak başlıkları aranır).')
        headers = [normalize_text(value) for value in rows[header_index]]

        columns = {}
        for key in COLUMN_KEYS:
            spec = specs.get(key)
            if spec:
                index = column_index(spec)
                if index is None:
                    wanted = normalize_text(spec)
                    index = next((i for i, h in enumerate(headers) if h == wanted), None)
                    if index is None:
                        index = next((i for i, h in enumerate(headers) if wanted in h), None)
                if index is not None:
                    columns[key] = index
            else:
                index = self._auto_column(headers, key, used=set(columns.values()))
                if index is not None:
                    columns[key] = index
        if {'borc', 'alacak'} <= columns.keys() and 'tutar' in columns and not specs.get('tutar'):
            del columns['tutar']  # borç/alacak sütunları varsa onları kullan
        return header_index, columns

    @staticmethod
    def _auto_column(headers, key, used):
        keywords, excludes = COLUMN_KEYWORDS[key]
        for keyword in keywords:
            for index, header in enumerate(headers):
                if index in used or not header or any(ex in header for ex in excludes):
                    continue
                if keyword in header:
                    return index
        return None

    @classmethod
    def _find_header_row(cls, rows):
        for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
            headers = [normalize_text(value) for value in row]
            has_date = cls._auto_column(headers, 'tarih', set()) is not None
            has_amount = any(cls._auto_column(headers, key, set()) is not None for key in ('tutar', 'borc', 'alacak'))
            if has_date and has_amount:
                return index
        return None
