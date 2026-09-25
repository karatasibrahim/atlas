"""Çek/senet bordro işlemleri ve durumları."""

EVRAK_TURU_SELECTION = [
    ('musteri_cek', 'Müşteri Çeki'),
    ('musteri_senet', 'Müşteri Senedi'),
    ('firma_cek', 'Firma Çeki'),
    ('firma_senet', 'Firma Senedi'),
]

DURUM_SELECTION = [
    ('portfoy', 'Portföyde'),
    ('tahsilde', 'Tahsilde (Bankada)'),
    ('teminatta', 'Teminatta (Bankada)'),
    ('ciro', 'Ciro Edildi'),
    ('tahsil', 'Tahsil Edildi'),
    ('karsiliksiz', 'Karşılıksız / Protestolu'),
    ('iade', 'İade Edildi'),
    ('verildi', 'Verildi (Ödenecek)'),
    ('odendi', 'Ödendi'),
    ('iptal', 'İptal'),
]

# islem: (etiket, taraf, yeni evrak mı, kabul edilen durumlar, yeni durum, cari gerekir mi, kasa/banka gerekir mi)
ISLEMLER = {
    'giris': ('Müşteri Çek/Senet Girişi', 'musteri', True, (), 'portfoy', True, None),
    'ciro': ('Ciro (Cariye Çıkış)', 'musteri', False, ('portfoy',), 'ciro', True, None),
    'tahsile_ver': ('Bankaya Tahsile Verme', 'musteri', False, ('portfoy',), 'tahsilde', False, 'bank'),
    'tahsilden_al': ('Tahsilden Geri Alma', 'musteri', False, ('tahsilde',), 'portfoy', False, None),
    'teminata_ver': ('Bankaya Teminata Verme', 'musteri', False, ('portfoy',), 'teminatta', False, 'bank'),
    'teminattan_al': ('Teminattan Geri Alma', 'musteri', False, ('teminatta',), 'portfoy', False, None),
    'tahsil': ('Tahsil', 'musteri', False, ('portfoy', 'tahsilde'), 'tahsil', False, 'bank_cash'),
    'karsiliksiz': ('Karşılıksız / Protesto', 'musteri', False, ('portfoy', 'tahsilde'), 'karsiliksiz', False, None),
    'musteriye_iade': ('Müşteriye İade', 'musteri', False, ('portfoy',), 'iade', False, None),
    'firma_cikis': ('Firma Çek/Senet Çıkışı', 'firma', True, (), 'verildi', True, None),
    'firma_odeme': ('Firma Çek/Senet Ödemesi', 'firma', False, ('verildi',), 'odendi', False, 'bank_cash'),
    'firma_iade': ('Firma Çek/Senet İadesi', 'firma', False, ('verildi',), 'iade', False, None),
}
ISLEM_SELECTION = [(key, value[0]) for key, value in ISLEMLER.items()]
