{
    'name': 'Atlas Yapay Zekâ',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Yapay zekâ çekirdeği: Anthropic Claude bağlantısı, belge okuma (OCR) kuyruğu, AI sunucu eylemleri',
    'description': """
Atlas Yapay Zekâ (Enterprise "AI" modüllerinin eşleniği)
=========================================================
- Sağlayıcı: Anthropic Claude (API anahtarı Ayarlar > Yapay Zekâ); anahtar yokken sistem normal çalışır
- Belge okuma (OCR): PDF / görselden yapılandırılmış veri — köprü modülleri fatura, masraf, CV, kartvizit ve
  belge sınıflandırma için kullanır (atlas_ai_muhasebe, atlas_ai_masraf, atlas_ai_ise_alim, atlas_ai_crm, atlas_ai_belgeler)
- İstekler kuyruğa alınır ve zamanlanmış görevde işlenir; her istek günlüğe yazılır (süre, token, hata)
- AI sunucu eylemi: otomasyon kurallarında bir alanı yapay zekâyla doldurma (metin, seçim, ilişki, sayı, etiket)
- AI önerileri kayıtta "AI ile dolduruldu" olarak işaretlenir; kullanıcı onaylar
    """,
    'author': 'Atlas',
    'depends': ['mail', 'base_setup'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.access.csv',
        'data/atlas_ai_data.xml',
        'views/atlas_ai_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
