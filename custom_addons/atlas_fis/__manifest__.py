{
    'name': 'Atlas Fişler ve Seri/Sayaç',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Mahsup, tahsil, tediye, açılış, kapanış, dekont fişleri ve belge seri/sayaç tablosu',
    'description': """
Netsis tarzı fiş ve numaralandırma
==================================
- Seri / sayaç tablosu: ön ek + (yıl) + sıra no, belge türüne ve yevmiyeye göre, firmaya özel
- GİB e-Fatura/e-Arşiv biçimi desteği (ABC2026000000001)
- Muhasebe fiş türleri: Mahsup, Tahsil, Tediye, Açılış, Kapanış, Dekont (her birinin ayrı sayacı)
- Tahsil/Tediye fişlerinde kasa karşılık satırı otomatik
- Cari alt hesabı seçilen satıra cari otomatik atanır
    """,
    'author': 'Atlas',
    'depends': ['atlas_cari'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_belge_turu_data.xml',
        'views/atlas_seri_views.xml',
        'views/account_move_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_atlas_fis_post_init',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
