import io
from datetime import date
from reportlab.pdfgen import canvas
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
ICP = env['ir.config_parameter'].sudo()
Istek = env['atlas.ai.istek']


def pdf(metin='FATURA'):
    t = io.BytesIO()
    c = canvas.Canvas(t)
    c.drawString(100, 750, metin)
    c.save()
    return t.getvalue()


class Yanit:
    def __init__(self, durum, veri):
        self.status_code, self._veri, self.text = durum, veri, str(veri)

    def json(self):
        return self._veri


class SahteAi:
    """Araç adına göre hazır yanıt döndürür; istekleri kaydeder."""
    def __init__(self, yanitlar, durum=200):
        self.yanitlar, self.durum, self.istekler = yanitlar, durum, []

    def post(self, url, json=None, timeout=None, headers=None):
        self.istekler.append((url, json, headers))
        if self.durum != 200:
            return Yanit(self.durum, {'error': {'message': 'invalid x-api-key'}})
        arac = (json.get('tool_choice') or {}).get('name')
        return Yanit(200, {'content': [{'type': 'tool_use', 'id': 'toolu_1', 'name': arac, 'input': self.yanitlar[arac]}],
                           'usage': {'input_tokens': 1500, 'output_tokens': 300}})


def isle(sahte, istekler=None):
    istekler = istekler or Istek.search([('durum', '=', 'bekliyor')])
    istekler.with_context(atlas_ai_oturum=sahte)._isle()
    return istekler


# --- Kapalıyken
fat = env['account.move'].create({'move_type': 'in_invoice'})
ek = env['ir.attachment'].create({'name': 'tedarikci_fatura.pdf', 'raw': pdf(), 'res_model': 'account.move', 'res_id': fat.id})
fat.message_main_attachment_id = ek
try:
    with env.cr.savepoint():
        fat.action_atlas_ai_oku(); kapali = False
except UserError:
    kapali = True
ok(kapali and not env['atlas.ai.ayar'].hazir(), "yapay zekâ kapalıyken okuma istenemez (sistem anahtarsız çalışır)")

env['atlas.ai.ayar'].create({'etkin': True, 'anahtar': 'sk-test', 'model': 'claude-sonnet-5', 'otomatik_oku': True}).action_kaydet()
ok(env['atlas.ai.ayar'].hazir(), "ayarlar kaydedildi")

# --- Fatura okuma
YANIT = {
    'fatura': {'satici': {'ad': 'AI Tedarik A.Ş.', 'vkn': '1234567890', 'vergi_dairesi': 'Kadıköy'}, 'alici': {'ad': env.company.name},
               'fatura_no': 'ATD2025000000077', 'fatura_tarihi': '2025-09-15', 'vade_tarihi': '2025-10-15', 'para_birimi': 'TRY',
               'satirlar': [{'aciklama': 'Kablo 3x2.5', 'miktar': 100, 'birim_fiyat': 25.5, 'kdv_orani': 20},
                            {'aciklama': 'Nakliye', 'miktar': 1, 'birim_fiyat': 450, 'kdv_orani': 20}],
               'ara_toplam': 3000, 'kdv_toplam': 600, 'genel_toplam': 3600, 'guven': 93},
    'masraf': {'aciklama': 'Taksi - Kadıköy', 'tarih': '2025-09-20', 'toplam': 245.5, 'para_birimi': 'TRY', 'satici': 'İstanbul Taksi',
               'kategori': None, 'guven': 88},
    'aday': {'ad_soyad': 'Ayşe Demir', 'eposta': 'ayse@ornek.com', 'telefon': '+90 532 000 00 00', 'deneyim_yili': 6,
             'son_pozisyon': 'Muhasebe Uzmanı', 'beceriler': ['Netsis', 'IFRS', 'Excel'], 'ozet': 'Altı yıllık muhasebe deneyimi.', 'guven': 90},
    'kartvizit': {'ad_soyad': 'Mehmet Kaya', 'unvan': 'Satın Alma Müdürü', 'sirket': 'Kaya Elektrik Ltd.', 'eposta': 'mehmet@kaya.com.tr',
                  'telefon': '+90 212 555 00 00', 'web': 'kaya.com.tr', 'guven': 97},
    'siniflandir': {'klasor': None, 'etiketler': ['Sözleşme'], 'ad': 'Kira Sözleşmesi 2025 Merkez Ofis', 'ozet': 'Merkez ofis kira sözleşmesi.',
                    'cari_vkn': '1234567890', 'guven': 85},
    'deger': {'deger': 'Satın Alma Müdürü'},
}
sahte = SahteAi(YANIT)
fat.action_atlas_ai_oku()
ok(fat.atlas_ai_durum == 'kuyrukta' and Istek.search_count([('model', '=', 'account.move'), ('res_id', '=', fat.id), ('durum', '=', 'bekliyor')]) == 1,
   "fatura okuma kuyruğa alındı")
