{
    'name': 'Atlas WhatsApp',
    'version': '20.0.1.0.0',
    'category': 'Marketing/WhatsApp',
    'summary': 'WhatsApp Business Cloud API: onaylı şablonlarla bildirim, 24 saatlik oturumda serbest yanıt, gelen mesajlar, durum takibi',
    'description': """
WhatsApp (Meta Cloud API)
=========================
- Hesap: Phone Number ID, WABA ID, erişim anahtarı; bağlantı testi; şablonları Meta'dan içe aktarma
- Şablon değişkenleri kayıt alanlarına eşlenir ({{1}} → partner_id.name, {{2}} → amount_total …), gönderim öncesi önizleme
- Kişi, satış siparişi ve faturadan "WhatsApp Gönder"; 24 saatlik müşteri oturumunda serbest metin
- Webhook: imza doğrulaması (X-Hub-Signature-256), gönderildi/iletildi/okundu/hata durumları, gelen mesajlar
  (kişi telefonla eşleşir, yoksa oluşturulur), ilgili kaydın yazışmasına not ve sorumluya aktivite
    """,
    'author': 'Atlas',
    'depends': ['mail', 'sale_management', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/atlas_whatsapp_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
