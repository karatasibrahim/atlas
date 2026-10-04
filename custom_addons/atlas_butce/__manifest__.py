{
    'name': 'Atlas Bütçe',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Yıllık bütçe: hesap kodu bazında aylık plan, gerçekleşen, sapma, aşım kontrolü, bütçe-gerçekleşen raporu',
    'description': """
Bütçe yönetimi
==============
- Yıllık bütçe; kalemler hesap kodu önekine göre (ör. 770, 7701, 600) ve isteğe bağlı analitik hesap (proje / departman)
- 12 aylık plan tutarları; geçen yılın gerçekleşeninden artış oranıyla doldurma
- Gerçekleşen (kapanış fişleri hariç), fark ve gerçekleşme oranı
- Bütçe aşım kontrolü: yok / uyarı / engelle (gider kalemleri, fatura ve fiş onayında)
- Muhasebe raporlarına "Bütçe - Gerçekleşen" raporu (ekran, PDF, Excel)
    """,
    'author': 'Atlas',
    'depends': ['atlas_rapor', 'atlas_fis', 'analytic'],
    'data': [
        'security/ir.access.csv',
        'views/atlas_butce_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