istek = isle(sahte, Istek.search([('model', '=', 'account.move'), ('res_id', '=', fat.id)]))
govde = sahte.istekler[-1][1]
ok(govde['tool_choice'] == {'type': 'tool', 'name': 'fatura'} and govde['messages'][0]['content'][0]['type'] == 'document'
   and govde['messages'][0]['content'][0]['source']['media_type'] == 'application/pdf' and sahte.istekler[-1][2]['x-api-key'] == 'sk-test',
   "istek: PDF 'document' bloğu, zorunlu araç, API anahtarı")
ok(istek.durum == 'tamam' and istek.giris_token == 1500 and istek.cikis_token == 300, "istek günlüğü: tamam, token kullanımı")
ok(fat.partner_id.name == 'AI Tedarik A.Ş.' and fat.partner_id.vat in ('1234567890', 'TR1234567890') and fat.ref == 'ATD2025000000077'
   and fat.invoice_date == date(2025, 9, 15) and fat.invoice_date_due == date(2025, 10, 15), "cari (VKN ile yeni), fatura no, tarih, vade")
ok(len(fat.invoice_line_ids) == 2 and all(l.tax_ids.amount == 20 and l.tax_ids.type_tax_use == 'purchase' for l in fat.invoice_line_ids)
   and abs(fat.amount_total - 3600) < 0.01, f"2 satır, %20 alış KDV'si, toplam {fat.amount_total}")
ok(fat.atlas_ai_durum == 'okundu' and fat.atlas_ai_guven == 93 and fat.state == 'draft', "fatura taslak kaldı, 'AI ile dolduruldu' güven %93")
# Aynı tedarikçinin ikinci faturası: cari VKN ile bulunur, yeni cari açılmaz
fat2 = env['account.move'].create({'move_type': 'in_invoice'})
fat2.message_main_attachment_id = env['ir.attachment'].create({'name': 'f2.pdf', 'raw': pdf(), 'res_model': 'account.move', 'res_id': fat2.id})
fat2.action_atlas_ai_oku(); isle(sahte)
ok(fat2.partner_id == fat.partner_id and env['res.partner'].search_count([('name', '=', 'AI Tedarik A.Ş.')]) == 1, "ikinci faturada cari VKN ile bulundu")

# --- Hata yolu
fat3 = env['account.move'].create({'move_type': 'in_invoice'})
fat3.message_main_attachment_id = env['ir.attachment'].create({'name': 'f3.pdf', 'raw': pdf(), 'res_model': 'account.move', 'res_id': fat3.id})
fat3.action_atlas_ai_oku()
hatali = isle(SahteAi(YANIT, durum=401))
ok(hatali.durum == 'hata' and 'invalid x-api-key' in hatali.hata and fat3.atlas_ai_durum == 'hata' and 'HTTP 401' in fat3.atlas_ai_hata_mesaji,
   "API hatası: istek ve kayıt 'hata', mesaj görünür")
fat4 = env['account.move'].create({'move_type': 'in_invoice'})
fat4.action_atlas_ai_oku()
ok(isle(sahte).durum == 'hata' and 'eki yok' in fat4.atlas_ai_hata_mesaji, "eki olmayan kayıtta anlaşılır hata")

# --- Masraf
kategori = env['product.product'].search([('can_be_expensed', '=', True)], limit=1)
YANIT['masraf']['kategori'] = kategori.display_name
calisan = env.user.employee_id or env['hr.employee'].create({'name': 'AI Çalışan', 'user_id': env.user.id})
masraf = env['hr.expense'].create({'name': 'fis.jpg', 'employee_id': calisan.id})
env['ir.attachment'].create({'name': 'fis.png', 'raw': b'\x89PNG\r\n\x1a\nsahte', 'mimetype': 'image/png', 'res_model': 'hr.expense', 'res_id': masraf.id})
masraf.action_atlas_ai_oku(); isle(sahte)
ok(masraf.name == 'Taksi - Kadıköy' and masraf.total_amount_currency == 245.5 and masraf.date == date(2025, 9, 20)
   and masraf.product_id == kategori and sahte.istekler[-1][1]['messages'][0]['content'][0]['type'] == 'image',
   "masraf fişi (görsel): açıklama, tutar, tarih, kategori")

