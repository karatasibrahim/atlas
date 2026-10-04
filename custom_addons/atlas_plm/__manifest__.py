{
    'name': 'Atlas PLM',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/PLM',
    'summary': 'Mühendislik değişiklik emirleri (ECO), reçete revizyonları, onay akışı, teknik dokümanlar',
    'description': """
Ürün yaşam döngüsü yönetimi
===========================
- Mühendislik Değişiklik Emri (ECO): tip, aşama, öncelik, sorumlu, etiket
- Reçete revizyonu: mevcut reçetenin taslak kopyası üzerinde çalışılır, uygulanınca eski sürüm arşivlenir
- Sürüm takibi: reçete ve ürün sürüm numarası, önceki reçete bağlantısı, sürüm geçmişi
- Bileşen ve rota (operasyon) değişiklik özeti
- Aşama bazlı onay şablonları (zorunlu / isteğe bağlı / yorum)
- Yürürlük tarihi: hemen veya ileri tarihte otomatik uygulama
- Teknik dokümanlar uygulamada ürüne aktarılır
- ECO değişiklik özeti çıktısı
    """,
    'author': 'Atlas',
    'depends': ['mrp', 'mail', 'product'],
    'data': [
        'security/atlas_plm_security.xml',
        'security/ir.access.csv',
        'data/atlas_plm_data.xml',
        'views/atlas_plm_tanim_views.xml',
        'views/atlas_plm_eco_views.xml',
        'views/mrp_bom_views.xml',
        'report/atlas_plm_report.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
