import base64
from datetime import timedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
U = env['res.users'].with_context(no_reset_password=True)
gruplar = ['base.group_user', 'sales_team.group_sale_salesman', 'stock.group_stock_user', 'hr_expense.group_hr_expense_user',
           'hr_attendance.group_hr_attendance_officer', 'hr_holidays.group_hr_holidays_employee']
satici = U.create({'name': 'MOB Satıcı', 'login': 'mob_satici', 'email': 'mob@ornek.com',
                   'group_ids': [Command.set([env.ref(g).id for g in gruplar if env.ref(g, raise_if_not_found=False)])]})
yonetici = U.create({'name': 'MOB Yönetici', 'login': 'mob_yonetici', 'email': 'mobyon@ornek.com',
                     'group_ids': [Command.set([env.ref('base.group_user').id, env.ref('hr_expense.group_hr_expense_team_approver').id])]})
e_yon = env['hr.employee'].create({'name': 'MOB Yönetici', 'user_id': yonetici.id})
e_sat = env['hr.employee'].create({'name': 'MOB Satıcı', 'user_id': satici.id, 'parent_id': e_yon.id, 'expense_manager_id': yonetici.id})
M = env['atlas.mobil'].with_user(satici)

p = M.profil()
ok(p['ad'] == 'MOB Satıcı' and p['calisan_id'] == e_sat.id and p['moduller']['satis'] and p['moduller']['masraf'],
   "profil: çalışan ve modül yetkileri")
ok(not env['atlas.mobil'].with_user(yonetici).profil()['moduller']['satis'], "satış yetkisi olmayana satış modülü kapalı")

# Cari + ürün
c = M.cari_olustur('MOB Test Ticaret A.Ş.', telefon='+90 212 000 00 00', sehir='İstanbul')
ok(c['id'] and any(x['id'] == c['id'] for x in M.cari_ara('MOB Test')), "cari oluşturuldu ve aranıyor")
try:
    with env.cr.savepoint(): M.cari_olustur('  '); bos = True
except UserError: bos = False
ok(not bos, "boş adla cari oluşturulamaz")
urun = env['product.product'].create({'name': 'MOB Kablo', 'default_code': 'MOB-1', 'list_price': 125.0, 'is_storable': True,
                                      'barcode': 'MOB0001'})
ok(M.urun_ara('MOB0001')[0]['id'] == urun.id and M.urun_ara('MOB-1')[0]['stok'] == 0, "ürün barkod/kodla bulunuyor, stok dönüyor")
ok(M.urun_detay(urun.id)['fiyat'] == 125.0, "ürün detayı")

# Satış
s = M.satis_olustur(c['id'], [{'urun_id': urun.id, 'miktar': 4}, {'urun_id': urun.id, 'miktar': 1, 'fiyat': 100.0, 'indirim': 10}],
                    not_metni='Mobil teklif')
ok(s['durum'] == 'draft' and len(s['satirlar']) == 2 and s['satirlar'][0]['fiyat'] > 0 and s['satirlar'][1]['fiyat'] == 100.0,
   "teklif oluşturuldu, fiyat listesi fiyatı ve elle girilen fiyat korunuyor")
ok(round(s['ara_toplam'], 2) == round(s['satirlar'][0]['tutar'] + 90.0, 2), "elle fiyatlı satırda %10 indirim uygulandı")
ok(any(x['id'] == s['id'] for x in M.satis_listesi(filtre='teklif')), "teklif listesinde")
s2 = M.satis_onayla(s['id'])
ok(s2['durum'] == 'sale' and not s2['onaylanabilir'] and s2['teslimatlar'], "teklif mobilden onaylandı, teslimat oluştu")
ozet = M.ozet()
ok(ozet['satis']['bu_ay'] > 0 and len(ozet['satis']['seri']) == 7 and ozet['satis']['bugun'] > 0,
   "ana sayfa satış göstergesi ve 7 günlük seri")
ok('depo' in ozet and ozet['depo']['sevkiyat'] >= 1, "ana sayfa depo sayıları")
cd = M.cari_detay(c['id'])
ok(cd['siparisler'] and cd['siparisler'][0]['id'] == s['id'], "cari detayında son siparişler")

# CRM
f = M.crm_olustur('MOB Fırsat', partner_id=c['id'], gelir=50000)
hat = M.crm_hat()
ok(any(fr['id'] == f['id'] for a in hat for fr in a['firsatlar']), "fırsat hattında")
ikinci = next(a for a in hat if a['id'] != f['asama_id'] and not a['kazanildi'])
ok(len(M.crm_asamalar()) == len(hat), "aşama listesi")
ok(M.crm_asama(f['id'], ikinci['id'])['asama_id'] == ikinci['id'], "fırsat aşaması değişti")
ok(M.crm_kazanildi(f['id'])['olasilik'] == 100, "fırsat kazanıldı")
M.not_ekle('crm.lead', f['id'], 'Mobilden not')
ok(any('Mobilden not' in m['metin'] for m in M.crm_detay(f['id'])['mesajlar']), "fırsata not eklendi")