# --- Aday (CV)
aday = env['hr.applicant'].create({'partner_name': 'cv'})
env['ir.attachment'].create({'name': 'cv.pdf', 'raw': pdf('CV'), 'res_model': 'hr.applicant', 'res_id': aday.id})
aday.action_atlas_ai_oku(); isle(sahte)
ok(aday.partner_name == 'Ayşe Demir' and aday.email_from == 'ayse@ornek.com' and set(aday.categ_ids.mapped('name')) >= {'Netsis', 'IFRS'}
   and 'Muhasebe Uzmanı' in (aday.applicant_notes or ''), "CV: ad, e-posta, beceri etiketleri, not")

# --- Kartvizit
firsat = env['crm.lead'].create({'name': 'Yeni'})
env['ir.attachment'].create({'name': 'kart.jpg', 'raw': b'\xff\xd8\xffsahte', 'mimetype': 'image/jpeg', 'res_model': 'crm.lead', 'res_id': firsat.id})
firsat.action_atlas_ai_oku(); isle(sahte)
ok(firsat.contact_name == 'Mehmet Kaya' and firsat.partner_name == 'Kaya Elektrik Ltd.' and firsat.email_from == 'mehmet@kaya.com.tr'
   and firsat.name == 'Kaya Elektrik Ltd.', "kartvizit: kişi, şirket, e-posta, fırsat adı")

# --- Belge sınıflandırma: Gelen Kutusu'na düşen belge otomatik
hedef = env.ref('atlas_belgeler.klasor_genel')
YANIT['siniflandir']['klasor'] = hedef.complete_name
belge = env['atlas.belge'].create({'name': 'scan001.pdf', 'dosya_adi': 'scan001.pdf', 'dosya': __import__('base64').b64encode(pdf()).decode(),
                                   'klasor_id': env.ref('atlas_ai_belgeler.klasor_gelen_kutusu').id})
ok(belge.atlas_ai_durum == 'kuyrukta', "Gelen Kutusu'na düşen belge otomatik sınıflandırma kuyruğunda")
isle(sahte)
ok(belge.klasor_id == hedef and belge.name == 'Kira Sözleşmesi 2025 Merkez Ofis.pdf' and 'Sözleşme' in belge.etiket_ids.mapped('name')
   and belge.partner_id == fat.partner_id and belge.aciklama, "belge: klasör, ad (uzantı korunur), etiket, cari (VKN), özet")

# --- Belgeler köprüsüyle: belgeden fatura → otomatik okuma kuyruğu
b2 = env['atlas.belge'].create({'name': 'gelen.pdf', 'dosya_adi': 'gelen.pdf', 'dosya': __import__('base64').b64encode(pdf()).decode(),
                                'klasor_id': env.ref('atlas_belgeler.klasor_gelen_fatura').id})
yeni = env['account.move'].browse(b2.action_belge_tedarikci_faturasi()['res_id'])
ok(yeni.atlas_ai_durum == 'kuyrukta', "Belgeler'den oluşturulan fatura otomatik okumaya alındı")
isle(sahte)
ok(yeni.partner_id == fat.partner_id and len(yeni.invoice_line_ids) == 2, "belge → fatura → AI ile dolduruldu")

# --- AI sunucu eylemi (otomasyon kurallarında kullanılabilir)
kisi = env['res.partner'].create({'name': 'Eylem Kişi'})
eylem = env['ir.actions.server'].create({'name': 'Unvan tahmin', 'model_id': env.ref('base.model_res_partner').id, 'state': 'atlas_ai',
                                         'atlas_ai_istem': '{name} kişisinin unvanını yaz',
                                         'atlas_ai_alan_id': env['ir.model.fields']._get('res.partner', 'function').id})
eylem.with_context(active_model='res.partner', active_ids=kisi.ids, active_id=kisi.id).run()
ist = Istek.search([('gorev', '=', 'eylem'), ('res_id', '=', kisi.id)])
isle(sahte, ist)
ok(ist.durum == 'tamam' and kisi.function == 'Satın Alma Müdürü' and 'Eylem Kişi kişisinin unvanını yaz' in str(sahte.istekler[-1][1]['messages']),
   "AI sunucu eylemi: talimattaki {alan} değiştirildi, alan dolduruldu")
env.cr.rollback(); print("(geri alındı)")
