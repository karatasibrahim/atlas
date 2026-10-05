from datetime import date, datetime, timedelta

import pytz
from odoo import fields
from odoo.exceptions import UserError, ValidationError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
T = env['atlas.randevu.tur']
tz = pytz.timezone('Europe/Istanbul')
ic = env.ref('base.group_user')
u1 = env['res.users'].create({'name': 'Danışman Bir', 'login': 'randevu_u1', 'email': 'u1@ornek.com', 'group_ids': [(6, 0, [ic.id])], 'tz': 'Europe/Istanbul'})
u2 = env['res.users'].create({'name': 'Danışman İki', 'login': 'randevu_u2', 'email': 'u2@ornek.com', 'group_ids': [(6, 0, [ic.id])], 'tz': 'Europe/Istanbul'})
bugun = fields.Date.context_today(T)
pazartesi = bugun + timedelta(days=(7 - bugun.weekday()) % 7 or 7)
if (pazartesi - bugun).days < 2:
    pazartesi += timedelta(days=7)


def utc(gun, saat, dakika=0):
    return tz.localize(datetime.combine(gun, datetime.min.time()) + timedelta(hours=saat, minutes=dakika)).astimezone(pytz.utc).replace(tzinfo=None)


def saatler(tur, gun, **kw):
    return [s['saat'] for s in tur.musait_slotlar(gun, gun, **kw).get(gun.isoformat(), [])]


tur = T.create({'name': 'Danışmanlık', 'sure': 1.0, 'tz': 'Europe/Istanbul', 'personel_ids': [(6, 0, [u1.id, u2.id])],
                'slot_ids': [(0, 0, {'gun': '1', 'bas_saat': 9.0, 'bit_saat': 12.0})], 'max_planlama_gun': 60, 'yayinda': True})
gunler = tur.musait_slotlar(pazartesi, pazartesi)
ok(saatler(tur, pazartesi) == ['09:00', '10:00', '11:00'] and set(gunler[pazartesi.isoformat()][0]['personel']) == {u1.id, u2.id},
   "haftalık dilimden 1 saatlik başlangıçlar; iki personel uygun")
ok(not tur.musait_slotlar(pazartesi + timedelta(days=1), pazartesi + timedelta(days=1)), "dilim olmayan gün boş")

env['calendar.event'].create({'name': 'Dolu', 'start': utc(pazartesi, 10), 'stop': utc(pazartesi, 11),
                              'partner_ids': [(6, 0, [u1.partner_id.id])], 'user_id': u1.id})
s10 = [s for s in tur.musait_slotlar(pazartesi, pazartesi)[pazartesi.isoformat()] if s['saat'] == '10:00'][0]
ok(s10['personel'] == [u2.id], "takvimi dolu personel o saatte uygun değil")

e1 = tur.randevu_olustur(fields.Datetime.to_string(utc(pazartesi, 10)), {'ad': 'Mehmet Müşteri', 'email': 'mehmet@ornek.com', 'telefon': '05551112233'})
ok(e1.user_id == u2 and e1.randevu_durum == 'onayli' and e1.randevu_musteri_id.email == 'mehmet@ornek.com'
   and {u2.partner_id, e1.randevu_musteri_id} <= set(e1.partner_ids) and e1.stop - e1.start == timedelta(hours=1),
   "randevu: uygun personele atandı, müşteri kişisi oluştu, onaylı")
ok(env['mail.mail'].search_count([('model', '=', 'calendar.event'), ('res_id', '=', e1.id), ('email_to', 'ilike', 'mehmet@ornek.com')]) == 1,
   "onay e-postası müşteriye")
ok('10:00' not in saatler(tur, pazartesi), "dolan saat artık sunulmuyor")
try:
    tur.randevu_olustur(fields.Datetime.to_string(utc(pazartesi, 10)), {'ad': 'Ayşe', 'email': 'ayse@ornek.com'}); cift = True
except UserError:
    cift = False
ok(not cift, "aynı saate ikinci randevu reddedilir")
e2 = tur.randevu_olustur(fields.Datetime.to_string(utc(pazartesi, 9)), {'ad': 'Ayşe', 'email': 'ayse@ornek.com'})
ok(e2.user_id == u1, "otomatik atama: o gün daha az randevusu olan personel")
m2 = tur.randevu_olustur(fields.Datetime.to_string(utc(pazartesi, 11)), {'ad': 'Mehmet', 'email': 'MEHMET@ornek.com'})
ok(m2.randevu_musteri_id == e1.randevu_musteri_id, "aynı e-postayla gelen müşteri tekrar oluşturulmaz")
try:
    tur.randevu_olustur(fields.Datetime.to_string(utc(pazartesi, 11)), {'ad': 'X', 'email': 'gecersiz'}); kotu = True
