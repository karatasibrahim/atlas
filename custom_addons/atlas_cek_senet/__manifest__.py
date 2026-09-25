{
    'name': 'Atlas Çek / Senet',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Müşteri/firma çek ve senetleri, portföy, bordrolar ve muhasebe kayıtları',
    'description': """
Netsis tarzı çek / senet yönetimi
=================================
- Müşteri çeki / senedi: giriş, ciro, tahsile verme, teminata verme, tahsil, karşılıksız/protesto, iade
- Firma çeki / senedi: çıkış (tedarikçiye), ödeme, iade
- Her işlem bir bordro ile yapılır; bordro onayında muhasebe fişi ve evrak durumu güncellenir
- Portföy, vade analizi, ortalama vade, bordro çıktısı
    """,
    'author': 'Atlas',
    'depends': ['atlas_kasa_banka'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_cek_data.xml',
        'views/atlas_cek_views.xml',
        'views/atlas_cek_bordro_views.xml',
        'views/res_config_settings_views.xml',
        'report/atlas_cek_bordro_report.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_atlas_cek_senet_post_init',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
