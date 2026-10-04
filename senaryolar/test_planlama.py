from datetime import date, datetime, timedelta
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k)
        return None
    except UserError as e: return str(e)
env.user.tz = 'Europe/Istanbul'
V = env['atlas.planlama.vardiya']; E = env['hr.employee']
sabah = env.ref('atlas_planlama.sablon_sabah'); montaj = env.ref('atlas_planlama.rol_montaj')
kullanici = env['res.users'].create({'name': 'Plan Çalışan', 'login': 'plan_calisan_test', 'email': 'plan@test.local',
                                     'group_ids': [Command.set([env.ref('base.group_user').id])]})
ali = E.create({'name': 'PLN Ali', 'user_id': kullanici.id, 'job_title': 'Montajcı'})
ayse = E.create({'name': 'PLN Ayşe'})
montaj.employee_ids = [Command.link(ali.id)]
pzt = date(2026, 11, 2)
vid = V.hizli_olustur(ali.id, str(pzt), sabah.id); v1 = V.browse(vid)
ok(v1.baslangic == datetime(2026, 11, 2, 5, 0) and v1.bitis == datetime(2026, 11, 2, 13, 0) and v1.planlanan_saat == 7.5 and v1.rol_id == montaj,
   f"şablondan vardiya: {v1.name} (UTC {v1.baslangic:%H:%M}), 7,5 saat, rol çalışandan")
v2 = V.browse(V.hizli_olustur(ali.id, str(pzt), sabah.id))
ok(v1.cakisma and v2.cakisma and 'başka vardiyası' in v2.uyari, "aynı saatte ikinci vardiya: çakışma uyarısı")
v2.unlink(); v1.invalidate_recordset()
ok(not v1.cakisma, "çakışan silinince uyarı kalktı")
if 'hr.leave' in env:
    tip = env['hr.work.entry.type'].create({'name': 'PLN Mazeret', 'code': 'PLNMZ', 'requires_allocation': False, 'leave_validation_type': 'no_validation'})
    izin = env['hr.leave'].create({'name': 'izin', 'employee_id': ayse.id, 'work_entry_type_id': tip.id,
        'request_date_from': pzt + timedelta(days=1), 'request_date_to': pzt + timedelta(days=1)})
    if izin.state != 'validate':
        izin.sudo().action_approve() if hasattr(izin, 'action_approve') else None
    v3 = V.browse(V.hizli_olustur(ayse.id, str(pzt + timedelta(days=1)), sabah.id))
    ok(izin.state == 'validate' and v3.izinli and 'izni' in v3.uyari, f"izinli güne vardiya: uyarı ({izin.state})")
    v3.unlink()
acik = V.browse(V.hizli_olustur(False, str(pzt + timedelta(days=2)), env.ref('atlas_planlama.sablon_aksam').id))
ok(not acik.employee_id and acik.planlanan_saat == 7.5, "açık (atanmamış) vardiya")
h = V.hafta_verisi(str(pzt + timedelta(days=3)))
satir = {s['ad']: s for s in h['satirlar']}
ok(h['hafta_basi'] == '2026-11-02' and len(h['gunler']) == 7 and h['gunler'][0]['ad'] == 'Pzt 02.11', f"hafta: {h['baslik']}")
ok(satir['PLN Ali']['gunler'][0][0]['saat'] == '08:00-16:00' and satir['Açık vardiyalar']['gunler'][2][0]['saat'] == '16:00-00:00', "kartlar yerel saatle doğru güne yerleşti")
ok('PLN Ayşe' not in satir or satir['PLN Ayşe']['izinli'] == [1] if 'hr.leave' in env else True, "izin günü işaretli")
ok(h['taslak_sayisi'] == 2 and h['yonetici'], "taslak sayısı 2")
V.browse(vid).tasi(ayse.id, str(pzt + timedelta(days=3)))
ok(v1.employee_id == ayse and v1.baslangic == datetime(2026, 11, 5, 5, 0), "sürükle-bırak: Ayşe'ye perşembe 08:00")
v1.tasi(ali.id, str(pzt))
mesaj_once = env['mail.message'].search_count([('partner_ids', 'in', kullanici.partner_id.ids)])
m = V.hafta_yayinla(str(pzt))
ok(v1.durum == 'yayinlandi' and acik.durum == 'taslak' and 'açık vardiya' in m, f"yayınla: {m}")
ok(env['mail.message'].search_count([('partner_ids', 'in', kullanici.partner_id.ids)]) > mesaj_once, "çalışana bildirim gitti")
Vk = V.with_user(kullanici)
ok(Vk.search([('baslangic', '>=', datetime(2026, 11, 2))]) == v1 and hata(Vk.hizli_olustur, ali.id, str(pzt), sabah.id) is not None,
   "çalışan yalnızca yayınlananı görür, vardiya oluşturamaz")
ok([s['ad'] for s in Vk.hafta_verisi(str(pzt))['satirlar'] if any(s['gunler'])] == ['PLN Ali'], "çalışanın haftalık planında taslak/açık vardiya yok")
m = V.onceki_haftayi_kopyala(str(pzt + timedelta(days=7)))
kopya = V.search([('baslangic', '>=', datetime(2026, 11, 9)), ('baslangic', '<', datetime(2026, 11, 16))])
ok(len(kopya) == 2 and all(k.durum == 'taslak' for k in kopya) and '2' in m, f"önceki haftayı kopyala: {m}")
ok('0' in V.onceki_haftayi_kopyala(str(pzt + timedelta(days=7))), "ikinci kopyalamada tekrar oluşturmadı")
cuma = V.browse(V.hizli_olustur(ayse.id, str(pzt + timedelta(days=11)), sabah.id))
w = env['atlas.planlama.tekrar.wizard'].create({'vardiya_ids': [Command.set(cuma.ids)], 'aralik': 'is_gunleri', 'adet': 4})
w.action_tekrarla()
gunler = sorted(V._yerel(x.baslangic).date() for x in V.search([('employee_id', '=', ayse.id), ('baslangic', '>', cuma.baslangic)]))
ok(gunler == [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)], f"hafta içi tekrar: {[g.strftime('%a %d') for g in gunler]}")

wc = env['mrp.workcenter'].create({'name': 'PLN Montaj Hattı', 'code': 'PLNM'})
V.create({'employee_id': ali.id, 'workcenter_id': wc.id, 'baslangic': datetime(2026, 11, 3, 5), 'bitis': datetime(2026, 11, 3, 13), 'mola_dk': 30})
urun = env['product.product'].create({'name': 'PLN Ürün', 'is_storable': True})
bom = env['mrp.bom'].create({'product_tmpl_id': urun.product_tmpl_id.id, 'operation_ids': [Command.create({'name': 'Montaj', 'workcenter_id': wc.id, 'time_cycle_manual': 600})]})
mo = env['mrp.production'].create({'product_id': urun.id, 'product_qty': 1, 'bom_id': bom.id}); mo.action_confirm()
mo.workorder_ids.write({'date_start': datetime(2026, 11, 3, 6), 'date_finished': datetime(2026, 11, 3, 16)})
d = V.doluluk_verisi(str(pzt))
hat = [s for s in d['satirlar'] if s['id'] == wc.id][0]['gunler'][1]
ok(hat['kapasite'] == 7.5 and hat['yuk'] == 10 and hat['durum'] == 'asiri' and hat['oran'] == 133, f"iş merkezi doluluğu salı: {hat['yuk']} / {hat['kapasite']} sa (%{hat['oran']})")
env.cr.rollback(); print("(geri alındı)")