except UserError:
    kotu = False
ok(not kotu, "geçersiz e-posta reddedilir")

# başlangıç aralığı, sınırlar, dönem
tur2 = T.create({'name': 'Kısa Görüşme', 'sure': 1.0, 'slot_araligi': 0.5, 'personel_ids': [(6, 0, [u1.id])],
                 'slot_ids': [(0, 0, {'gun': str(pazartesi.isoweekday() % 7 + 1), 'bas_saat': 14.0, 'bit_saat': 16.0})], 'max_planlama_gun': 60})
sali = pazartesi + timedelta(days=1)
ok(saatler(tur2, sali) == ['14:00', '14:30', '15:00'], "yarım saat aralıkla başlangıçlar")
tur2.max_planlama_gun = (sali - bugun).days - 1
ok(not saatler(tur2, sali), "en geç planlama sınırı")
tur2.write({'max_planlama_gun': 60, 'kategori': 'donemlik', 'baslangic': utc(sali + timedelta(days=7), 0), 'bitis': utc(sali + timedelta(days=8), 0)})
ok(not saatler(tur2, sali) and saatler(tur2, sali + timedelta(days=7)), "belirli tarih aralığı dışında saat yok")
tur2.write({'kategori': 'ozel', 'slot_ids': [(5, 0, 0), (0, 0, {'tip': 'tek', 'bas_zaman': utc(sali, 16), 'bit_zaman': utc(sali, 18)})]})
ok(saatler(tur2, sali) == ['16:00', '16:30', '17:00'], "belirli saat dilimleri")
try:
    env['atlas.randevu.slot'].create({'tur_id': tur2.id, 'gun': '1', 'bas_saat': 12, 'bit_saat': 9}); hatali = True
except ValidationError:
    hatali = False
ok(not hatali, "hatalı dilim saati reddedilir")

# çalışma saatleri
tur3 = T.create({'name': 'Sabah', 'sure': 1.0, 'personel_ids': [(6, 0, [u1.id])], 'calisma_saatleri': True, 'max_planlama_gun': 60,
                 'slot_ids': [(0, 0, {'gun': '1', 'bas_saat': 6.0, 'bit_saat': 10.0})]})
saat3 = saatler(tur3, pazartesi + timedelta(days=7))
ok('06:00' not in saat3 and '08:00' in saat3, "çalışma saatleri dışı gösterilmez")

# kaynak + kapasite
masa = env['atlas.randevu.kaynak'].create({'name': 'Toplantı Odası', 'kapasite': 4})
oda = env['atlas.randevu.kaynak'].create({'name': 'Küçük Oda', 'kapasite': 2})
restoran = T.create({'name': 'Rezervasyon', 'sure': 2.0, 'planlama': 'kaynak', 'kaynak_ids': [(6, 0, [masa.id, oda.id])],
                     'kapasite_yonetimi': True, 'max_kisi': 4, 'max_planlama_gun': 60,
                     'slot_ids': [(0, 0, {'gun': '1', 'bas_saat': 18.0, 'bit_saat': 20.0})]})
r1 = restoran.randevu_olustur(fields.Datetime.to_string(utc(pazartesi, 18)), {'ad': 'Grup', 'email': 'grup@ornek.com'}, kisi=3, kaynak_id=masa.id)
ok(r1.randevu_kaynak_ids == masa and r1.randevu_rezervasyon_ids.kapasite == 3 and r1.location == 'Toplantı Odası', "kaynak rezervasyonu ve kişi sayısı")
s = restoran.musait_slotlar(pazartesi, pazartesi, kisi=2)[pazartesi.isoformat()][0]
ok(s['kaynaklar'] == [oda.id], "kapasitesi dolan kaynak 2 kişiye sunulmaz, diğer kaynak sunulur")
s1 = restoran.musait_slotlar(pazartesi, pazartesi, kisi=1)[pazartesi.isoformat()][0]
ok(set(s1['kaynaklar']) == {masa.id, oda.id}, "kalan kapasite 1 kişiye yeter")
r1.action_randevu_iptal()
ok(r1.randevu_durum == 'iptal' and r1.show_as == 'free'
   and set(restoran.musait_slotlar(pazartesi, pazartesi, kisi=4)[pazartesi.isoformat()][0]['kaynaklar']) == {masa.id}, "iptal kapasiteyi serbest bırakır")

