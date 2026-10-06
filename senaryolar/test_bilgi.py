from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
M = env['atlas.bilgi.makale']
ic = env.ref('base.group_user')
ali = env['res.users'].create({'name': 'Ali Bilgi', 'login': 'bilgi_ali', 'group_ids': [(6, 0, [ic.id])]})
ayse = env['res.users'].create({'name': 'Ayşe Bilgi', 'login': 'bilgi_ayse', 'group_ids': [(6, 0, [ic.id])]})
can = env['res.users'].create({'name': 'Can Bilgi', 'login': 'bilgi_can', 'group_ids': [(6, 0, [ic.id])]})

# ---------------------------------------------------------------- çalışma alanı ve hiyerarşi
kok = M.create({'name': 'Satış El Kitabı', 'simge': '💼', 'body': '<p>Satış süreçleri</p>'})
alt1 = M.create({'name': 'Teklif Hazırlama', 'parent_id': kok.id})
alt2 = M.create({'name': 'İade Politikası', 'parent_id': kok.id})
torun = M.create({'name': 'İade Formu', 'parent_id': alt2.id})
ok(kok.kategori == 'calisma' and torun.kategori == 'calisma' and torun.kok_id == kok and torun.etkin_yetki == 'write',
   "çalışma alanı: kök, alt ve torun aynı bölümde, erişim miras")
ok(alt1.sira < alt2.sira, "yeni alt sayfa sona eklenir")
ok(M.with_user(ali).search_count([('id', '=', torun.id)]) == 1 and torun.with_user(ali).kullanici_yetkisi == 'write',
   "iç kullanıcı çalışma alanını okur ve düzenler")
torun.with_user(ali).write({'body': '<p>Ali yazdı</p>'})
ok(torun.son_duzenleyen_id == ali, "son düzenleyen güncellenir")

# ---------------------------------------------------------------- yetki: okuma, üye, engel
alt2.ic_yetki = 'read'
ok(torun.etkin_yetki == 'read' and torun.yetki_kaynak_id == alt2, "alt makalenin erişimi değişince torunlar miras alır")
try:
    torun.with_user(ali).write({'name': 'değişti'}); yazdi = True
except AccessError:
    yazdi = False
ok(not yazdi and torun.with_user(ali).name == 'İade Formu', "okuma erişiminde düzenleme engellenir")
alt2.uye_ids = [(0, 0, {'partner_id': ayse.partner_id.id, 'yetki': 'write'})]
torun.with_user(ayse).write({'name': 'İade Formu v2'})
ok(torun.name == 'İade Formu v2', "üst makalede düzenleyici üye olan alt sayfayı da düzenler")
alt1.uye_ids = [(0, 0, {'partner_id': can.partner_id.id, 'yetki': 'none'})]
ok(not M.with_user(can).search_count([('id', '=', alt1.id)]) and M.with_user(ali).search_count([('id', '=', alt1.id)]),
   "üye bazında engelleme: yalnız o kişi göremez")
kok.uye_ids = [(0, 0, {'partner_id': can.partner_id.id, 'yetki': 'read'})]
try:
    kok.with_user(can).write({'name': 'x'}); can_yazdi = True
except AccessError:
    can_yazdi = False
ok(not can_yazdi, "okuyucu üye, iç erişim düzenlenebilir olsa da düzenleyemez")

# ---------------------------------------------------------------- özel ve paylaşılan
ozel_id = M.with_user(ali).yeni_makale(False, 'ozel')
ozel = M.browse(ozel_id)
ok(ozel.kategori == 'ozel' and ozel.with_user(ali).kullanici_yetkisi == 'write', "özel makale: sahibine düzenleme")
ok(not M.with_user(ayse).search_count([('id', '=', ozel.id)]), "özel makaleyi başkası göremez")
sihirbaz = env['atlas.bilgi.paylas'].with_user(ali).create({'makale_id': ozel.id, 'davet_partner_ids': [(6, 0, [ayse.partner_id.id])],
                                                            'davet_yetki': 'read', 'mesaj': 'Göz atar mısın?'})
