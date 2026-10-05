{
    'name': 'Atlas Randevu',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Calendar',
    'summary': 'Çevrim içi randevu: haftalık müsaitlik, personel / kaynak (masa, oda) ataması, kapasite, sorular, onay, hatırlatma, paylaşım bağlantısı',
    'description': """
Atlas Randevu (Enterprise Appointments eşleniği)
================================================
- Randevu türleri: süre, saat dilimi, haftalık müsaitlik dilimleri ya da belirli tarih aralığı, en erken / en geç planlama,
  iptal süresi, otomatik ya da elle onay, hatırlatmalar, konum veya görüntülü görüşme
- Personel bazlı (kullanıcı takvimi ve çalışma saatleriyle çakışma denetimi; otomatik ya da müşteri seçimli atama)
  veya kaynak bazlı (masa, oda, cihaz; kapasite ve kişi sayısı)
- Müşteriye sorular (metin, telefon, seçim, çoklu seçim); yanıtlar randevuda saklanır
- Herkese açık randevu sayfası: takvim, uygun saatler, bilgi formu, onay sayfası, .ics, iptal
- Davet bağlantıları: belirli türler / personel / kaynaklarla sınırlı, kısa kod
- Randevu durumları: talep, onaylı, geldi, gelmedi, iptal; CRM kuruluysa fırsat oluşturma
- Raporlama: tür, personel, durum bazında pivot / grafik
    """,
    'author': 'Atlas',
    'depends': ['calendar', 'resource', 'mail'],
    'data': [
        'data/atlas_randevu_data.xml',
        'security/ir.access.csv',
        'views/atlas_randevu_views.xml',
        'views/calendar_event_views.xml',
        'views/atlas_randevu_templates.xml',
        'views/atlas_randevu_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
