{
    'name': 'Atlas MySoft e-Belge Entegrasyonu',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'MySoft e-Belge API: e-Fatura / e-Arşiv / e-İrsaliye gönderimi, durum takibi, PDF, e-Arşiv iptal, mükellef sorgu, gelen e-faturalar',
    'description': """
MySoft entegratör bağlantısı (edocumentapi)
============================================
- Erişim anahtarı (Client Id / Client Secret) ile OAuth 2.0 token (5 dk, otomatik yenilenir); firma veya iş ortağı anahtarı
  (iş ortağında şirket VKN'si tenantIdentifierNumber olarak gönderilir); test ve canlı ortam
- Giden fatura: invoiceOutbox JSON (temel/ticari/e-Arşiv/ihracat; satış, iade, tevkifat, istisna, ihraç kayıtlı),
  Atlas seri numarası veya MySoft ön eki, doğrudan GİB'e ya da MySoft'ta taslak
- Onaylanan faturalar kuyruğa alınır, 10 dakikada bir gönderilir; durumlar getInvoiceOutboxStatusChanged ile güncellenir,
  hata/ret durumunda sorumluya aktivite
- PDF indirme, e-Arşiv iptali (ters kayıtla), e-posta gönderimi
- Mükellef sorgusu: onaydan önce alıcının e-Fatura mükellefiyeti ve posta kutusu etiketi GİB'den güncellenir
- Gelen e-faturalar: 30 dakikada bir alınır, UBL XML'den taslak alış faturası, ticari faturada kabul/red
- e-İrsaliye: tamamlanan sevkiyatlar (plaka, şoför, taşıyıcı) despatchOutbox ile gönderilir
- Tüm istek/yanıtlar MySoft Günlüğü'nde (gizli alanlar maskelenir)
    """,
    'author': 'Atlas',
    'depends': ['atlas_ebelge', 'atlas_irsaliye', 'stock', 'l10n_tr'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_mysoft_data.xml',
        'views/atlas_mysoft_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
