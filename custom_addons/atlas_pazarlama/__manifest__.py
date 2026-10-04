{
    'name': 'Atlas Pazarlama Otomasyonu',
    'version': '20.0.1.0.0',
    'category': 'Marketing/Marketing Automation',
    'summary': 'Davranışa göre dallanan otomatik e-posta ve eylem akışları (açtı/tıkladı/yanıtladı), katılımcı takibi, istatistikler',
    'description': """
Pazarlama Otomasyonu
====================
- Kampanya: hedef model ve kitle filtresi, tekil alan (ör. e-posta ile mükerrer girişi önleme)
- Adımlar: e-posta (takipli toplu e-posta altyapısı) veya sunucu eylemi; bekleme süresi; adım filtresi
- Tetikleyiciler: başlangıç, önceki adımdan sonra, e-posta açıldı/açılmadı, tıklandı/tıklanmadı, yanıtlandı/yanıtlanmadı
- Kitleye sonradan uyan kayıtlar otomatik katılır; 15 dakikada bir çalışır, "Şimdi Çalıştır" ile elle tetiklenir
- Katılımcı bazında adım geçmişi; adım ve kampanya istatistikleri (gönderilen, açılan, tıklanan, yanıtlanan)
    """,
    'author': 'Atlas',
    'depends': ['mass_mailing'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_pazarlama_data.xml',
        'views/atlas_pazarlama_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
