{
    'name': 'Atlas Ana Üretim Planlama (MPS)',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Dönemsel talep tahmini, güvenlik stoğu, önerilen üretim/satınalma, dolaylı (bileşen) talep',
    'description': """
Ana Üretim Planlama
===================
- Ürün / depo bazında plan satırları: güvenlik stoğu, en az / en çok ikmal, tedarik tipi (üretim / satınalma)
- Gün, hafta veya ay dönemleri; dönem sayısı ayarlanabilir
- Her dönem için: başlangıç stoğu, tahmini talep, gerçek talep (onaylı çıkışlar ve üretim tüketimleri),
  dolaylı talep (üst ürünlerin önerilen üretiminden bileşen ihtiyacı), onaylı ikmal (açık giriş ve teklifler),
  önerilen ikmal ve tahmini stok
- Önerilen ikmal elle değiştirilebilir; tek tıkla üretim emri veya satınalma teklifi oluşturulur
- Otomatik tetikleme: günlük görev ilk dönemin önerisini sipariş eder
    """,
    'author': 'Atlas',
    'depends': ['mrp', 'purchase_stock'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_mps_data.xml',
        'views/atlas_mps_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_mps/static/src/mps/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
