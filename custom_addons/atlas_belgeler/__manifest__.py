{
    'name': 'Atlas Belgeler',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Belge yönetimi: klasörler ve erişim yetkileri, etiketler, sürüm geçmişi, toplu yükleme, otomatik toplama, süreli paylaşım',
    'description': """
Belgeler
========
- Klasör ağacı; klasör bazında okuma / yazma grupları ve kullanıcıları (alt klasörler devralır)
- Belge: dosya veya bağlantı, etiketler, sahibi, cari, ilgili kayıt; kilitleme
- Yeni sürüm yükleme: önceki sürümler saklanır
- Toplu yükleme sihirbazı; kanban görünümünde klasör paneli
- Otomatik toplama kuralları: belirli modellerin (ör. alış faturası) ekleri ilgili klasöre belge olarak düşer
- Süreli paylaşım bağlantısı (giriş gerektirmez), indirme sayacı
    """,
    'author': 'Atlas',
    'depends': ['mail', 'base_setup'],
    'data': [
        'security/atlas_belgeler_security.xml',
        'security/ir.access.csv',
        'data/atlas_belgeler_data.xml',
        'wizard/atlas_belge_yukle_views.xml',
        'views/atlas_belgeler_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
