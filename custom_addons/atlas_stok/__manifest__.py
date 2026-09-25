{
    'name': 'Atlas Stok / Üretim Muhasebesi',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'TDHP stok hesapları, maliyet ve envanter yöntemi, irsaliye seri numarası, dönem sonu stok kapanışı',
    'description': """
Stok ve üretimin Türkiye muhasebesine uyarlanması
=================================================
- TDHP stok kategorileri: 150 İlk Madde, 151 Yarı Mamul, 152 Mamul, 153 Ticari Mal, 157 Diğer Stok, Hizmet
- Stok değişim hesapları: 150 → 710, 151/152 → 620, 153 → 621, 157 → 770
- Maliyet yöntemi (ağırlıklı ortalama / FIFO / standart) ve envanter yöntemi (aralıklı / sürekli) ayarlardan seçilir;
  envanter yöntemi değişince kategori alış hesapları uyarlanır
- Lot/seri, çoklu lokasyon, ölçü birimi ve iş emri özelliklerinin açılması
- Sevk irsaliyesi numarası seri/sayaç tablosundan (GİB e-İrsaliye biçimi), araç plaka ve şoför bilgileri
- Dönem sonu stok kapanışı (aralıklı envanter), üretim giderlerinin 7/A yansıtmasıyla birlikte
    """,
    'author': 'Atlas',
    'depends': ['atlas_donem', 'stock_account', 'mrp_account', 'purchase_stock', 'sale_stock'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_stok_data.xml',
        'views/res_config_settings_views.xml',
        'views/stock_picking_views.xml',
        'report/report_deliveryslip.xml',
        'wizard/atlas_stok_kapanis_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_atlas_stok_post_init',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
