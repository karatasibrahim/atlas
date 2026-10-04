{
    'name': 'Atlas OEE Raporu',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Toplam Ekipman Etkinliği: Kullanılabilirlik × Performans × Kalite, duruş nedenleri (Pareto)',
    'description': """
OEE (Overall Equipment Effectiveness)
=====================================
- Kullanılabilirlik = çalışma süresi / planlanan üretim süresi (çalışma + duruş)
- Performans = ideal süre (iş emri beklenen süresi × üretilen adet oranı) / çalışma süresi
- Kalite = sağlam adet / (sağlam + hatalı)
- OEE = K × P × Ka; iş merkezi bazında ve toplam
- Duruş nedenleri: süre, adet ve pay (Pareto sırası)
- Veri: iş merkezi verimlilik kayıtları ve Üretim Alanı ekranından girilen hatalı adetler
- Ekran, PDF ve Excel (Muhasebe raporlarıyla aynı altyapı)
    """,
    'author': 'Atlas',
    'depends': ['atlas_rapor', 'atlas_shopfloor'],
    'data': ['security/ir.access.csv', 'views/atlas_oee_views.xml'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
