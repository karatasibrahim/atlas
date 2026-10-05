{
    'name': 'Atlas Veri Temizleme',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Data Cleaning',
    'summary': 'Mükerrer kayıtları bul ve birleştir, metin biçimlerini düzelt (Enterprise data_merge / data_cleaning eşleniği)',
    'description': """
Veri Temizleme
==============
- Mükerrer kayıtlar: model başına tekilleştirme kuralları (tam / büyük-küçük harf ve aksan duyarsız eşleşme,
  kurallardan biri ya da tümü), benzerlik yüzdesi ve eşik, şirketler arası seçeneği, yoksayılan grupları hatırlama
- Birleştirme: ana kayıt seçimi; diğer kayıtlara olan tüm bağlantılar (ilişki ve referans alanları) ana kayda taşınır,
  ana kayıttaki boş alanlar doldurulur, kopyalar arşivlenir ya da silinir; carilerde Odoo cari birleştirme kuralları
- Herhangi bir listeden "Birleştir" eylemi (model başına açılır)
- Biçim temizliği: boşluk (tümü / fazlalık), Türkçe büyük-küçük harf (İ/ı doğru), telefon (uluslararası biçim), HTML temizleme;
  öneriler incelenip uygulanır ya da otomatik uygulanır
- Günlük tarama; bildirim alacak kullanıcılara aktivite
    """,
    'author': 'Atlas',
    'depends': ['data_recycle', 'product', 'phone_validation'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_veri_data.xml',
        'wizard/birlestir_views.xml',
        'views/atlas_veri_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
