{
    'name': 'Atlas Telefon (VoIP)',
    'version': '20.0.1.0.0',
    'category': 'Productivity/VOIP',
    'summary': 'Santral entegrasyonu: tek tıkla arama (click-to-call), gelen arama ekran bildirimi, görüşme kaydı, cevapsız arama takibi',
    'description': """
Telefon / VoIP
==============
- Telefon alanlarındaki arama düğmesi: santral API'si üzerinden click-to-call (URL/gövde şablonlu, çoğu bulut santrale uyar)
  ya da bilgisayardaki softphone (tel:)
- Santral olay adresi (webhook): çalıyor / cevaplandı / kapandı / cevapsız; numaradan kişi bulunur
- Gelen aramada ilgili dahilideki kullanıcının ekranında kişi kartıyla bildirim
- Görüşme kayıtları (süre, ses kaydı bağlantısı, notlar), kişinin yazışmasına özet, cevapsız aramaya "geri ara" aktivitesi
    """,
    'author': 'Atlas',
    'depends': ['mail', 'bus'],
    'data': [
        'security/ir.access.csv',
        'views/atlas_voip_views.xml',
    ],
    'assets': {
        'web.assets_backend': ['atlas_voip/static/src/**/*'],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
