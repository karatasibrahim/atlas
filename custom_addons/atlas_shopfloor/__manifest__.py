{
    'name': 'Atlas Üretim Alanı (Shop Floor)',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Tablet operatör ekranı: iş merkezi ve operatör seçimi, iş emri adımları, zaman takibi, kalite adımları, hurda, duruş bildirimi',
    'description': """
Üretim alanı operatör ekranı
============================
- İş merkezi seçimi (durum: boş / çalışıyor / duruşta) ve operatör seçimi (PIN isteğe bağlı)
- İş emri listesi, iş emri ekranı: talimat, bileşenler, kalite kontrol adımları
- Başlat / Duraklat / Bitir, üretilen ve hatalı adet; süre sayacı (planlanan / gerçekleşen)
- Hurda (bileşen veya mamul), sorun bildirimi (uygunsuzluk), duruş bildirimi (kayıp nedeni) ve duruşu bitirme
- Son iş emri bitince üretimi tamamlama
- Kayıtlar OEE hesabının veri kaynağıdır (iş merkezi verimlilik kayıtları + hatalı adet)
    """,
    'author': 'Atlas',
    'depends': ['mrp', 'hr', 'atlas_kalite'],
    'data': [
        'security/ir.access.csv',
        'views/atlas_shopfloor_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_shopfloor/static/src/shopfloor/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
