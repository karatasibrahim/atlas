{
    'name': 'Atlas Zaman Çizelgesi',
    'version': '20.0.1.0.0',
    'category': 'Services/Timesheets',
    'summary': 'Haftalık zaman çizelgesi tablosu, sayaç (görev ve üst çubuk), onay ve kilitleme, eksik kayıt hatırlatmaları',
    'description': """
Zaman Çizelgesi
===============
- Haftalık tablo: proje/görev satırları × günler; "1:30" veya "1,5" ile hızlı giriş, mesai saatine göre günlük toplam renklendirme,
  geçen haftanın satırları hazır gelir; onaylayıcılar çalışan seçebilir ve haftayı tek tıkla onaylar
- Sayaç: görev formundan veya tablodan başlat; üst çubukta çalışan süre; durdurunca yuvarlanmış süre kayda yazılır
- Onay: onaylanan kayıtlar kilitlenir (değiştirilemez/silinemez), onay kaldırılabilir; "Onay Bekleyenler" menüsü
- Hatırlatma: geçen hafta eksik kayıt giren çalışanlara ve onay bekleyen yöneticilere pazartesi e-postası
    """,
    'author': 'Atlas',
    'depends': ['hr_timesheet'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_zaman_data.xml',
        'views/atlas_zaman_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_zaman/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
