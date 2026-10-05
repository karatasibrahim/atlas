from unittest.mock import MagicMock, patch
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.addons.atlas_voip.models import atlas_voip as vp
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
C = env['atlas.voip.cagri']
S = env['atlas.voip.saglayici']
S.search([]).write({'active': False})
U = env['res.users'].with_context(no_reset_password=True)
ali = U.create({'name': 'VOIP Ali', 'login': 'voip_ali', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
veli = U.create({'name': 'VOIP Veli', 'login': 'voip_veli', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
ali.with_user(ali).write({'atlas_dahili': '101'})
ok(ali.atlas_dahili == '101', "kullanıcı kendi dahilisini tanımlayabildi")
mus = env['res.partner'].create({'name': 'VOIP Müşteri A.Ş.', 'is_company': True, 'phone': '+90 (212) 555 44 33', 'user_id': veli.id})
kisi = env['res.partner'].create({'name': 'Ayşe Kaya', 'parent_id': mus.id, 'phone': '0532 777 88 99'})
ok(env['res.partner']._atlas_numara_bul('905327778899') == kisi and env['res.partner']._atlas_numara_bul('02125554433') == mus, "numaradan kişi bulma (farklı biçimler)")
s = C.with_user(ali).atlas_ara('0532 777 88 99', 'res.partner', kisi.id)
c = C.browse(s['cagri_id'])
ok(s['yontem'] == 'tel' and c.partner_id == kisi and c.yon == 'giden' and c.user_id == ali, "santral yokken tel: ile arama, kayıt açıldı")
santral = S.create({'name': 'Bulut Santral', 'yontem': 'http', 'url_sablonu': 'https://santral.test/originate?key={anahtar}&ext={dahili}&to={numara}',
                    'anahtar': 'K123', 'dis_hat_oneki': '0'})
istekler = []
def sahte(yontem, url, headers=None, json=None, timeout=None):
    istekler.append((yontem, url)); r = MagicMock(); r.status_code = 200 if 'ext=101' in url else 404; r.text = 'OK'; return r
with patch.object(vp.requests, 'request', side_effect=sahte):
    so = env['sale.order'].create({'partner_id': kisi.id}) if 'sale.order' in env else None
    s = C.with_user(ali).atlas_ara('+90 532 777 88 99', so._name if so else 'res.partner', so.id if so else kisi.id)
    ok(s['yontem'] == 'api' and istekler[-1][1] == 'https://santral.test/originate?key=K123&ext=101&to=005327778899', f"click-to-call isteği: {istekler[-1][1]}")
    giden = C.browse(s['cagri_id'])
    ok(giden.partner_id == kisi and giden.durum == 'baslatildi', "siparişten aranınca kişi bağlandı")
    try:
        with env.cr.savepoint(): C.with_user(veli).atlas_ara('05327778899'); dahilisiz = True
    except UserError: dahilisiz = False
    ok(not dahilisiz, "dahilisi olmayan kullanıcı santralden arayamaz")
    veli.atlas_dahili = '102'
    try:
        with env.cr.savepoint(): C.with_user(veli).atlas_ara('05327778899'); reddedildi = False
    except UserError: reddedildi = True
    ok(reddedildi, "santral hatası kullanıcıya iletildi")
# giden aramanın santral olayları
C._olay_isle({'event': 'ringing', 'call_id': 'A1', 'direction': 'outbound', 'from': '101', 'to': '05327778899', 'extension': '101'})
C._olay_isle({'event': 'answered', 'call_id': 'A1', 'extension': '101'})
C._olay_isle({'event': 'hangup', 'call_id': 'A1', 'duration': '95', 'recording': 'https://santral.test/kayit/A1.mp3'})
ok(giden.santral_id == 'A1' and giden.durum == 'tamamlandi' and giden.sure == 95 and giden.sure_metin == '1:35' and giden.kayit_url,
   "giden arama santral olaylarıyla eşleşti: süre ve ses kaydı")
ok(any('Giden arama' in (m.body or '') for m in kisi.message_ids), "kişinin yazışmasına özet düştü")
# gelen arama
bildirimler = []
with patch.object(type(env['res.users']), '_bus_send', lambda self, tip, yuk, **kw: bildirimler.append((self.id, tip, yuk))):
    g = C._olay_isle({'event': 'ringing', 'call_id': 'B7', 'from': '+902125554433', 'to': '02120000000', 'extension': '101'})
    ok(g.yon == 'gelen' and g.partner_id == mus and g.user_id == ali and g.durum == 'caliyor', "gelen arama: kişi ve dahili eşleşti")
    ok(bildirimler and bildirimler[-1][0] == ali.id and bildirimler[-1][1] == 'atlas_voip/gelen' and bildirimler[-1][2]['partner_ad'] == mus.name,
       "ilgili kullanıcının ekranına bildirim gönderildi")
    C._olay_isle({'event': 'hangup', 'call_id': 'B7', 'duration': '0'})
    ok(g.durum == 'cevapsiz' and mus.activity_ids.filtered(lambda a: a.user_id == ali), "cevapsız arama: geri ara aktivitesi")
    ok(any(b[1] == 'atlas_voip/cevapsiz' for b in bildirimler), "cevapsız arama bildirimi")
    bildirimler.clear()
    y = C._olay_isle({'event': 'incoming', 'call_id': 'C3', 'from': '05559998877'})
    ok(y.yon == 'gelen' and not y.partner_id and len({b[0] for b in bildirimler}) > 1, "dahilisiz/tanınmayan arama tüm iç kullanıcılara bildirildi")
    ok(y.action_kisi_olustur()['context']['default_phone'] == '05559998877', "kişi oluşturma için numara hazır")
ok(not C._olay_isle({'event': 'bilinmeyen'}), "bilinmeyen olay yok sayıldı")
ok(mus.atlas_cagri_sayisi == 3 and kisi.atlas_cagri_sayisi == 2, "arama sayısı: şirket kişileriyle birlikte 3, kişi 2")
ok(santral.olay_url.endswith('/voip/olay/' + santral.olay_anahtari), "olay adresi")
env.cr.rollback(); print("(geri alındı)")