sihirbaz.action_davet()
ozel.invalidate_recordset()
ok(ozel.kategori == 'paylasilan' and M.with_user(ayse).search_count([('id', '=', ozel.id)]) == 1 and ozel.with_user(ayse).kullanici_yetkisi == 'read',
   "paylaş: davet edilen okur, bölüm 'Paylaşılan' olur")
ok(ayse.partner_id in ozel.message_ids[:1].partner_ids, "davet bildirimi gönderildi")
try:
    env['atlas.bilgi.paylas'].with_user(ayse).create({'makale_id': ozel.id}).action_kaydet(); yetkisiz = True
except AccessError:
    yetkisiz = False
ok(not yetkisiz, "okuyucu paylaşım ayarlarını değiştiremez")
try:
    M.with_user(ayse).create({'name': 'izinsiz alt', 'parent_id': ozel.id}); alt_izin = True
except AccessError:
    alt_izin = False
ok(not alt_izin, "okuyucu alt sayfa ekleyemez")

# ---------------------------------------------------------------- herkese açık bağlantı
w = env['atlas.bilgi.paylas'].create({'makale_id': kok.id})
w.herkese_acik = True
w.action_kaydet()
ok(kok.herkese_acik and kok.erisim_anahtari and kok.paylasim_url.endswith(f'/bilgi/paylas/{kok.id}/{kok.erisim_anahtari}'), "herkese açık bağlantı")
from odoo.addons.atlas_bilgi.controllers.main import AtlasBilgiPaylasim
ok(hasattr(AtlasBilgiPaylasim, 'paylas'), "paylaşım denetleyicisi")

# ---------------------------------------------------------------- favoriler ve kenar çubuğu
kok.with_user(ali).action_favori()
alt2.with_user(ali).action_favori()
ok(kok.with_user(ali).favori_mi and M.with_user(ali).search_count([('favori_mi', '=', True)]) == 2 and not kok.with_user(ayse).favori_mi,
   "favoriler kullanıcıya özel")
veri = M.with_user(ali).kenar_verisi(torun.id)
ok([f['id'] for f in veri['favoriler']] == [kok.id, alt2.id] and any(d['id'] == kok.id for d in veri['bolumler']['calisma'])
   and veri['zincir'] == [kok.id, alt2.id, torun.id] and any(d['id'] == ozel.id for d in veri['bolumler']['paylasilan']),
   "kenar çubuğu: favoriler, bölümler, açık makale zinciri")
M.with_user(ali).favori_sirala([alt2.id, kok.id])
ok([f['id'] for f in M.with_user(ali).kenar_verisi()['favoriler']] == [alt2.id, kok.id], "favori sırası")
ok([d['id'] for d in M.alt_makaleler(kok.id)] == [alt1.id, alt2.id], "alt makaleler sırayla")

# ---------------------------------------------------------------- taşıma
M.makale_tasi(alt2.id, kok.id, False, alt1.id)
ok([d['id'] for d in M.alt_makaleler(kok.id)] == [alt2.id, alt1.id], "sürükle-bırak: kardeşler arasında sıra")
M.makale_tasi(alt1.id, alt2.id)
ok(alt1.parent_id == alt2 and alt1.kok_id == kok, "sürükle-bırak: başka makalenin altına")
try:
    M.makale_tasi(kok.id, torun.id); dongu = True
except (ValidationError, UserError):
    dongu = False
ok(not dongu, "makale kendi altına taşınamaz")
M.makale_tasi(alt1.id, False, 'calisma')
ok(not alt1.parent_id and alt1.kategori == 'calisma' and alt1.kok_id == alt1, "bölüm köküne taşıma")
env['atlas.bilgi.tasi'].create({'makale_id': alt1.id, 'hedef': 'ozel'}).action_tasi()
ok(alt1.kategori == 'ozel' and alt1.ic_yetki == 'none', "taşı sihirbazı: özel bölüme")

# ---------------------------------------------------------------- kilit ve sürüm geçmişi
kok.write({'body': '<p>Satış süreçleri v2</p>'})
kok.write({'body': '<p>Satış süreçleri v3</p>'})
ok(len((kok.html_field_history_metadata or {}).get('body', [])) >= 2, "sürüm geçmişi kaydediliyor")
kok.action_kilit()
try:
    kok.write({'body': '<p>kilitliyken</p>'}); kilit = True
