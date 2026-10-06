{
    'name': 'Atlas Şirketler Arası Kurallar',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Grup şirketleri arasında fatura ↔ alış faturası ve satış ↔ satın alma siparişlerini otomatik oluşturma',
    'description': """
Atlas Şirketler Arası Kurallar (Enterprise account_inter_company_rules / sale_purchase_inter_company_rules eşleniği)
=================================================================================================================
- Bir şirketin diğer grup şirketine kestiği müşteri faturası / iadesi onaylanınca, karşı şirkette tedarikçi faturası /
  iadesi oluşur (ve tersi); taslak ya da onaylı, karşı şirketin vergileri ürün tanımından eşlenir
- Grup şirketine satış siparişi onaylanınca karşı şirkette satın alma siparişi; satın alma siparişi onaylanınca karşı
  şirkette satış siparişi oluşur; isteğe bağlı otomatik onay ve depo seçimi
- Kurallar her şirketin kendi kartında (alıcı şirketin ayarı geçerlidir); belgeler birbirine bağlıdır, döngü oluşmaz
- Oluşturan kullanıcı şirket bazında seçilebilir
    """,
    'author': 'Atlas',
    'depends': ['sale_stock', 'purchase_stock', 'account'],
    'data': [
        'views/atlas_sirketler_arasi_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
