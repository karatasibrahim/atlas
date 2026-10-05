{
    'name': 'Atlas Finansal Raporlar',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Etkileşimli finansal raporlar: aç-kapa, dönem karşılaştırma, kalem denetimi, notlar, Excel/PDF, otomatik gönderim',
    'description': """
Etkileşimli Finansal Raporlar (Enterprise "Muhasebe Raporları" eşleniği, TDHP'ye göre)
======================================================================================
- Tek ekran: tarih ön ayarları, dönem karşılaştırması (önceki dönem / geçen yıl, N dönem, % değişim),
  taslaklar, sıfırları gizle, tümünü aç, yevmiye / cari / analitik filtreleri, çoklu şirket
- Satıra tıklayınca alt kırılım (sınıf → grup → ana hesap → alt hesap → cari → yevmiye kalemi), tutara tıklayınca
  o tutarı oluşturan yevmiye kalemleri (denetim), satır notları, Excel ve PDF çıktısı
- Raporlar: Bilanço, Gelir Tablosu, Nakit Akış Tablosu, Yönetici Özeti, Mizan, Büyük Defter, Cari Defter,
  Alacak / Borç Yaşlandırma (geçmiş tarihe göre), Gerçekleşmemiş Kur Farkları, Banka Denkleştirme, Vergi Raporu,
  Yevmiye Raporu, Amortisman Tablosu
- Satır tanımlı raporlar (hesap kodu öneki, toplam, formül) yapılandırılabilir; yeni rapor tanımlanabilir
- Otomatik gönderim: seçilen rapor dönemsel olarak Excel/PDF e-postayla gönderilir
    """,
    'author': 'Atlas',
    'depends': ['atlas_donem', 'atlas_kasa_banka'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_finansal_tanim_data.xml',
        'data/atlas_finansal_rapor_data.xml',
        'views/atlas_finansal_views.xml',
        'report/atlas_finansal_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_finansal/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
