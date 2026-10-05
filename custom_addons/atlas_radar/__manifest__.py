{
    'name': 'Atlas Radar',
    'version': '20.0.1.0.0',
    'category': 'Administration',
    'summary': 'Resmî kurum ve mevzuat değişikliklerini izleme: kaynak tarama, değişiklik tespiti, sınıflandırma, ERP etki analizi, inceleme ve görev',
    'description': """
Atlas Radar — resmî kurum / mevzuat değişiklik izleme (yalnız sistem yöneticileri)
===================================================================================
- Kaynaklar: GİB, Resmî Gazete, SGK, KVKK, Ticaret Bakanlığı … HTML liste, RSS/Atom, JSON API veya tek sayfa;
  ülke / yetki alanı, kurum, öncelik, kontrol aralığı, izinli alan adları
- Güvenli tarayıcı: robots.txt'ye uyar, zaman aşımı, yeniden deneme, alan adı başına hız sınırı, User-Agent,
  SSL doğrulaması, izinli alan listesi, özel/iç IP engeli (SSRF), yönlendirmelerde yeniden doğrulama, boyut sınırı
- Tarama yalnız zamanlanmış görevde yapılır; kullanıcı isteği içinde dış siteye bağlanılmaz
- Değişiklik tespiti: normalleştirilmiş içerik SHA-256 özeti, önceki sürümle fark (diff), mükerrer tespiti
- Sınıflandırma: anahtar kelime kuralları (kategori, önem, etkilenen Atlas modülleri, geliştirme/ayar/kullanıcı aksiyonu);
  isteğe bağlı yapay zekâ önerisi (güven skoru ile, "AI önerisi" olarak işaretli; zorunlu değil)
- Etki analizi: Atlas/Odoo modülleri ve şirket bazında; modül sorumlusuna aktivite
- İnceleme akışı: yeni → inceleniyor → onaylandı / reddedildi / uygulandı; onayda proje görevi
- Yürürlük takvimi, panel (KPI, kaynak sağlığı, yaklaşan yürürlükler), günlük özet e-postası
- Silinemez denetim günlüğü; salt okunur REST API (/atlas_radar/api/v1, API anahtarı ile)
- Radar hiçbir ERP kaydını (fatura, fiş, bordro …) değiştirmez; yalnız uyarır ve görev açar
    """,
    'author': 'Atlas',
    'depends': ['mail', 'project'],
    'external_dependencies': {'python': ['requests', 'lxml']},
    'data': [
        'security/ir.access.csv',
        'data/atlas_radar_data.xml',
        'data/atlas_radar_kaynak.xml',
        'data/atlas_radar_kural.xml',
        'views/atlas_radar_views.xml',
        'views/atlas_radar_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_radar/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
