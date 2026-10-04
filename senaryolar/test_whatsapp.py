import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.addons.atlas_whatsapp.models import atlas_whatsapp as wa
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
ok(wa.telefon_normalize('0532 111 22 33') == '905321112233' and wa.telefon_normalize('+49 151 2345678') == '491512345678'
   and wa.telefon_normalize('5321112233') == '905321112233' and wa.telefon_normalize('0090 532 111 22 33') == '905321112233', "telefon normalizasyonu")
cagrilar = []
def yanit(veri, kod=200):
    r = MagicMock(); r.status_code = kod; r.json.return_value = veri; r.text = json.dumps(veri); return r
def sahte(yontem, url, headers=None, json=None, params=None, timeout=None):
    cagrilar.append((yontem, url, json, headers))
    if url.endswith('/message_templates'):
        return yanit({'data': [{'name': 'siparis_hazir', 'language': 'tr', 'status': 'APPROVED', 'category': 'UTILITY', 'id': '991',
                                'components': [{'type': 'BODY', 'text': 'Sayın {{1}}, {{2}} numaralı siparişiniz ({{3}}) hazır.'}]},
                               {'name': 'kampanya', 'language': 'tr', 'status': 'PENDING', 'category': 'MARKETING', 'components': [{'type': 'BODY', 'text': 'İndirim!'}]}]})
    if url.endswith('/messages'):
        if json['to'] == '900000000000':
            return yanit({'error': {'code': 131026, 'message': 'Message undeliverable'}}, 400)
        return yanit({'messages': [{'id': f'wamid.{len(cagrilar)}'}]})
    return yanit({'display_phone_number': '+90 212 000 00 00', 'verified_name': 'Atlas Test', 'quality_rating': 'GREEN'})
