{
    'name': 'Atlas e-İmza',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Sign',
    'summary': 'PDF belgeleri e-posta bağlantısıyla imzalatma: sıralı/paralel imzacılar, imza çizimi, denetim izi, imzalı PDF',
    'description': """
e-İmza (basit elektronik imza)
==============================
- PDF yükle, imzacıları (sıralı veya paralel) ekle, gönder
- İmzacıya özel bağlantı: belgeyi görüntüleme, imzayı çizme veya adını yazma, reddetme
- İmzalar belirlenen sayfaya basılır; sona IP, tarayıcı, zaman ve SHA-256 özetlerini içeren denetim sayfası eklenir
- Tamamlanınca imzalı belge tüm imzacılara ve ilgili kayda gönderilir
- Hatırlatma e-postaları ve son tarih kontrolü

Not: 5070 sayılı Kanun'daki nitelikli elektronik imza (NES / mali mühür) yerine geçmez.
    """,
    'author': 'Atlas',
    'depends': ['mail'],
    'data': [
        'security/atlas_imza_security.xml',
        'security/ir.access.csv',
        'data/atlas_imza_data.xml',
        'views/atlas_imza_views.xml',
        'views/atlas_imza_templates.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