except UserError:
    kilit = False
ok(not kilit and not kok.duzenleyebilir, "kilitli makale düzenlenemez")
kok.action_kilit()
ok(kok.duzenleyebilir, "kilit açıldı")

# ---------------------------------------------------------------- şablonlar
sablonlar = M.with_user(ali).sablonlar()
ok(len(sablonlar) >= 5 and {'Toplantı Notu', 'Süreç Dokümanı'} <= {s['ad'] for s in sablonlar}, "şablon galerisi")
sablon = env.ref('atlas_bilgi.sablon_toplanti')
yeni = M.browse(M.with_user(ali).yeni_makale(False, 'calisma', sablon.id))
ok(yeni.name == 'Toplantı Notu' and 'Gündem' in yeni.body and not yeni.sablon_mi and yeni.kategori == 'calisma', "şablondan makale")
try:
    sablon.with_user(ali).write({'name': 'boz'}); sablon_yaz = True
except AccessError:
    sablon_yaz = False
ok(not sablon_yaz, "şablonlar kullanıcılar için salt okunur")

# ---------------------------------------------------------------- öğeler (veritabanı)
proje = M.create({'name': 'Yol Haritası'})
proje.action_oge_kur()
asamalar = env['atlas.bilgi.asama'].search([('makale_id', '=', proje.id)])
proje.ozellik_tanimi = [{'name': 'oncelik', 'string': 'Öncelik', 'type': 'selection', 'selection': [['y', 'Yüksek'], ['d', 'Düşük']]},
                        {'name': 'tahmin', 'string': 'Tahmin (gün)', 'type': 'integer'}]
oge = M.create({'name': 'Mobil uygulama', 'parent_id': proje.id, 'oge_mi': True, 'asama_id': asamalar[0].id,
                'ozellikler': {'oncelik': 'y', 'tahmin': 5}})
ok(len(asamalar) == 3 and oge in proje.oge_ids and oge not in proje.alt_ids, "öğe listesi: aşamalar ve öğe")
ok(oge.ozellikler['tahmin'] == 5 and oge.ozellikler['oncelik'] == 'y', "öğe özellikleri (properties)")
ok(not any(d['id'] == oge.id for d in M.alt_makaleler(proje.id)), "öğeler kenar çubuğunda alt sayfa olarak görünmez")

# ---------------------------------------------------------------- arama
sonuc = M.with_user(ali).ara('süreçleri')
ok(any(s['id'] == kok.id for s in sonuc), "arama: içerikte geçen metin")
ok(not any(s['id'] == ozel.id for s in M.with_user(can).ara('Adsız')), "arama yetkiye uyar")

# ---------------------------------------------------------------- çöp kutusu
kok.action_cope_at()
ok(not kok.active and not torun.active and kok.cope_atildi and torun.cope_atildi and kok.silinme_tarihi == fields.Date.today() + timedelta(days=30),
   "çöpe at: alt sayfalarla birlikte, 30 gün sonra silinecek")
ok(not M.with_user(ali).search_count([('favori_mi', '=', True), ('id', '=', kok.id)]), "çöpe atılan favorilerden çıkar")
kok.action_geri_yukle()
ok(kok.active and torun.active and not torun.cope_atildi, "geri yükle: alt sayfalarla")
alt2.action_cope_at()
alt2.silinme_tarihi = fields.Date.today() - timedelta(days=1)
torun_id = torun.id
M._cron_cop_temizle()
ok(not alt2.exists() and not M.with_context(active_test=False).browse(torun_id).exists(), "zamanlanmış görev süresi dolanı kalıcı siler")