# Aktivite
lead = env['crm.lead'].browse(f['id'])
act = lead.activity_schedule('mail.mail_activity_data_todo', summary='MOB arama', user_id=satici.id,
                             date_deadline=fields.Date.today())
ok(M.rozetler()['aktivite'] >= 1 and any(a['id'] == act.id for a in M.aktiviteler()), "aktivite listede ve rozette")
M.aktivite_tamamla(act.id, 'Arandı')
ok(not act.exists() or not act.active, "aktivite tamamlandı")

# Onay merkezi: Atlas onay talebi
kat = env['atlas.onay.kategori'].create({'name': 'MOB Avans', 'alan_tutar': 'zorunlu',
                                         'onaylayici_ids': [Command.create({'user_id': yonetici.id})]})
t = M.onay_talep_olustur(kat.id, 'Saha avansı', tutar=2500)
Y = env['atlas.onay.mobil'] if 'atlas.onay.mobil' in env else env['atlas.mobil'].with_user(yonetici)
liste = Y.onay_listesi()
ok(any(i['kaynak'] == 'onay' and i['id'] == t['id'] for i in liste), "onaylayıcının onay merkezinde talep var")
d = Y.onay_detay('onay', t['id'])
ok(d['karar_verebilir'] and d['tutar'] == 2500, "talep detayı: karar verebilir")
ok(not M.onay_detay('onay', t['id'])['karar_verebilir'], "talep eden karar veremez")
Y.onay_ver('onay', t['id'], 'Uygun')
ok(env['atlas.onay.talep'].browse(t['id']).durum == 'onaylandi', "mobilden onaylandı")
ok(M.onay_taleplerim()[0]['durum'] == 'onaylandi', "taleplerim listesinde sonuç")

# Masraf (fiş fotoğrafıyla) + yönetici onayı
masraf_urun = env['product.product'].search([('can_be_expensed', '=', True)], limit=1)
fis = base64.b64encode(b'\xff\xd8\xff\xe0' + b'0' * 64).decode()
mr = M.masraf_olustur('Taksi', 340.5, urun_id=masraf_urun.id, fis_b64=fis, fis_adi='taksi.jpg', gonder=True)
ok(mr['tutar'] == 340.5 and mr['ek'] == 1, f"masraf tutarı korunuyor ve fiş eklendi ({mr['tutar']}, ek={mr['ek']})")
ok(mr['durum'] == 'submitted', f"masraf onaya gönderildi ({mr['durum']})")
ok(any(i['kaynak'] == 'masraf' and i['id'] == mr['id'] for i in Y.onay_listesi()), "masraf yöneticinin onay merkezinde")
Y.onay_ver('masraf', mr['id'])
ok(env['hr.expense'].browse(mr['id']).state == 'approved', "masraf mobilden onaylandı")
try:
    with env.cr.savepoint(): M.masraf_olustur('Otopark', 50); urunsuz = True
except UserError: urunsuz = False
ok(not urunsuz, "kategorisiz masraf anlaşılır hatayla reddedilir")
mr2 = M.masraf_olustur('Otopark', 50, urun_id=masraf_urun.id, gonder=True)
Y.onay_reddet('masraf', mr2['id'], 'Fiş yok')
ok(env['hr.expense'].browse(mr2['id']).state == 'refused', "masraf nedenle reddedildi")

# Giriş / çıkış
d0 = M.devam_degistir(41.0082, 28.9784, 'İstanbul')
att = env['hr.attendance'].search([('employee_id', '=', e_sat.id)], limit=1)
ok(d0['durum'] == 'checked_in' and d0['giris'] and round(att.in_latitude, 4) == 41.0082 and att.in_location == 'İstanbul',
   "konumlu giriş yapıldı")
att.check_in = fields.Datetime.now() - timedelta(hours=2)
d1 = M.devam_degistir(41.0, 29.0)
ok(d1['durum'] == 'checked_out' and d1['bugun_saat'] >= 1.9, f"çıkış yapıldı, bugün {d1['bugun_saat']} saat")
ok(len(M.devam_gecmis()) == 1, "devam geçmişi")

# İzin
turler = M.izin_turleri()
serbest = [x for x in turler if not x['tahsis']]
if serbest:
    bas = fields.Date.today() + timedelta(days=30)
    while bas.weekday() >= 5:
        bas += timedelta(days=1)
    iz = M.izin_olustur(serbest[0]['id'], str(bas), str(bas), 'Mobil izin')
    ok(iz['durum'] in ('confirm', 'validate'), f"izin talebi oluştu ({iz['durum']}, {iz['sure']})")
    ok(M.izin_listesi()[0]['id'] == iz['id'], "izin listesinde")
else:
    ok(True, "tahsissiz izin türü yok (izin testi atlandı)")

# Depo: atlas.barkod mobil kullanıcı yetkisiyle
B = env['atlas.barkod'].with_user(satici)
ok(isinstance(B.ana_ekran()['sevkiyat'], int), "barkod ana ekranı mobil kullanıcıyla çalışıyor")

env.cr.rollback()
