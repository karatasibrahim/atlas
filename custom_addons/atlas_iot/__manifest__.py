{
    'name': 'Atlas IoT',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/IoT',
    'summary': 'Cihaz bağlantıları: USB terazi (tarayıcıdan), ağ ZPL etiket yazıcı, makine sayacı ve sensörler (HTTP), OEE ile entegre',
    'description': """
IoT (Nesnelerin İnterneti)
==========================
- Cihaz kaydı: terazi, etiket yazıcı, makine sayacı, sensör; son değer ve çevrimiçi durumu
- Terazi: kutu gerektirmez — tarayıcı (Web Serial) ile USB/seri teraziden kararlı ağırlık okunur; "atlas_terazi" alan widget'ı
- Tartım istasyonu: ürün, dara/net, lot, transfer; ZPL etiket basma
- Ağ etiket yazıcısı (Zebra vb., 9100 portu): ZPL şablonu; ürünlerden toplu etiket
- Makine sayacı: sayım çalışan iş emrine eklenir (hatalı adet dahil), "durdu" iş merkezini duruşa alır → OEE raporuna yansır
- Sensör: ölçüm kaydı, alt/üst sınır alarmı ve sorumluya aktivite
    """,
    'author': 'Atlas',
    'depends': ['stock', 'mrp', 'atlas_shopfloor'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_iot_data.xml',
        'views/atlas_iot_views.xml',
    ],
    'assets': {
        'web.assets_backend': ['atlas_iot/static/src/**/*'],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
