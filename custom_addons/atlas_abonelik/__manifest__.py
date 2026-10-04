{
    'name': 'Atlas Abonelikler',
    'version': '20.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Yinelenen satış: abonelik planları, dönemsel otomatik fatura, MRR, durdurma / kapanış, yenileme',
    'description': """
Abonelik yönetimi
=================
- Planlar: her N gün / hafta / ay / yıl; otomatik onaylı veya taslak fatura; isteğe bağlı sabit süre (taahhüt)
- Satış siparişi abonelik olarak onaylanır; başlangıç, sonraki fatura, bitiş tarihleri
- Günlük görev vadesi gelen abonelikleri faturalar (sipariş satırlarından, dönem açıklamasıyla)
- MRR (aylık yinelenen gelir) ve ARR; durumlar: devam / durduruldu / kapandı, kapanış nedenleri
- Yenileme (yeni dönem siparişi) ve upsell (ek satır), yenilenecek / süresi biten listeleri
- Abonelik analizi (MRR pivot / grafik)
    """,
    'author': 'Atlas',
    'depends': ['sale_management'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_abonelik_data.xml',
        'views/atlas_abonelik_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
