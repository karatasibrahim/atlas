{
    'name': 'Atlas Kalite',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Quality',
    'summary': 'Kontrol noktaları, kalite kontrolleri, uygunsuzluk ve DÖF (düzeltici/önleyici faaliyet)',
    'description': """
Kalite yönetimi
===============
- Kontrol noktaları: giriş (mal kabul), üretim ara (iş emri / operasyon), final (üretim emri), sevkiyat öncesi
- Test tipleri: talimat, geçti/kaldı, ölçüm (nominal ve tolerans), kontrol listesi, fotoğraf, numune sayımı
- Kontrol yeri: belge, ürün veya lot/seri başına; sıklık: her seferinde, rastgele %, periyodik, isteğe bağlı
- Bekleyen kontrol varken mal kabul / sevkiyat / iş emri / üretim tamamlanamaz
- Uygunsuzluk (kalite uyarısı): aşamalar, kök neden, düzeltici ve önleyici faaliyet
- Kalite kontrol fişinde QR kod (ATL:QC:...)
    """,
    'author': 'Atlas',
    'depends': ['atlas_barkod', 'mrp', 'stock', 'mail'],
    'data': [
        'security/atlas_kalite_security.xml',
        'security/ir.access.csv',
        'data/atlas_kalite_data.xml',
        'views/atlas_kalite_tanim_views.xml',
        'views/atlas_kalite_nokta_views.xml',
        'views/atlas_kalite_kontrol_views.xml',
        'views/atlas_kalite_uyari_views.xml',
        'views/stock_mrp_views.xml',
        'report/atlas_kalite_report.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_kalite/static/src/barkod_kalite/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
