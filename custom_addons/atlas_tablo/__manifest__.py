{
    'name': 'Atlas Hesap Tabloları',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Düzenlenebilir hesap tabloları (Excel benzeri), canlı ERP verisiyle pivot, Excel çıktısı '
               '(Enterprise spreadsheet_edition / documents_spreadsheet eşleniği)',
    'description': """
Hesap Tabloları
===============
- Odoo'nun o-spreadsheet motoruyla tam düzenleyici: formüller, biçimlendirme, grafikler, koşullu biçim, filtreler, çoklu sayfa
- Pivot görünümlerinden "Hesap Tablosuna Ekle": seçili gruplama ve ölçülerle canlı =PIVOT() bağlantısı (veri her açılışta güncel)
- Otomatik kaydetme, Excel (.xlsx) indirme, Belgeler klasörleriyle düzenleme
    """,
    'author': 'Atlas',
    'depends': ['spreadsheet', 'atlas_belgeler'],
    'data': [
        'security/ir.access.csv',
        'views/tablo_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_tablo/static/src/backend/**/*',
        ],
        'spreadsheet.o_spreadsheet': [
            'atlas_tablo/static/src/bundle/**/*',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
