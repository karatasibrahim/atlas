{
    'name': 'Atlas Performans Değerlendirme',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Appraisals',
    'summary': 'Performans değerlendirme dönemleri, ağırlıklı yetkinlikler, öz ve yönetici değerlendirmesi, hedefler, derece',
    'description': """
Performans Değerlendirme
========================
- Şablon: ağırlıklı yetkinlik/soru listesi (1-5 puan veya yorum), hedeflerin sonuçtaki payı
- Dönem: bölüm veya çalışan seçerek başlat; her çalışana değerlendirme, ilgili kişiye aktivite
- Akış: öz değerlendirme → yönetici değerlendirmesi → görüşme → çalışan onayı → tamamlandı
- Hedefler: çalışan/yönetici tarafından izlenen ilerleme, ağırlık; dönem değerlendirmesine otomatik dahil
- Sonuç puanı (100 üzerinden) ve derece (A–E); çalışanda son derece ve sonraki değerlendirme tarihi
- Yetki: çalışan kendi, yönetici ekibinin değerlendirmesini görür; puan alanları aşamaya ve role göre kilitli
    """,
    'author': 'Atlas',
    'depends': ['hr', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_degerlendirme_data.xml',
        'views/atlas_degerlendirme_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
