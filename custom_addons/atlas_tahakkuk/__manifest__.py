{
    'name': 'Atlas Gelecek Aylara Ait Gider / Gelir',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Ertelenmiş gider ve gelir: 180/280, 380/480 ile aylık tahakkuk (dönemsellik ilkesi)',
    'description': """
Gelecek aylara / yıllara ait gider ve gelirler
==============================================
- Fatura satırına hizmet başlangıç ve bitiş tarihi girilince satır otomatik ertelenir
- Erteleme fişi: gider → 180 (gelecek 12 ay içi) / 280 (sonraki yıllar); gelir → 380 / 480
- Aylık tahakkuk fişleri gün oranına göre; tarihi gelmeyenler taslak kalır ve tarihinde otomatik onaylanır
- Yıl sonlarında 280 → 180 (480 → 380) virmanı otomatik planlanır
- Faturasız (elle) erteleme kaydı: peşin ödenen sigorta, kira vb.
- Fatura taslağa alınınca erteleme kayıtları geri alınır
    """,
    'author': 'Atlas',
    'depends': ['atlas_donem'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_tahakkuk_data.xml',
        'views/atlas_tahakkuk_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
