{
    'name': 'Atlas Mobil',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Atlas mobil uygulaması (Flutter, Android/iOS) için sunucu API katmanı',
    'description': """
Atlas Mobil API
===============
Flutter mobil uygulamasının (odooMobile/) kullandığı, ekran başına tek çağrıyla veri döndüren sunucu metotları:

- Ana sayfa özeti: satış, tahsilat, depo, onay göstergeleri ve 7 günlük satış serisi
- Aktiviteler, cari kartı ve bakiye, ürün sorgulama
- Satış teklifi oluşturma / onaylama, CRM fırsat hattı
- Onay merkezi: Atlas onay talepleri + masraf + izin onayları tek listede
- Personel: konumlu giriş/çıkış, fiş fotoğraflı masraf, izin talebi
- Depo işlemleri atlas.barkod üzerinden (mal kabul, sevkiyat, sayım, üretim)

Uygulama oturumla (/web/session/authenticate) giriş yapar ve /web/dataset/call_kw ile atlas.mobil metotlarını çağırır;
tüm yetki ve kayıt kuralları kullanıcının kendi haklarıyla uygulanır.
    """,
    'author': 'Atlas',
    'depends': ['atlas_barkod', 'atlas_onay', 'atlas_cari', 'sale_management', 'crm', 'purchase',
                'hr_attendance', 'hr_expense', 'hr_holidays'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
