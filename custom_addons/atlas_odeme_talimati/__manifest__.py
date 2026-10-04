{
    'name': 'Atlas Toplu Ödeme Talimatı',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Tedarikçi faturalarından toplu ödeme talimatı: IBAN kontrolü, toplu ödeme kaydı, banka yükleme dosyası (Excel/CSV)',
    'description': """
Toplu ödeme talimatı
====================
- Vadesi gelen alış faturalarını seçip talimata ekleme (cari bazında gruplanır, kısmi ödeme tutarı girilebilir)
- Faturasız ödeme satırı (avans, kira vb.)
- Onay: IBAN doğrulaması, her cari için ödeme kaydı (banka bekleyen hesabı), faturalar kapanır
- Banka yükleme dosyası: Excel ve CSV (alıcı, VKN, IBAN, tutar, açıklama)
- Banka ekstresi eşleştikçe talimat tamamlanır; onaylı talimat iptal edilebilir (ödemeler geri alınır)
    """,
    'author': 'Atlas',
    'depends': ['atlas_kasa_banka'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_odeme_talimati_data.xml',
        'wizard/atlas_odeme_talimati_ekle_views.xml',
        'views/atlas_odeme_talimati_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
