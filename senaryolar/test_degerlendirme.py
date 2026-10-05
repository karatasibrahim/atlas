from datetime import date
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
U = env['res.users'].with_context(no_reset_password=True)
g = [Command.set([env.ref('base.group_user').id])]
u_cal, u_yon, u_diger = (U.create({'name': f'DGR {a}', 'login': f'dgr_{a}', 'group_ids': g}) for a in ('calisan', 'yonetici', 'diger'))
E = env['hr.employee']
e_yon = E.create({'name': 'DGR Yönetici', 'user_id': u_yon.id})
e_cal = E.create({'name': 'DGR Çalışan', 'user_id': u_cal.id, 'parent_id': e_yon.id})
E.create({'name': 'DGR Diğer', 'user_id': u_diger.id})
sablon = env.ref('atlas_degerlendirme.sablon_genel')
donem = env['atlas.degerlendirme.donem'].create({'name': 'DGR 2026', 'sablon_id': sablon.id, 'tarih_bas': date(2026, 1, 1),
                                                  'tarih_bit': date(2026, 12, 31), 'son_tarih': date(2026, 12, 20),
                                                  'employee_ids': [Command.set(e_cal.ids)]})
H = env['atlas.hedef']
h1 = H.with_user(u_yon).create({'name': 'Şikâyetleri azalt', 'employee_id': e_cal.id, 'son_tarih': date(2026, 11, 30), 'agirlik': 1})
h2 = H.with_user(u_yon).create({'name': 'Sertifika al', 'employee_id': e_cal.id, 'son_tarih': date(2026, 10, 30), 'agirlik': 1})
ok(h1.yonetici_kullanici_id == u_yon and h1 in H.with_user(u_cal).search([]) and h1 not in H.with_user(u_diger).search([]),
   "yönetici ekibine hedef verdi; çalışan görüyor, ilgisiz kullanıcı görmüyor")
h1.with_user(u_cal).ilerleme = 60
h2.with_user(u_cal).ilerleme = 100
ok(h1.ilerleme == 60 and h2.durum == 'tamamlandi', "çalışan ilerlemeyi güncelledi; %100 hedef tamamlandı")
try:
    with env.cr.savepoint(): H.with_user(u_cal).create({'name': 'Kendine hedef', 'employee_id': e_cal.id}); kendisi = True
except AccessError: kendisi = False
ok(not kendisi, "çalışan kendine hedef açamaz (yönetici verir)")
donem.action_baslat()
d = donem.degerlendirme_ids
ok(len(d) == 1 and d.durum == 'oz' and len(d.cevap_ids) == 6 and d.yonetici_id == e_yon, "dönem başladı: öz değerlendirme, 6 yetkinlik")
ok(d.activity_ids.user_id == u_cal, "çalışana öz değerlendirme aktivitesi")
D = env['atlas.degerlendirme']
ok(d in D.with_user(u_cal).search([]) and d in D.with_user(u_yon).search([]) and d not in D.with_user(u_diger).search([]),
   "değerlendirmeyi çalışan ve yöneticisi görür, başkası görmez")
puanli = d.cevap_ids.filtered(lambda c: c.tur == 'puan')
try:
    with env.cr.savepoint(): puanli[0].with_user(u_yon).yonetici_puan = '5'; erken = True
except AccessError: erken = False
ok(not erken, "yönetici öz değerlendirme aşamasında puan veremez")
try:
    with env.cr.savepoint(): d.with_user(u_cal).action_oz_tamamla(); eksik = True
except UserError: eksik = False
ok(not eksik, "puanlanmamış yetkinlikle öz değerlendirme gönderilemez")
for c in puanli:
    c.with_user(u_cal).oz_puan = '4'
try:
    with env.cr.savepoint(): puanli[0].with_user(u_cal).yonetici_puan = '5'; kendi = True
except AccessError: kendi = False
ok(not kendi, "çalışan yönetici puanı giremez")
d.with_user(u_cal).action_oz_tamamla()
ok(d.durum == 'yonetici' and u_yon in d.activity_ids.user_id, "öz değerlendirme gönderildi, yöneticiye aktivite")
try:
    with env.cr.savepoint(): puanli[0].with_user(u_cal).oz_puan = '5'; degisti = True
except AccessError: degisti = False
ok(not degisti, "gönderilen öz puan değiştirilemez")
puanlar = ['5', '4', '4', '3', '4']
for c, p in zip(puanli.sorted('sequence'), puanlar):
    c.with_user(u_yon).yonetici_puan = p
d.with_user(u_yon).write({'guclu_yonler': 'Analitik düşünce', 'gelisim_alanlari': 'Sunum'})
d.with_user(u_yon).action_yonetici_tamamla()
# ağırlıklar: 2,2,1,1,1 → (5*2 + 4*2 + 4 + 3 + 4)/7 * 20 = 29/7*20 = 82.857
ok(d.durum == 'gorusme' and abs(d.yetkinlik_puan - 82.86) < 0.1, f"yetkinlik puanı ağırlıklı: {d.yetkinlik_puan:.2f}")
ok(abs(d.hedef_puan - 80) < 0.01 and abs(d.sonuc_puan - (82.857 * 0.6 + 80 * 0.4)) < 0.1 and d.derece == 'B',
   f"hedef 80, sonuç {d.sonuc_puan:.1f}, derece {d.derece}")
try:
    with env.cr.savepoint(): d.with_user(u_cal).action_tamamla(); bitirdi = True
except AccessError: bitirdi = False
ok(not bitirdi, "çalışan değerlendirmeyi tamamlayamaz")
d.with_user(u_cal).action_calisan_onayla()
d.with_user(u_yon).action_tamamla()
ok(d.durum == 'tamamlandi' and d.calisan_onayi and e_cal.atlas_son_derece == 'B' and e_cal.atlas_sonraki_degerlendirme == date(2027, 12, 31),
   "tamamlandı: çalışanda son derece ve sonraki değerlendirme tarihi")
ok(donem.tamamlanan == 1 and abs(donem.ortalama_puan - d.sonuc_puan) < 0.01, "dönem özeti")
donem.action_kapat()
ok(donem.durum == 'kapandi', "dönem kapandı")
d.action_geri_al()
ok(d.durum == 'yonetici', "İK geri aldı")
env.cr.rollback(); print("(geri alındı)")
