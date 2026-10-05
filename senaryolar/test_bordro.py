from datetime import date
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
yak = lambda a, b, t=0.02: abs((a or 0) - b) <= t
P = env['atlas.bordro.parametre']
p25 = P.search([('yil', '=', 2025)])
p26 = P.search([('yil', '=', 2026)])
ok(len(p25) == 2 and len(p26) == 1 and not p26.onaylandi and p25.filtered(lambda p: p.donem_bas == 7).kidem_tavan == 53919.68,
   "parametreler: 2025 (iki dönem) ve 2026 taslağı kuruldu")
ok(env.ref('atlas_bordro.kalem_avans').hesap_id.code.startswith('196'), "avans kesintisi 196 hesabına bağlı")
D = env['atlas.bordro.donem']
sirket = env.company
E = env['hr.employee']
def calisan(ad, brut, bas=date(2024, 1, 1), bitis=False, **kw):
    e = E.create(dict({'name': ad, 'identification_id': '12345678950', 'company_id': sirket.id}, **kw))
    e.version_id.write({'wage': brut, 'contract_date_start': bas, 'contract_date_end': bitis})
    return e
# Mevcut çalışanlar teste karışmasın: yalnız bu testin çalışanları dönemde olsun
E.search([('company_id', '=', sirket.id), ('name', 'not like', 'BRD %')]).write({'active': False})
asgari = calisan('BRD Asgari', 26005.50)
orta = calisan('BRD Orta', 50000)
yeni = calisan('BRD Ay İçi Giriş', 30000, bas=date(2025, 1, 16))
neti = calisan('BRD Net Anlaşma', 0, atlas_ucret_tipi='net', atlas_net_ucret=30000)
emekli = calisan('BRD Emekli', 40000, atlas_emekli=True)
yuksek = calisan('BRD Yüksek', 250000)
engelli = calisan('BRD Engelli', 40000, atlas_engelli_derece='2')
ocak = D.create({'yil': 2025, 'ay': '1'})
try:
    with env.cr.savepoint(): ocak.action_hesapla(); hesaplandi = True
except UserError as e: hesaplandi = False
ok(not hesaplandi, "kontrol edilmemiş parametreyle bordro hesaplanmaz")
p25.write({'onaylandi': True})
ocak.action_hesapla()
B = lambda e, d=ocak: d.bordro_ids.filtered(lambda b: b.employee_id == e)
ok(len(ocak.bordro_ids) == 7 and ocak.durum == 'hesaplandi', "7 çalışanın bordrosu hesaplandı")
a = B(asgari)
ok(yak(a.sgk_isci, 3640.77) and yak(a.issizlik_isci, 260.06) and a.gv == 0 and a.dv == 0 and yak(a.net, 22104.67),
   f"asgari ücret 2025: net 22.104,67 (hesaplanan {a.net})")
ok(yak(a.maliyet, 30621.48, 0.03) and yak(a.tesvik, 1300.28), f"asgari ücret işveren maliyeti ~30.621,48 ({a.maliyet})")
o = B(orta)
ok(yak(o.gv_matrah, 42500) and yak(o.gv_hesaplanan, 6375) and yak(o.gv_istisna, 3315.70) and yak(o.gv, 3059.30), f"50.000 brüt: GV 3.059,30 ({o.gv})")
ok(yak(o.dv, 182.12) and yak(o.net, 39258.58), f"50.000 brüt: DV 182,12, net 39.258,58 ({o.net})")
y = B(yeni)
ok(y.gun == 15 and y.giris_tarihi == date(2025, 1, 16) and yak(y.brut_ucret, 15000), f"16 Ocak girişi: 15 gün, 15.000 brüt ({y.gun})")
ok(yak(y.gv_istisna, min(y.gv_hesaplanan, 3315.70 * 15 / 30)), "ay içi girişte asgari ücret istisnası gün oranında")
n = B(neti)
ok(yak(n.net, 30000, 0.01) and n.aylik_brut > 30000, f"net anlaşma: 30.000 net için brüt {n.aylik_brut}")
em = B(emekli)
ok(yak(em.sgk_isci, 3000) and em.issizlik_isci == 0 and yak(em.sgk_isveren, 9900) and em.tesvik == 0, "emekli: SGDP %7,5 / %24,75, işsizlik yok")
yk = B(yuksek)
ok(yak(yk.sgk_matrah, 195041.25) and yak(yk.sgk_isci, 27305.78), f"SGK tavanı: matrah 195.041,25 ({yk.sgk_matrah})")
ok(yk.vergi_dilimi in (15.0, 20.0, 27.0), "vergi dilimi gösteriliyor")
en = B(engelli)
ok(yak(en.engelli_indirimi, 5700) and yak(en.gv_matrah, 40000 - 5600 - 400 - 5700), "engelli indirimi GV matrahından düşüldü")
# Ek ödeme ve kesintiler
o.write({'kalem_ids': [Command.create({'tur_id': env.ref('atlas_bordro.kalem_fazla_mesai').id, 'saat': 10}),
                       Command.create({'tur_id': env.ref('atlas_bordro.kalem_avans').id, 'tutar': 2000}),
                       Command.create({'tur_id': env.ref('atlas_bordro.kalem_yemek').id, 'tutar': 6000, 'gun': 22})]})
