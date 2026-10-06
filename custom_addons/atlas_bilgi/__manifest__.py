{
    'name': 'Atlas Bilgi Bankası',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Knowledge',
    'summary': 'Şirket içi bilgi bankası: hiyerarşik makaleler, yetkiler, favoriler, şablonlar, öğeler, sürüm geçmişi, paylaşım',
    'description': """
Atlas Bilgi Bankası (Enterprise Knowledge eşleniği)
==================================================
- Çalışma Alanı / Paylaşılan / Özel bölümleri; sınırsız alt makale, sürükle-bırak ile taşıma ve sıralama
- Zengin metin düzenleyici (görsel, tablo, kontrol listesi, bağlantı, /komutlar), emoji simge, kapak görseli, tam genişlik, kilit
- Yetkiler: şirket içi erişim (düzenleme / okuma / yok) alt makalelere miras; üye bazında düzenleme / okuma / engelleme
- Favoriler, son düzenleyen, sürüm geçmişi ve geri yükleme, yorumlar (chatter)
- Öğeler: makalenin altında aşamalı (kanban) ve özellik (properties) alanlı kayıtlar
- Şablon galerisi (toplantı notu, süreç dokümanı, SSS, proje planı, karar kaydı)
- Çöp kutusu: 30 gün sonra kalıcı silme; geri yükleme
- Bağlantıyla herkese açık paylaşım (salt okunur sayfa)
- Makaleye gömülü görünümler: /Liste görünümü, /Kanban görünümü (herhangi bir menü; canlı, filtreli), listelerin ve
  kanbanların dişli menüsünden "Bilgi Bankası makalesine ekle"; /Alt sayfalar, /Makale bağlantısı
- Metin üzerinde yorum: seçili metne yorum dizisi, yanıt, çözüldü / yeniden aç, yorumlar paneli
- Kayıtlardan bilgi bankası: her formun dişli menüsünde arama, önizleme, kayda bağlama, mesaj olarak ekleme;
  makalede bağlı kayıtlar
    """,
    'author': 'Atlas',
    'depends': ['mail', 'html_editor'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_bilgi_data.xml',
        'data/atlas_bilgi_sablonlar.xml',
        'views/atlas_bilgi_views.xml',
        'views/atlas_bilgi_paylas_templates.xml',
        'wizard/atlas_bilgi_wizard_views.xml',
        'views/atlas_bilgi_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_bilgi/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
