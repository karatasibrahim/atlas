{
    'name': 'Atlas Banka Kredileri',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Banka kredisi takibi: ödeme planı (eşit taksit / eşit anapara / balon), BSMV-KKDF, 300/303/400/780 kayıtları',
    'description': """
Banka kredileri
===============
- Kredi kartı: banka hesabı, kullanım tarihi, tutar, faiz (aylık / yıllık), taksit sayısı, BSMV / KKDF, dosya masrafı
- Ödeme planı: eşit taksitli, eşit anaparalı veya anapara vade sonunda (balon)
- Kullanım fişi: banka (ekstreyle eşleşen transit kayıt) / 300-303 (ertesi yıl sonuna kadar) ve 400 (sonrası)
- Taksit fişleri: anapara 300/303, faiz + BSMV + KKDF 780; tarihi gelmeyenler taslak ve tarihinde otomatik onay
- Yıl sonu 400 → 303 virmanı, erken kapama, vade takvimi
    """,
    'author': 'Atlas',
    'depends': ['atlas_kasa_banka', 'atlas_donem'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_kredi_data.xml',
        'views/atlas_kredi_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