o.action_yeniden_hesapla()
fm = o.kalem_ids.filtered(lambda k: k.tur_id.saatlik)
ok(yak(fm.tutar, 3333.33), f"fazla mesai: 10 saat × 222,22 × 1,5 = 3.333,33 ({fm.tutar})")
ok(yak(o.brut_toplam, 50000 + 3333.33 + 6000) and yak(o.sgk_matrah, 50000 + 3333.33 + 6000 - 240 * 22), "yemek yardımında 22 × 240 istisna SGK'dan düşüldü")
ok(yak(o.kesinti, 2000) and yak(o.net, o.brut_toplam - o.sgk_isci - o.issizlik_isci - o.gv - o.dv - 2000), "avans kesintisi netten düşüldü")
# Ücretsiz izin
tur = env['hr.work.entry.type'].search([('atlas_ucretsiz', '=', True)], limit=1)
ok(tur and tur.atlas_eksik_gun_nedeni, "ücretsiz izin türü işaretli")
izin = env['hr.leave'].sudo().create({'employee_id': asgari.id, 'work_entry_type_id': tur.id, 'request_date_from': date(2025, 1, 13),
                                     'request_date_to': date(2025, 1, 15)})
izin.sudo().action_approve() if izin.state != 'validate' else None
if izin.state != 'validate':
    izin.sudo().write({'state': 'validate'})
a.action_yeniden_hesapla()
ok(a.gun == 27 and a.eksik_gun == 3 and a.eksik_gun_nedeni and yak(a.brut_ucret, 26005.50 * 27 / 30), f"3 gün ücretsiz izin: 27 prim günü ({a.gun})")
# Onay ve muhasebe
ocak.action_onayla()
fis = ocak.move_id
ok(ocak.durum == 'onaylandi' and fis.state == 'posted' and fis.amount_total > 0, "onay: muhasebe fişi işlendi")
kod = lambda k: sum(fis.line_ids.filtered(lambda l: l.account_id.code.startswith(k)).mapped('balance'))
ok(yak(-kod('335'), sum(ocak.bordro_ids.mapped('net'))) and yak(-kod('196'), 2000)
   and yak(-kod('360'), sum(ocak.bordro_ids.mapped('gv')) + sum(ocak.bordro_ids.mapped('dv'))), "fiş: 335 net, 196 avans, 360 vergiler")
ok(yak(kod('770'), sum(ocak.bordro_ids.mapped('maliyet'))) and yak(-kod('361'), ocak.toplam_sgk), "fiş: 770 toplam maliyet, 361 SGK")
# Kümülatif matrah (Şubat–Nisan)
sonuncu = ocak
for ay in ('2', '3', '4'):
    d = D.create({'yil': 2025, 'ay': ay})
    d.action_hesapla()
    sonuncu = d
nisan = B(orta, sonuncu)
ok(yak(nisan.kumulatif_onceki, o.gv_matrah + 42500 * 2) and nisan.kumulatif > 158000, f"nisan: kümülatif {nisan.kumulatif} (dilim aşımı)")
beklenen = (158000 - nisan.kumulatif_onceki) * 0.15 + (nisan.kumulatif - 158000) * 0.20
ok(yak(nisan.gv_hesaplanan, beklenen) and nisan.vergi_dilimi == 20, f"dilim geçişinde GV {beklenen:.2f}")
try:
    with env.cr.savepoint(): ocak.action_taslaga_al(); geri = True
except UserError: geri = False
ok(geri, "ocak taslağa alınabildi (sonraki aylar onaylı değil)")
ocak.action_hesapla(); ocak.action_onayla()
sonuncu.action_onayla()
try:
    with env.cr.savepoint(): ocak.action_taslaga_al(); geri = True
except UserError: geri = False
ok(not geri, "sonraki ay onaylıyken önceki ay taslağa alınamaz")
# Çıktılar
r = ocak.action_banka_listesi()
s = ocak.action_sgk_listesi()
ok(r['url'].startswith('/web/content/') and s['url'].startswith('/web/content/'), "banka ve SGK/MUHSGK listeleri")
pdf, _ = env['ir.actions.report']._render_qweb_pdf('atlas_bordro.action_report_pusula', ocak.bordro_ids[:2].ids)
ok(pdf[:4] == b'%PDF', "ücret pusulası PDF")
# Kıdem / ihbar
K = env['atlas.bordro.kidem'].create({'employee_id': orta.id, 'giris_tarihi': date(2022, 4, 1), 'cikis_tarihi': date(2025, 5, 31),
                                      'giydirilmis_brut': 60000, 'ihbar_hakki': True, 'kullanilmayan_izin_gun': 5})
gunler = (date(2025, 5, 31) - date(2022, 4, 1)).days + 1
ok(K.hizmet_yil == 3 and yak(K.kidem_esas, 46655.43) and yak(K.kidem_brut, 46655.43 * gunler / 365, 0.05), f"kıdem: tavanla {K.kidem_brut}")
ok(yak(K.kidem_net, K.kidem_brut - K.kidem_brut * 0.00759, 0.02) and K.ihbar_hafta == 8 and yak(K.ihbar_brut, 2000 * 56), "kıdemde yalnız DV; 3+ yılda 8 hafta ihbar")
ok(K.ihbar_gv > 0 and yak(K.izin_brut, 10000) and K.toplam_net > 0, "ihbar ve izin ücreti GV/DV'ye tabi")
K2 = env['atlas.bordro.kidem'].create({'employee_id': yeni.id, 'giris_tarihi': date(2025, 1, 16), 'cikis_tarihi': date(2025, 6, 30), 'giydirilmis_brut': 30000})
ok(K2.kidem_brut == 0 and K2.uyari, "1 yıldan az: kıdem yok, uyarı")
env.cr.rollback(); print("(geri alındı)")
