{
    'name': 'Atlas e-Belge Hazırlık',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'e-Fatura / e-Arşiv ayrımı, senaryo ve fatura tipi, tipe göre seri seçimi, ETTN (entegratör gönderimine hazırlık)',
    'description': """
e-Belge kuralları (MYSOFT gönderiminden önceki katman)
======================================================
- Cari: e-Fatura mükellefi, posta kutusu etiketi (GB/PK), son kontrol tarihi
- Fatura: e-Belge tipi (e-Fatura / e-Arşiv / kâğıt), senaryo (TEMELFATURA, TICARIFATURA, IHRACAT, EARSIVFATURA)
  ve fatura tipi (SATIS, IADE, TEVKIFAT, ISTISNA, IHRACKAYITLI) otomatik belirlenir, elle değiştirilebilir
- Seri: her seri bir e-Belge tipine bağlanabilir; fatura tipine uygun seri otomatik seçilir
- Onayda ETTN (UUID) üretilir; e-Fatura için alıcı VKN/TCKN ve etiket kontrolü
    """,
    'author': 'Atlas',
    'depends': ['atlas_fis', 'atlas_cari', 'atlas_muhasebe_base'],
    'data': [
        'data/atlas_ebelge_data.xml',
        'views/atlas_ebelge_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
