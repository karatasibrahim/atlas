{
    'name': 'Atlas Menü',
    'version': '20.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': 'Açılır-kapanır (akordeon) sol menü: uygulamalar başlık, bölümler ve işlemler altında; menü araması, daraltma',
    'description': """
Atlas kurumsal arayüz
=====================
- Solda sabit, açılır-kapanır menü: Uygulama ▸ Bölüm ▸ İşlem (Odoo menü ağacının tamamı)
- Aktif uygulama ve sayfa vurgulanır; açık bölümler tarayıcıda hatırlanır
- Menü araması (tüm uygulamalarda), ikon moduna daraltma
- Üst bardaki uygulama ve bölüm menüleri gizlenir (sol menüde var); mobilde Odoo'nun kendi menüsü kullanılır
- Kurumsal renk teması
    """,
    'author': 'Atlas',
    'depends': ['web'],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'atlas_menu/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'atlas_menu/static/src/scss/menu_accordion.scss',
            'atlas_menu/static/src/js/menu_accordion.js',
            'atlas_menu/static/src/xml/menu_accordion.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
