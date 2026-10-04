{
    'name': 'Atlas Onaylar',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Approvals',
    'summary': 'Onay akışları: kategoriler, çok seviyeli / sıralı onaylayıcılar, yönetici onayı, satın alma-satış-fatura onay kuralları',
    'description': """
Onay Akışları
=============
- Onay kategorileri: onaylayıcılar (zorunlu / sıra), gereken onay sayısı, sıralı onay, yönetici onayı
- Kategoriye göre talep formu alanları (tarih, dönem, tutar, cari, ürün, miktar, referans, belge eki: yok / isteğe bağlı / zorunlu)
- Onaylayıcıya aktivite, onay / red (nedenli), talep edene bildirim
- Kayıt onay kuralları: koşula uyan satın alma, satış siparişi ve faturalar onaylanmadan onaylanamaz/işlenemez;
  onaydan sonra tutar artarsa yeniden onay gerekir
    """,
    'author': 'Atlas',
    'depends': ['mail', 'product', 'hr', 'purchase', 'sale_management', 'account'],
    'data': [
        'security/atlas_onay_security.xml',
        'security/ir.access.csv',
        'data/atlas_onay_data.xml',
        'wizard/atlas_onay_red_views.xml',
        'views/atlas_onay_views.xml',
        'views/atlas_onay_kayit_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
