from datetime import date, datetime, timedelta
from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
L = env['account.analytic.line']
U = env['res.users'].with_context(no_reset_password=True)
g_user = env.ref('hr_timesheet.group_hr_timesheet_user'); g_onay = env.ref('hr_timesheet.group_hr_timesheet_approver')
calisan_u = U.create({'name': 'ZMN Çalışan', 'login': 'zmn_calisan', 'email': 'c@zmn.local', 'group_ids': [Command.set([env.ref('base.group_user').id, g_user.id])]})
diger_u = U.create({'name': 'ZMN Diğer', 'login': 'zmn_diger', 'group_ids': [Command.set([env.ref('base.group_user').id, g_user.id])]})
yonetici_u = U.create({'name': 'ZMN Yönetici', 'login': 'zmn_yonetici', 'email': 'y@zmn.local', 'group_ids': [Command.set([env.ref('base.group_user').id, g_onay.id])]})
e_yon = env['hr.employee'].create({'name': 'ZMN Yönetici', 'user_id': yonetici_u.id})
e = env['hr.employee'].create({'name': 'ZMN Çalışan', 'user_id': calisan_u.id, 'parent_id': e_yon.id})
env['hr.employee'].create({'name': 'ZMN Diğer', 'user_id': diger_u.id})
proje = env['project.project'].create({'name': 'ZMN Proje', 'allow_timesheets': True, 'privacy_visibility': 'employees'})
gorev = env['project.task'].create({'name': 'ZMN Görev', 'project_id': proje.id})
pzt = date(2026, 11, 2)
Lc = L.with_user(calisan_u)
def hucre(saat, tarih=pzt, task=gorev.id, kim=Lc):
    kim.atlas_hucre_kaydet(e.id, proje.id, task, str(tarih), saat)
    return L.search([('employee_id', '=', e.id), ('project_id', '=', proje.id), ('task_id', '=', task), ('date', '=', tarih)])
s = hucre(3)
ok(len(s) == 1 and s.unit_amount == 3 and s.user_id == calisan_u, "boş hücreye 3 saat: kayıt oluştu")
s = hucre(5)
ok(len(s) == 1 and s.unit_amount == 5, "5 saate çıkarıldı: aynı kayda eklendi")
Lc.create({'employee_id': e.id, 'project_id': proje.id, 'task_id': gorev.id, 'date': pzt, 'unit_amount': 2, 'name': 'Toplantı'})
s = hucre(4)
ok(round(sum(s.mapped('unit_amount')), 2) == 4 and len(s) == 1 and s.unit_amount == 4, "7 → 4: fark sondan düşüldü, sıfırlanan kayıt silindi")
s = hucre(0)
ok(not s, "0 yazınca kayıtlar silindi")
hucre(2.5, pzt + timedelta(days=1)); hucre(1, pzt - timedelta(days=3), False)
v = Lc.atlas_haftalik(str(pzt + timedelta(days=3)))
satir = next(x for x in v['satirlar'] if x['task_id'] == gorev.id)
ok(v['gunler'][0]['tarih'] == str(pzt) and satir['hucreler'][str(pzt + timedelta(days=1))]['saat'] == 2.5 and v['kendi'], "haftalık veri: pazartesiden başlıyor, hücre değeri")
ok(any(x['task_id'] is False and x['toplam'] == 0 for x in v['satirlar']), "geçen haftanın satırı boş olarak geliyor")
ok(v['gunler'][0]['beklenen'] == 8 and v['gunler'][5]['beklenen'] == 0, "mesai: hafta içi 8, cumartesi 0 saat")
ok(not v['onaylayici'] and not v['calisanlar'], "çalışan onaylayıcı değil, çalışan seçemez")
try:
    with env.cr.savepoint(): L.with_user(diger_u).atlas_haftalik(str(pzt), e.id); gordu = True
except AccessError: gordu = False
ok(not gordu, "başka çalışanın çizelgesi görüntülenemez")
try:
    with env.cr.savepoint(): hucre(25); fazla = True
