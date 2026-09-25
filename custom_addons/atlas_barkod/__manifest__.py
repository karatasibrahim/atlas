{
    'name': 'Atlas Barkod',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Telefon kamerasıyla barkod/QR: mal kabul, sevkiyat toplama, stok sayımı, üretimde malzeme okutma, seri QR etiketleri',
    'description': """
Mobil barkod uygulaması
=======================
- Telefon kamerası veya klavye olarak çalışan okuyucu ile barkod / QR okutma
- Mal kabul, sevkiyat toplama, stok sayımı, üretimde malzeme ve mamul seri okutma
- Seri takibi: seri numarası üretme, her seri için QR etiket
- Üretim emri çıktısında QR kod
- İş mantığı sunucu tarafında (atlas.barkod); native mobil uygulama /json/2 API ile aynı metotları kullanabilir
    """,
    'author': 'Atlas',
    'depends': ['atlas_stok', 'barcodes', 'mrp', 'stock'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_barkod_data.xml',
        'views/product_views.xml',
        'report/atlas_barkod_reports.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_barkod/static/src/barkod_app/**/*',
        ],
    },
    'post_init_hook': '_atlas_barkod_post_init',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
