{
    'name': 'Atlas Yardım Masası',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Destek talepleri: ekipler, e-postadan talep, otomatik atama, SLA, müşteri portalı, memnuniyet anketi',
    'description': """
Yardım masası
=============
- Ekipler: üyeler, e-posta adresi (gelen e-posta talep açar), otomatik atama (sırayla / en az yüklü)
- Talepler: tip, öncelik, etiket, aşama, sorumlu, cari; sohbet geçmişi ve aktiviteler
- SLA politikaları: ekip / tip / öncelik koşulu, hedef aşama, çalışma takvimine göre süre; ihlal takibi
- Müşteri portalı: taleplerim, talep detayı ve mesajlaşma, yeni talep formu
- Kapanışta memnuniyet anketi (1-5 puan), talep ve SLA analizleri
- Hazır cevaplar: Odoo'nun "::" kısayolu (mail.canned.response)
    """,
    'author': 'Atlas',
    'depends': ['mail', 'portal', 'rating', 'resource'],
    'data': [
        'security/atlas_destek_security.xml',
        'security/ir.access.csv',
        'data/atlas_destek_data.xml',
        'views/atlas_destek_views.xml',
        'views/atlas_destek_portal.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
