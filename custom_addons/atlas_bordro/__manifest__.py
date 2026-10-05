{
    'name': 'Atlas Bordro',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Türkiye bordrosu: SGK, kümülatif gelir vergisi, asgari ücret istisnası, damga vergisi, net/brüt, muhasebe fişi, pusula, kıdem/ihbar',
    'description': """
Bordro (Türkiye)
================
- Yıl parametreleri: asgari ücret, SGK tavanı, prim oranları, 5 puan teşvik, SGDP, damga vergisi, gelir vergisi dilimleri,
  yemek istisnası, engelli indirimleri, kıdem tavanı (yıl içi değişiklikler için ay bazlı; kontrol edilmeden kullanılmaz)
- Dönem bordrosu: sözleşmeli çalışanlar, prim günü (giriş/çıkış, ücretsiz izinler ve SGK eksik gün nedeni),
  ek ödeme (fazla mesai saatle, prim, yemek istisnalı, yol…) ve kesintiler (avans, icra, sendika, BES)
- Hesap: SGK tavan/taban, işçi/işveren payları, kümülatif GV ve dilim, asgari ücret GV/DV istisnası, engelli indirimi,
  emekli (SGDP), net anlaşmada brüt ücretin otomatik bulunması
- Onayda muhasebe fişi (bölüm gider hesabı / 335 / 360 / 361 / 196), ücret pusulası PDF, banka ödeme listesi,
  SGK–MUHSGK dökümü (Excel), kıdem ve ihbar tazminatı hesaplayıcı
    """,
    'author': 'Atlas',
    'depends': ['hr', 'hr_holidays', 'hr_work_entry', 'account'],
    'data': [
        'security/atlas_bordro_security.xml',
        'security/ir.access.csv',
        'data/atlas_bordro_data.xml',
        'report/atlas_bordro_report.xml',
        'views/atlas_bordro_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
