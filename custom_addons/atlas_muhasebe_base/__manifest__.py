{
    'name': 'Atlas Muhasebe - Temel',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Tek Düzen Hesap Planı, TCMB kurları ve tam muhasebe yetkileri',
    'description': """
Atlas ERP muhasebe altyapısı
============================
- Türkiye yerelleştirmesi (l10n_tr) ve Tek Düzen Hesap Planı'nın yüklenmesi
- TCMB döviz kurlarının otomatik / geçmişe dönük çekilmesi
- Community sürümünde gizli olan tam muhasebe özellikleri için "Muhasebeci" rolü
    """,
    'author': 'Atlas',
    'depends': ['account', 'l10n_tr', 'contacts', 'base_report_wkhtmltox'],
    'data': [
        'security/atlas_security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'data/menu_data.xml',
        'wizard/atlas_tcmb_rate_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_currency_rate_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_atlas_post_init',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