# talep (elle onay) ve sorular
s_metin = env['atlas.randevu.soru'].create({'name': 'Konu', 'tip': 'char', 'zorunlu': True})
s_secim = env['atlas.randevu.soru'].create({'name': 'İlgi alanları', 'tip': 'checkbox',
                                             'secenek_ids': [(0, 0, {'name': 'ERP'}), (0, 0, {'name': 'E-fatura'}), (0, 0, {'name': 'Bordro'})]})
tur.write({'otomatik_onay': False, 'soru_ids': [(6, 0, [s_metin.id, s_secim.id])]})
gun2 = pazartesi + timedelta(days=7)
try:
    tur.randevu_olustur(fields.Datetime.to_string(utc(gun2, 9)), {'ad': 'Zeynep', 'email': 'zeynep@ornek.com'}); eksik = True
except UserError:
    eksik = False
ok(not eksik, "zorunlu soru yanıtlanmadan randevu alınamaz")
secenekler = s_secim.secenek_ids
t1 = tur.randevu_olustur(fields.Datetime.to_string(utc(gun2, 9)), {'ad': 'Zeynep', 'email': 'zeynep@ornek.com'},
                         yanitlar={s_metin.id: 'E-dönüşüm', s_secim.id: [secenekler[0].id, secenekler[1].id]}, not_metni='Öğleden önce')
ok(t1.randevu_durum == 'talep' and t1.activity_ids, "elle onaylı tür: talep + personele aktivite")
ok(len(t1.randevu_yanit_ids) == 3 and 'E-dönüşüm' in t1.description and 'ERP, E-fatura' in t1.description and 'Öğleden önce' in t1.description,
   "yanıtlar kaydedildi ve açıklamaya yazıldı")
ok(env['mail.mail'].search_count([('res_id', '=', t1.id), ('subject', 'ilike', 'talebiniz alındı')]) == 1, "talep alındı e-postası")
t1.action_randevu_onayla()
ok(t1.randevu_durum == 'onayli' and env['mail.mail'].search_count([('res_id', '=', t1.id), ('subject', 'ilike', 'onaylandı')]) == 1,
   "onayla: durum ve onay e-postası")
t1.action_randevu_geldi()
ok(t1.randevu_durum == 'geldi' and not t1._randevu_iptal_edilebilir(), "geldi; gelmiş randevu iptal edilemez")

# davet bağlantısı
davet = env['atlas.randevu.davet'].create({'tur_ids': [(6, 0, [tur.id])], 'personel_ids': [(6, 0, [u1.id])], 'kisa_kod': 'u1-ozel'})
gun3 = pazartesi + timedelta(days=14)
d_slot = tur.musait_slotlar(gun3, gun3, davet=davet)[gun3.isoformat()]
ok(all(s['personel'] == [u1.id] for s in d_slot) and env['atlas.randevu.davet']._bul('u1-ozel') == davet and davet.url.endswith('/randevu/davet/u1-ozel'),
   "davet: personel kısıtı ve kısa kod")
d_e = tur.randevu_olustur(fields.Datetime.to_string(utc(gun3, 9)), {'ad': 'Davetli', 'email': 'davetli@ornek.com'},
                          yanitlar={s_metin.id: 'x'}, davet=davet)
ok(d_e.user_id == u1 and d_e.randevu_davet_id == davet and davet.etkinlik_sayisi == 1, "davetle alınan randevu")
try:
    env['atlas.randevu.davet'].create({'tur_ids': [(6, 0, [tur.id])], 'kisa_kod': 'boşluk var'}); kod = True
except ValidationError:
    kod = False
ok(not kod, "kısa kod biçimi denetlenir")

# iptal süresi, ics, sayılar
ok(e1._randevu_iptal_edilebilir() and 'DTSTART:' in e1._randevu_ics() and 'SUMMARY:Danışmanlık' in e1._randevu_ics(), "iptal edilebilir; .ics")
tur.min_iptal_saat = 24 * 400
ok(not e1._randevu_iptal_edilebilir(), "iptal süresi geçtiyse iptal edilemez")
tur.invalidate_recordset()
ok(tur.randevu_sayisi == 5 and tur.yaklasan_sayisi >= 3, "tür sayaçları")
ok(e1._randevu_url().endswith(f'/randevu/etkinlik/{e1.id}/{e1.access_token}'), "müşteri yönetim bağlantısı")

if 'crm.lead' in env:
    tur.write({'firsat_olustur': True, 'otomatik_onay': True})
    c = tur.randevu_olustur(fields.Datetime.to_string(utc(gun3, 10)), {'ad': 'Fırsat', 'email': 'firsat@ornek.com'}, yanitlar={s_metin.id: 'y'})
    ok(c.opportunity_id and c.opportunity_id.partner_id == c.randevu_musteri_id, "CRM fırsatı oluşturuldu")

env.cr.rollback(); print("(geri alındı)")
