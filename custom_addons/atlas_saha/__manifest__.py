{
    'name': 'Atlas Saha Servisi',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'Saha servis görevleri: planlama (Gantt/harita), kontrol listesi, malzeme, müşteri imzası, servis raporu, otomatik faturalama',
    'description': """
Saha Servisi
============
- Saha projeleri: işçilik ürünü, tamamlanınca faturalama, imza zorunluluğu, kontrol listesi şablonu
- Görev: müşteri adresi ve yol tarifi, kontrol listesi, kullanılan malzemeler, iş raporu, müşteri imzası
- Sayaçla veya zaman çizelgesiyle süre kaydı (atlas_zaman)
- Servisi Tamamla: zorunlu kontroller ve imza denetlenir; süre + malzemeden satış siparişi, malzeme çıkışı ve fatura taslağı oluşur;
  imzalı servis raporu PDF olarak göreve eklenir, müşteriye e-postayla gönderilebilir
- Görevlerim (mobil uyumlu kanban), planlama (Gantt), harita, faturalanacak işler
    """,
    'author': 'Atlas',
    'depends': ['project', 'hr_timesheet', 'sale_management', 'stock', 'atlas_gorunum', 'atlas_zaman'],
    'data': [
        'security/ir.access.csv',
        'report/atlas_saha_report.xml',
        'data/atlas_saha_data.xml',
        'views/atlas_saha_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
