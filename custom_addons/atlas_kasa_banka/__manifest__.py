{
    'name': 'Atlas Kasa / Banka',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'TL/döviz kasaları, banka hesapları, virman, Excel banka ekstresi ve eşleştirme',
    'description': """
Netsis tarzı kasa ve banka yönetimi
===================================
- Kasa kartları (TL / döviz) ve banka hesap kartları (IBAN, Türkiye banka listesi)
- Kasa / banka hareketleri: yürüyen bakiyeli, hesabın kendi para biriminde
- Virman: kasa-banka, banka-banka, kasa-kasa (dövizler arası dahil)
- Banka ekstresi Excel (xlsx) içe aktarma: sütunlar otomatik algılanır, bankaya özel şablon tanımlanabilir
- Eşleştirme: bekleyen ödeme/virman, fatura (FIFO), cari ve kurala göre otomatik öneri
    """,
    'author': 'Atlas',
    'depends': ['atlas_fis'],
    'external_dependencies': {'python': ['openpyxl']},
    'data': [
        'security/ir.access.csv',
        'data/res_bank_data.xml',
        'data/atlas_belge_turu_data.xml',
        'views/account_journal_views.xml',
        'views/atlas_kasa_banka_hareket_views.xml',
        'views/atlas_banka_kural_views.xml',
        'views/atlas_banka_ekstre_sablon_views.xml',
        'views/account_bank_statement_line_views.xml',
        'wizard/atlas_virman_wizard_views.xml',
        'wizard/atlas_banka_ekstre_import_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_atlas_kasa_banka_post_init',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
