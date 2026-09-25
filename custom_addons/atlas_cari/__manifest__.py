{
    'name': 'Atlas Cari',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Cari kartlar, 120/320 alt hesapları, cari hareketleri ve cari ekstre',
    'description': """
Netsis tarzı cari hesap yönetimi
================================
- Cari kodu (120-GG-NNNN / 320-GG-NNNN) ve her cari için otomatik muhasebe alt hesabı
- Cari tipi (Alıcı / Satıcı / Alıcı + Satıcı), cari grubu, bölge, özel kodlar
- Cari hareketleri: yürüyen bakiyeli, hareket türüne göre
- Cari ekstre: PDF ve Excel
    """,
    'author': 'Atlas',
    'depends': ['atlas_muhasebe_base'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_cari_data.xml',
        'views/atlas_cari_tanim_views.xml',
        'views/atlas_cari_hareket_views.xml',
        'wizard/atlas_cari_ekstre_wizard_views.xml',
        'views/res_partner_views.xml',
        'report/atlas_cari_ekstre_report.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
