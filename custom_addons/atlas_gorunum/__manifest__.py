{
    'name': 'Atlas Gantt ve Harita Görünümleri',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Gantt (sürükle-bırak planlama) ve harita görünüm türleri; üretim, iş emri, görev, izin, kiralama, kontak ve sipariş ekranlarında',
    'description': """
Gantt ve Harita Görünümleri
===========================
- Yeni görünüm türleri: atlas_gantt ve atlas_harita; her modelde XML ile tanımlanabilir, arama/filtre/gruplama ile çalışır
- Gantt: gün / hafta / ay / yıl ölçeği, gruplara göre satırlar, çakışmalar alt alta, renk, ilerleme,
  sürükleyerek tarih ve grup değiştirme, sağ kenardan süre uzatma, boş hücreye tıklayarak kayıt oluşturma
- Harita: OpenStreetMap üzerinde işaretler, aynı adresteki kayıtlar tek işarette, liste-harita eşlemesi,
  eksik koordinatları adresten bulma (base_geolocalize)
- Hazır ekranlar: üretim emirleri, iş emirleri, proje görevleri (planlanan başlangıç alanı eklenir), izinler,
  kiralama siparişleri (Gantt); kontaklar, satış siparişleri (harita)

Leaflet 1.9.4 (BSD-2) yerel olarak paketlenmiştir; harita karoları OpenStreetMap'ten yüklenir.
    """,
    'author': 'Atlas',
    'depends': ['web', 'base_geolocalize', 'mrp', 'project', 'contacts', 'sale_management', 'hr_holidays', 'atlas_kiralama'],
    'data': [
        'views/atlas_gorunum_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_gorunum/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