# ---------------------------------------------------------------- gömülü görünüm, yorum, kayıt bağlantısı
import json
from lxml import html as lxml_html
secenekler = M.with_user(ali).gorunum_secenekleri('Kişi') or M.with_user(ali).gorunum_secenekleri('')
ok(secenekler and all(s['modlar'] and set(s['modlar']) <= {'list', 'kanban'} for s in secenekler), "gömülebilir menü görünümleri listelenir")
s0 = secenekler[0]
belge = M.create({'name': 'Gösterge', 'body': '<p>Özet</p>'})
belge.with_user(ali).gorunum_ekle(s0['eylem_id'], 'kanban', 'Açık işler', [('id', '>', 0)], {'group_by': ['create_uid']})
govde = lxml_html.fromstring(belge.body)
gomulu = govde.xpath("//div[@data-embedded='atlasBilgiGorunum']")
props = json.loads(gomulu[0].get('data-embedded-props')) if gomulu else {}
ok(gomulu and props.get('eylem_id') == s0['eylem_id'] and props.get('tur') == 'kanban' and props.get('context', {}).get('group_by') == ['create_uid']
   and 'Özet' in belge.body, "görünüm makaleye gömüldü (filtre ve gruplama saklı, kaydedince silinmez)")
ok(M.gorunum_bilgisi(s0['eylem_id'])['model'] == s0['model'], "gömülü görünüm bilgisi")
belge.kilitli = True
try:
    belge.with_user(ali).gorunum_ekle(s0['eylem_id'], 'list', 'x'); kilitli_ekledi = True
except AccessError:
    kilitli_ekledi = False
ok(not kilitli_ekledi, "kilitli makaleye görünüm eklenemez")
belge.kilitli = False

y = belge.with_user(ali).yorum_olustur('Özet', 'Bu bölüm güncel mi?')
ok(y['metin'] == 'Özet' and len(y['mesajlar']) == 1 and y['mesajlar'][0]['yazar'] == 'Ali Bilgi', "seçili metne yorum dizisi")
y2 = M.with_user(ayse).yorum_yanitla(y['id'], 'Evet, güncellendi.')
ok(len(y2['mesajlar']) == 2 and y2['mesajlar'][1]['yazar'] == 'Ayşe Bilgi', "yoruma yanıt")
ok(belge.acik_yorum_sayisi == 1, "açık yorum sayısı")
M.with_user(ayse).yorum_coz(y['id'])
belge.invalidate_recordset()
ok(belge.acik_yorum_sayisi == 0 and belge.with_user(ali).yorumlar()[0]['cozuldu'], "yorum çözüldü")
gizli = M.with_user(ali).create({'name': 'Gizli not', 'ic_yetki': 'none'})
gy = gizli.with_user(ali).yorum_olustur('x', 'özel')
try:
    M.with_user(can).yorum_getir(gy['id']); sizdi = True
except AccessError:
    sizdi = False
ok(not sizdi and not env['atlas.bilgi.yorum'].with_user(can).search_count([('id', '=', gy['id'])]), "erişimi olmayan yorumları göremez")

talep = env['res.partner'].create({'name': 'Kayıt Bağlantısı Testi'})
belge.with_user(ali).kayda_bagla('res.partner', talep.id)
ok([m['id'] for m in M.with_user(ali).kayit_makaleleri('res.partner', talep.id)] == [belge.id]
   and belge.baglanti_listesi()[0]['ad'] == talep.display_name, "makale kayda bağlandı; makalede bağlı kayıtlar")
belge.kayda_gonder('res.partner', talep.id)
mesaj = talep.message_ids[:1].body
ok('Gösterge' in mesaj and 'Özet' in mesaj and '<h4>' in mesaj and 'data-embedded' not in mesaj and 'Açık işler' in mesaj,
   "makale kayda mesaj olarak eklendi (HTML; gömülü görünüm başlığa çevrildi, yorum işareti yok)")
ok(M.with_user(ali).kayit_makaleleri('res.partner', talep.id).__len__() == 1, "aynı bağlantı ikinci kez oluşmaz")
ok(belge.makale_onizleme()['ad'] == 'Gösterge', "makale önizleme")
M.with_user(ali).baglanti_kaldir(M.with_user(ali).kayit_makaleleri('res.partner', talep.id)[0]['baglanti_id'])
ok(not M.kayit_makaleleri('res.partner', talep.id), "bağlantı kaldırıldı")

eylem = M.with_user(ali).action_bilgi_ana()
ok(eylem['res_model'] == 'atlas.bilgi.makale' and eylem['res_id'], "menü eylemi bir makale açar")

env.cr.rollback(); print("(geri alındı)")
