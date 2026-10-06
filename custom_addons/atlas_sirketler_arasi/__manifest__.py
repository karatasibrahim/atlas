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
- Faturalar karşı şirketin sipariş satırlarına bağlanır (faturalanan miktar, 3'lü eşleştirme); satır satır izlenebilirlik
- Teslimat şirketler arası transit lokasyona; gönderilen lot / seri numaraları karşı şirketin mal kabulüne aktarılır
- Ayarlar: Genel Ayarlar > Şirketler > Şirketler Arası İşlemler (ve şirket kartı); alıcı şirketin ayarı geçerlidir;
  belgeler birbirine bağlıdır, döngü oluşmaz; deposu olmayan karşı şirkete depo açılır
- Oluşturan kullanıcı şirket bazında seçilebilir
    """,
    'author': 'Atlas',
    'depends': ['sale_stock', 'purchase_stock', 'account', 'base_setup'],
    'data': [
        'views/atlas_sirketler_arasi_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
