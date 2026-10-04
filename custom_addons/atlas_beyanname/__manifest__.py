{
    'name': 'Atlas Beyannameler (KDV1, KDV2, Ba-Bs)',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'KDV1 ve KDV2 beyannamesi, Form Ba / Form Bs: dönem hesabı, PDF, Excel ve e-Beyanname XML',
    'description': """
Beyannameler
============
- KDV1: oranlara göre teslim ve hizmetler, kısmi tevkifat, istisnalar, ihraç kayıtlı teslimler,
  indirilecek KDV, önceki dönemden devreden, ödenecek / sonraki döneme devreden
- KDV2: sorumlu sıfatıyla (alış tevkifatı) beyan edilen KDV
- Form Ba / Bs: cari bazında belge sayısı ve KDV hariç tutar (bildirim sınırı ayarlanabilir)
- Hesap kontrolü: beyan tutarları 191 / 391 / 360 hesap hareketleriyle karşılaştırılır
- Çıktılar: PDF, Excel, e-Beyanname XML (Beyanname Düzenleme Programına aktarılarak kontrol edilmelidir)
    """,
    'author': 'Atlas',
    'depends': ['atlas_muhasebe_base', 'atlas_fis', 'atlas_rapor', 'l10n_tr'],
    'data': [
        'security/ir.access.csv',
        'data/atlas_beyanname_data.xml',
        'report/atlas_beyanname_report.xml',
        'views/atlas_beyanname_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
