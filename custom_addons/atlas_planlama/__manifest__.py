{
    'name': 'Atlas Planlama',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Planning',
    'summary': 'Vardiya planlama: roller, vardiya şablonları, haftalık plan, yayınlama, izin/çakışma kontrolü, iş merkezi doluluğu',
    'description': """
Vardiya ve kapasite planlama
============================
- Roller (montajcı, kaynakçı, forklift operatörü...) ve vardiya şablonları (saat, süre, mola, iş merkezi)
- Haftalık plan ekranı: çalışan × gün, şablondan tek tıkla vardiya, sürükle-bırak ile taşıma
- Çakışma ve izin uyarısı (aynı çalışana üst üste vardiya, onaylı izin günü)
- Taslak / yayınlandı: yayınlanan vardiyalar çalışana bildirilir, çalışanlar yalnızca yayınlananları görür
- Önceki haftayı kopyalama, vardiyayı günlük / haftalık tekrarlama
- İş merkezi doluluğu: vardiya kapasitesi ile planlanan iş emri süreleri
    """,
    'author': 'Atlas',
    'depends': ['hr', 'mrp', 'mail'],
    'data': [
        'security/atlas_planlama_security.xml',
        'security/ir.access.csv',
        'data/atlas_planlama_data.xml',
        'wizard/atlas_planlama_tekrar_views.xml',
        'views/atlas_planlama_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'atlas_planlama/static/src/planlama/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
