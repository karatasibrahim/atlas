{
    'name': 'Atlas Muhasebe Raporları',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Mizan, büyük defter, yevmiye defteri, bilanço, gelir tablosu, yaşlandırma, KDV özeti',
    'description': """
TDHP'ye göre yasal ve yönetim raporları
=======================================
- Mizan (1/2/3 hane ve detay seviyeli, devirli)
- Büyük Defter / Muavin (yürüyen bakiyeli)
- Yevmiye Defteri (madde numaralı, ana hesap / detay biçiminde)
- Bilanço ve Gelir Tablosu (TDHP / Tek Düzen biçimi, 7/A yansıtma seçeneği)
- Cari yaşlandırma (vade analizi)
- KDV özeti (hesaplanan / indirilecek)

Her rapor ekranda, PDF ve Excel olarak alınabilir.
    """,
    'author': 'Atlas',
    'depends': ['atlas_cari', 'atlas_fis'],
    'data': [
        'security/ir.access.csv',
        'report/atlas_rapor_report.xml',
        'wizard/atlas_rapor_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
