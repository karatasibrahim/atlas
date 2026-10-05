{
    'name': 'Atlas Üretim Analizi',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Üretim maliyet analizi ve maliyet yapısı raporu: gerçekleşen / beklenen bileşen, iş merkezi, işçilik maliyeti, verim '
               '(Enterprise mrp_account_enterprise eşleniği)',
    'description': """
Üretim Analizi
==============
- Biten her üretim emri için: üretilen / talep edilen miktar, verim %, toplam ve birim süre,
  bileşen maliyeti (tüketim hareketlerinin değeri), iş merkezi maliyeti (süre × saat ücreti),
  işçilik maliyeti (operatör süresi × çalışan saat maliyeti), ek maliyet, toplam ve birim maliyet
- Beklenen birim maliyetler (reçete açılımı × standart maliyet, operasyon süresi × saat ücreti) ve sapma
- Pivot / grafik / liste; üretim emri bitince otomatik güncellenir
- Maliyet Yapısı raporu (üretim emirlerinden): ürün bazında bileşenler ve operasyonlar dökümü
    """,
    'author': 'Atlas',
    'depends': ['mrp_account', 'hr'],
    'data': [
        'security/ir.access.csv',
        'views/analiz_views.xml',
        'report/maliyet_yapisi.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
