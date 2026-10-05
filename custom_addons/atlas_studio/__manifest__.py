{
    'name': 'Atlas Studio',
    'version': '20.0.2.0.0',
    'category': 'Productivity/Studio',
    'summary': 'Kod yazmadan özelleştirme: mevcut ekranlara alan ekleme, yeni kayıt türü / uygulama oluşturma, geri alma',
    'description': """
Studio
======
- Alan Ekle: herhangi bir modele özel alan (metin, sayı, para, tarih, seçim, bağlantı, etiket, dosya…);
  form görünümünde istenen alanın yanına, isteğe bağlı listeye ve aramaya eklenir
- Yeni Model / Uygulama: alanları tanımla; form, liste, arama görünümleri, menü, erişim hakları otomatik oluşur;
  isteğe bağlı mesajlaşma/aktiviteler, arşivleme, şirket ve sorumlu alanları
- Özelleştirmeler listesi: yapılan her değişiklik kayıtlı, tek tıkla geri alınır
    """,
    'author': 'Atlas',
    'depends': ['mail', 'base_setup', 'base_automation', 'web'],
    'data': [
        'security/ir.access.csv',
        'views/atlas_studio_views.xml',
        'views/atlas_studio_onay_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_studio/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