with patch.object(wa.requests, 'request', side_effect=sahte):
    h = env['atlas.whatsapp.hesap'].create({'name': 'WA Test', 'telefon_no_id': '1111', 'waba_id': '2222', 'erisim_anahtari': 'GIZLI', 'uygulama_sirri': 'sir123'})
    h.action_baglanti_test()
    ok(h.gorunen_numara == '+90 212 000 00 00' and cagrilar[-1][3]['Authorization'] == 'Bearer GIZLI', "bağlantı testi: numara alındı, anahtar başlıkta")
    ok(h.webhook_url.endswith(f'/whatsapp/webhook/{h.id}') and len(h.dogrulama_anahtari) > 20, "webhook adresi ve doğrulama anahtarı")
    h.action_sablon_senkron(); h.action_sablon_senkron()
    s = h.sablon_ids.filtered(lambda x: x.wa_adi == 'siparis_hazir')
    ok(len(h.sablon_ids) == 2 and s.durum == 'onaylandi' and '{{3}}' in s.govde, "şablonlar içe aktarıldı (tekrar senkron mükerrer oluşturmaz)")
    s.write({'model_id': env.ref('sale.model_sale_order').id, 'degisken_ids': [Command.create({'sira': 1, 'alan_yolu': 'partner_id.name'}),
            Command.create({'sira': 2, 'alan_yolu': 'name'}), Command.create({'sira': 3, 'alan_yolu': 'amount_total'})]})
    mus = env['res.partner'].create({'name': 'WA Müşteri', 'phone': '0532 111 22 33', 'email': 'wa@musteri.local'})
    so = env['sale.order'].create({'partner_id': mus.id, 'user_id': env.ref('base.user_admin').id, 'order_line': [Command.create({'product_id': env['product.product'].create({'name': 'WA Ürün', 'list_price': 100}).id, 'product_uom_qty': 2})]})
    eylem = env['atlas.whatsapp.gonder']._ac(so)
    w = env['atlas.whatsapp.gonder'].with_context(**eylem['context']).create({'hesap_id': h.id, 'sablon_id': s.id})
    ok(w.telefon == '905321112233' and w.partner_id == mus and not w.oturum_acik, "sipariştan gönderim: telefon ve kişi otomatik")
    ok(w.onizleme.startswith('Sayın WA Müşteri, ' + so.name) and 'hazır' in w.onizleme, f"önizleme: {w.onizleme}")
    w.action_gonder()
    istek = cagrilar[-1][2]
    ok(istek['type'] == 'template' and istek['template']['name'] == 'siparis_hazir' and istek['to'] == '905321112233'
       and istek['template']['components'][0]['parameters'][1]['text'] == so.name, "şablon isteği doğru parametrelerle gönderildi")
    m = env['atlas.whatsapp.mesaj'].search([('res_model', '=', 'sale.order'), ('res_id', '=', so.id)])
    ok(m.durum == 'gonderildi' and m.wa_mesaj_id and m.yon == 'giden', "mesaj kaydı: gönderildi")
    ok(any('WhatsApp' in (x.body or '') for x in so.message_ids), "sipariş yazışmasına not düşüldü")
    w2 = env['atlas.whatsapp.gonder'].with_context(**eylem['context']).create({'hesap_id': h.id, 'tur': 'metin', 'metin': 'Merhaba'})
    try:
        with env.cr.savepoint(): w2.action_gonder(); serbest = True
    except UserError: serbest = False
    ok(not serbest, "24 saatlik oturum yokken serbest metin gönderilemez")
    def webhook(veri):
        govde = json.dumps(veri).encode()
        imza = 'sha256=' + hmac.new(b'sir123', govde, hashlib.sha256).hexdigest()
        return h._imza_dogrula(govde, imza), h._imza_dogrula(govde, 'sha256=yanlis')
    deg = {'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '1111'}, 'statuses': [{'id': m.wa_mesaj_id, 'status': 'read'}]}}]}]}
    dogru, yanlis = webhook(deg)
    ok(dogru and not yanlis, "webhook imzası doğrulanıyor")
    h._webhook_isle(deg)
    h._webhook_isle({'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '1111'}, 'statuses': [{'id': m.wa_mesaj_id, 'status': 'delivered'}]}}]}]})
    ok(m.durum == 'okundu', "durum okundu; geç gelen 'iletildi' geri almadı")
    gelen = {'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '1111'}, 'contacts': [{'wa_id': '905321112233', 'profile': {'name': 'Ali'}}],
             'messages': [{'id': 'wamid.gelen1', 'from': '905321112233', 'type': 'text', 'text': {'body': 'Teşekkürler, ne zaman teslim?'}}]}}]}]}
    h._webhook_isle(gelen); h._webhook_isle(gelen)
    g = env['atlas.whatsapp.mesaj'].search([('wa_mesaj_id', '=', 'wamid.gelen1')])
    ok(len(g) == 1 and g.partner_id == mus and g.res_id == so.id and g.durum == 'alindi', "gelen mesaj kişiyle ve siparişle eşleşti (tekrar webhook yok sayıldı)")
    ok(mus.atlas_whatsapp_son_gelen and so.activity_ids, "oturum açıldı, sorumluya aktivite")
    w3 = env['atlas.whatsapp.gonder'].with_context(**g.action_yanitla()['context']).create({'tur': 'metin', 'metin': 'Yarın teslim edilecek.'})
    ok(w3.oturum_acik, "yanıt sihirbazında oturum açık")
    w3.action_gonder()
    ok(cagrilar[-1][2]['type'] == 'text' and cagrilar[-1][2]['text']['body'] == 'Yarın teslim edilecek.', "serbest metin yanıtı gönderildi")
    yabanci = {'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '1111'}, 'contacts': [{'wa_id': '905559998877', 'profile': {'name': 'Yeni Kişi'}}],
               'messages': [{'id': 'wamid.gelen2', 'from': '905559998877', 'type': 'image'}]}}]}]}
    h._webhook_isle(yabanci)
    y = env['atlas.whatsapp.mesaj'].search([('wa_mesaj_id', '=', 'wamid.gelen2')])
    ok(y.partner_id.name == 'Yeni Kişi' and y.govde == '[image]', "tanınmayan numaradan gelen mesaj: kişi oluşturuldu")
    hatali = env['res.partner'].create({'name': 'WA Hatalı', 'phone': '+90 000 000 00 00'})
    so2 = env['sale.order'].create({'partner_id': hatali.id})
    w4 = env['atlas.whatsapp.gonder'].with_context(**env['atlas.whatsapp.gonder']._ac(so2)['context']).create({'hesap_id': h.id, 'sablon_id': s.id})
    try:
        with env.cr.savepoint(): w4.action_gonder(); gitti = True
    except UserError as e: gitti = 'undeliverable' not in str(e)
    ok(not gitti, "API hatası kullanıcıya iletildi")
    h._webhook_isle({'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '1111'}, 'statuses': [{'id': m.wa_mesaj_id, 'status': 'failed', 'errors': [{'code': 131047, 'title': 'Re-engagement message'}]}]}}]}]})
    ok(m.durum == 'hata' and '131047' in m.hata, "başarısız durum bildirimi işlendi")
env.cr.rollback(); print("(geri alındı)")
