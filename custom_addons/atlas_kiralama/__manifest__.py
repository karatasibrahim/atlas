{
    'name': 'Atlas Kiralama',
    'version': '20.0.1.0.0',
    'category': 'Sales/Rental',
    'summary': 'Ürün kiralama: süreye göre kira fiyatı, müsaitlik kontrolü, teslim / iade transferi, gecikme bedeli, takvim',
    'description': """
Kiralama
========
- Kiralık ürün ve fiyatları: saatlik / günlük / haftalık / aylık; süreye göre en uygun fiyat otomatik seçilir
- Kiralama siparişi: teslim ve iade tarihleri, müsaitlik kontrolü (çakışan kiralamalar ve stok)
- Teslim: stoktan "Kirada" lokasyonuna transfer; iade: geri transfer (seri numaraları korunur)
- Geç iadede günlük gecikme bedeli siparişe eklenir
- Kiralama uygulaması: siparişler, takvim, bugün teslim / iade, gecikmiş
    """,
    'author': 'Atlas',
    'depends': ['sale_stock'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_kiralama_data.xml',
        'views/atlas_kiralama_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
