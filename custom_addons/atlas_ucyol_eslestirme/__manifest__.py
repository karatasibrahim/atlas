{
    'name': 'Atlas 3\'lü Eşleştirme',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Satın alma siparişi – mal kabul – tedarikçi faturası eşleştirmesi; ödemeye serbest bırakma (Release to Pay)',
    'description': """
Atlas 3'lü Eşleştirme (Enterprise account_3way_match eşleniği)
============================================================
- Her tedarikçi faturası satırı bağlı satın alma satırıyla karşılaştırılır: sipariş miktarı, teslim alınan miktar,
  daha önce faturalanan miktar ve birim fiyat
- Satır durumu: Ödenebilir / Teslimat bekleniyor / İstisna (fazla faturalama, fiyat farkı); fatura durumu satırlardan
- Mal kabul yapıldıkça, faturalar onaylandıkça durum kendiliğinden güncellenir
- Elle "Ödemeye serbest bırak" ya da "Beklet" (gerekçeyle, chatter kaydı)
- Şirket ayarları: fiyat ve miktar toleransı (%), ödenebilir olmayan faturaya ödeme kaydını engelleme
- Tedarikçi faturaları listesinde durum sütunu ve filtreleri
    """,
    'author': 'Atlas',
    'depends': ['purchase_stock', 'account'],
    'data': [
        'views/atlas_ucyol_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
