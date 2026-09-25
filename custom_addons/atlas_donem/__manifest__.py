{
    'name': 'Atlas Dönem Sonu İşlemleri',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Kur değerleme, 7/A yansıtma, dönem kapanış/açılış, yevmiye madde no, sabit kıymet ve amortisman',
    'description': """
Dönem sonu işlemleri
====================
- Dönem sonu kur değerlemesi (VUK 280): dövizli kasa, banka, cari ve diğer hesaplar; 646/656
- 7/A gider yansıtma (750/760/770/780 → 630/631/632/660)
- Dönem kapanışı: 7 grubu kapanışı, 6 → 690 → 692 → 590/591, bilanço kapanış fişi ve yeni yıl açılış fişi
- Yevmiye madde numaralandırma ve dönem kilidi
- Sabit kıymetler: VUK normal / azalan bakiyeler, kıst amortisman, aylık/yıllık kayıt, satış/hurda
    """,
    'author': 'Atlas',
    'depends': ['atlas_rapor', 'atlas_kasa_banka'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_donem_data.xml',
        'wizard/atlas_kur_degerleme_views.xml',
        'wizard/atlas_yansitma_views.xml',
        'wizard/atlas_yevmiye_no_views.xml',
        'views/atlas_donem_kapanis_views.xml',
        'views/atlas_sabit_kiymet_views.xml',
        'wizard/atlas_amortisman_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
