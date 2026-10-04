{
    'name': 'Atlas Ödeme Hatırlatma',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Vadesi geçmiş alacaklar için seviyeli ödeme hatırlatma: e-posta, mektup, tahsilat görevi',
    'description': """
Ödeme hatırlatma (tahsilat takibi)
==================================
- Hatırlatma seviyeleri: vadeden kaç gün sonra, e-posta, mektup, sorumluya görev
- Cari bazında gecikmiş tutar, en eski gecikme, sıradaki seviye
- Her fatura için gönderilen son seviye tutulur; aynı seviye tekrar gönderilmez
- Toplu veya tek tek gönderim, günlük otomatik gönderim (seviyede "otomatik" seçiliyse)
- Hatırlatma mektubu (PDF) e-postaya eklenir; carinin hatırlatması durdurulabilir
    """,
    'author': 'Atlas',
    'depends': ['atlas_cari', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_hatirlatma_data.xml',
        'report/atlas_hatirlatma_report.xml',
        'views/atlas_hatirlatma_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
