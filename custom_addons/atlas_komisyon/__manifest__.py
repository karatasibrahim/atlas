{
    'name': 'Atlas Satış Komisyonu',
    'version': '20.0.1.0.0',
    'category': 'Sales/Commission',
    'summary': 'Satış temsilcisi ve ekip komisyon planları: başarı oranları, hedefler, kademeler, dönemsel hesap ve rapor',
    'description': """
Atlas Satış Komisyonu (Enterprise sale_commission eşleniği)
==========================================================
- Komisyon planı: dönem (aylık / çeyreklik / yıllık), kişi ya da satış ekibi bazında
- Başarı bazlı plan: satış tutarı, faturalanan tutar, satılan / faturalanan miktar; ürün ya da kategori filtresi, oran
- Hedef bazlı plan: dönem hedefleri ve kademeler (ör. %50 → 0 ₺, %100 → 5.000 ₺, %150 → 9.000 ₺; aradaki değerler doğrusal)
- Elle düzeltmeler (prim, kesinti), planlara temsilci / ekip atama (tarih aralığıyla)
- Komisyon raporu: temsilci, dönem, başarı, hedef, gerçekleşme oranı, komisyon; kaynak belge satırlarına kadar ayrıntı
- İade faturaları başarıdan düşülür; döviz tutarları şirket para birimine çevrilir
- Temsilci yalnız kendi komisyonunu görür; satış yöneticisi tümünü
    """,
    'author': 'Atlas',
    'depends': ['sale', 'account'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_komisyon_data.xml',
        'views/atlas_komisyon_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
