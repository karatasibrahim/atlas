{
    'name': 'Atlas e-İrsaliye Hazırlık',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'e-İrsaliye sevk bilgileri: irsaliye tipi, araç/dorse plakaları, şoförler, taşıyıcı firma',
    'description': """
e-İrsaliye sevk bilgileri (GİB / entegratör gönderimine hazırlık)
=================================================================
- İrsaliye tipi: SEVK (e-İrsaliye) veya MATBUDAN (matbu irsaliye no ve tarihi)
- Plaka tablosu (araç / dorse, TR plaka biçim kontrolü) ve şoför tablosu (TCKN kontrolü)
- Taşıyıcı firma (VKN zorunlu); taşıyıcı seçilirse plaka/şoför isteğe bağlı
- e-İrsaliye kullanan şirkette sevkiyat doğrulanırken zorunlu bilgiler kontrol edilir
- İrsaliye çıktısında taşıyıcı, plakalar ve şoförler
    """,
    'author': 'Atlas',
    'depends': ['atlas_stok'],
    'data': [
        'security/ir.access.csv',
        'views/atlas_irsaliye_views.xml',
        'report/report_deliveryslip.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