except Exception: fazla = False
ok(not fazla, "24 saatten fazla girilemez")
vy = L.with_user(yonetici_u).atlas_haftalik(str(pzt), e.id)
ok(vy['onaylayici'] and vy['calisan']['id'] == e.id and vy['bekleyen_onay'] == 1 and not vy['kendi'], "onaylayıcı çalışanın haftasını görüyor")
sayi = L.with_user(yonetici_u).atlas_hafta_onayla(str(pzt), e.id)
kayit = L.search([('employee_id', '=', e.id), ('date', '=', pzt + timedelta(days=1))])
ok(sayi == 1 and kayit.atlas_onayli and kayit.atlas_onaylayan_id == yonetici_u and kayit.readonly_timesheet, "hafta onaylandı, kayıt kilitli")
try:
    with env.cr.savepoint(): kayit.with_user(calisan_u).write({'unit_amount': 9}); degisti = True
except UserError: degisti = False
ok(not degisti, "onaylı kayıt değiştirilemez")
try:
    with env.cr.savepoint(): kayit.with_user(yonetici_u).unlink(); silindi = True
except UserError: silindi = False
ok(not silindi, "onaylı kayıt yönetici tarafından da silinemez")
try:
    with env.cr.savepoint(): hucre(4, pzt + timedelta(days=1)); yazdi = True
except UserError: yazdi = False
ok(not yazdi, "tabloda onaylı hücre değiştirilemez")
try:
    with env.cr.savepoint(): kayit.with_user(calisan_u).action_atlas_onay_kaldir(); kaldirdi = True
except AccessError: kaldirdi = False
ok(not kaldirdi, "çalışan onayı kaldıramaz")
kayit.with_user(yonetici_u).action_atlas_onay_kaldir()
ok(not kayit.atlas_onayli and hucre(4, pzt + timedelta(days=1)).unit_amount == 4, "onay kaldırılınca düzenlenebildi")

# Sayaç
S = env['atlas.zaman.sayac'].with_user(calisan_u)
bilgi = S.atlas_baslat(False, gorev.id, 'Analiz')
sayac = S.browse(bilgi['id'])
ok(bilgi['project_id'] == proje.id and sayac.employee_id == e, "sayaç görevden başlatıldı (proje görevden)")
sayac.sudo().baslangic = fields.Datetime.now() - timedelta(minutes=7)
env.company.write({'atlas_zaman_yuvarlama': 15, 'atlas_zaman_minimum': 15})
sonuc = sayac.atlas_durdur()
yeni = L.browse(sonuc[0]['id'])
ok(yeni.unit_amount == 0.25 and yeni.name == 'Analiz' and yeni.task_id == gorev and not sayac.exists(), "7 dk → 15 dk'ya yuvarlandı (0,25 saat)")
b1 = S.atlas_baslat(proje.id); S.browse(b1['id']).sudo().baslangic = fields.Datetime.now() - timedelta(minutes=50)
S.atlas_baslat(proje.id, gorev.id)
ok(S.search_count([('user_id', '=', calisan_u.id)]) == 1 and L.search_count([('employee_id', '=', e.id), ('unit_amount', '=', 1.0), ('task_id', '=', False), ('date', '=', fields.Date.context_today(L))]) == 1,
   "yeni sayaç başlatınca önceki durdu ve 50 dk → 1 saat yazıldı")
ok(gorev.with_user(calisan_u).atlas_sayac_calisiyor, "görev formu: sayaç çalışıyor")
gorev.with_user(calisan_u).action_atlas_sayac_durdur()
ok(not S.search_count([('user_id', '=', calisan_u.id)]) and not gorev.with_user(calisan_u).atlas_sayac_calisiyor, "görevden durduruldu")
try:
    with env.cr.savepoint(): S.browse(S.with_user(diger_u).atlas_baslat(proje.id)['id']).atlas_durdur(); baskasi = True
except AccessError: baskasi = False
ok(not baskasi, "başkasının sayacı durdurulamaz")

# Hatırlatma
onceki = env['mail.mail'].search([], order='id desc', limit=1).id or 0
L._cron_atlas_hatirlatma()
mailler = env['mail.mail'].search([('id', '>', onceki)])
ok(any(calisan_u.partner_id in m.recipient_ids and 'eksik' in (m.subject or '') for m in mailler), "eksik kayıt hatırlatması gönderildi")
env.cr.rollback(); print("(geri alındı)")
