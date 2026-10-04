from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k)
        return None
    except (UserError, ValidationError) as e: return str(e)
c = env.company; c.write({'atlas_mps_periyot': 'ay', 'atlas_mps_periyot_sayisi': 6, 'atlas_mps_talep': 'en_buyuk'})
M = env['atlas.mps']; Prod = env['product.product']; wh = env['stock.warehouse'].search([('company_id', '=', c.id)], limit=1)
cat = lambda x: env.ref(f'atlas_stok.categ_{x}')
ted = env['res.partner'].create({'name': 'MPS Tedarikçi', 'is_company': True})
vida = Prod.create({'name': 'MPS Vida', 'is_storable': True, 'categ_id': cat('ilk_madde').id, 'seller_ids': [Command.create({'partner_id': ted.id, 'price': 1})]})
kasa = Prod.create({'name': 'MPS Kasa', 'is_storable': True, 'categ_id': cat('ilk_madde').id})
kombi = Prod.create({'name': 'MPS Kombi', 'is_storable': True, 'tracking': False, 'categ_id': cat('mamul').id})
bom = env['mrp.bom'].create({'product_tmpl_id': kombi.product_tmpl_id.id, 'product_qty': 1,
    'bom_line_ids': [Command.create({'product_id': vida.id, 'product_qty': 2}), Command.create({'product_id': kasa.id, 'product_qty': 1})]})
pk = M.create({'product_id': kombi.id, 'warehouse_id': wh.id, 'guvenlik_stok': 5, 'min_ikmal': 10})
pv = M.create({'product_id': vida.id, 'warehouse_id': wh.id, 'guvenlik_stok': 20})
ok(pk.tedarik == 'uretim' and pk.bom_id == bom and pv.tedarik == 'satinalma', "tedarik tipi reçeteden: kombi üretim, vida satınalma")
try:
    with env.cr.savepoint(): M.create({'product_id': kombi.id, 'warehouse_id': wh.id}); env.flush_all(); cift = False
except Exception: cift = True
ok(cift, "aynı depo/ürün için ikinci plan reddedildi")
per = M._periyotlar(c)
ok(len(per) == 6 and per[0][0].day == 1 and per[0][0] <= per[0][1], f"aylık 6 dönem: {[p[2] for p in per]}")
pk.tahmin_yaz(str(per[0][0]), 'tahmini_talep', 30); pk.tahmin_yaz(str(per[1][0]), 'tahmini_talep', 20)
h = (pk | pv)._hesapla()
k0, k1 = h[pk.id][0], h[pk.id][1]
ok(k0['ikmal'] == 35 and k0['stok_sonu'] == 5 and k1['ikmal'] == 20 and k1['stok_sonu'] == 5, f"kombi öneri: {k0['ikmal']}, {k1['ikmal']} (güvenlik stoğu 5)")
ok(h[pk.id][2]['ikmal'] == 0 and h[pk.id][2]['durum'] == 'yeterli', "talep olmayan dönemde öneri yok")
v0 = h[pv.id][0]
ok(v0['dolayli_talep'] == 70 and v0['ikmal'] == 90 and h[pv.id][1]['dolayli_talep'] == 40, f"vida dolaylı talep {v0['dolayli_talep']} (35 kombi × 2), öneri {v0['ikmal']}")
mus = env['res.partner'].create({'name': 'MPS Müşteri', 'is_company': True})
so = env['sale.order'].create({'partner_id': mus.id, 'order_line': [Command.create({'product_id': kombi.id, 'product_uom_qty': 40, 'price_unit': 1, 'tax_ids': False})]})
so.action_confirm()
k0 = pk._hesapla()[pk.id][0]
ok(k0['gercek_talep'] == 40 and k0['ikmal'] == 45, f"onaylı satış 40 > tahmin 30 → öneri {k0['ikmal']}")
c.atlas_mps_talep = 'tahmin'
ok(pk._hesapla()[pk.id][0]['ikmal'] == 35, "talep hesabı 'yalnızca tahmin' → 35")
c.atlas_mps_talep = 'en_buyuk'

r = pk.siparis_ver()
mo = env['mrp.production'].search([('product_id', '=', kombi.id), ('origin', '=', 'MPS')])
ok(r['sonuc'] == 'ok' and len(mo) == 1 and mo.product_qty == 45 and mo.state == 'confirmed' and mo.bom_id == bom, f"üretim emri oluştu: {mo.name} 45 adet")
h = (pk | pv)._hesapla()
ok(h[pk.id][0]['gelen'] == 45 and h[pk.id][0]['ikmal'] == 0, "sipariş sonrası kombi: onaylı ikmal 45, yeni öneri yok")
v0 = h[pv.id][0]
ok(v0['gercek_talep'] == 90 and v0['dolayli_talep'] == 0 and v0['ikmal'] == 110, f"vida: üretim emri tüketimi gerçek talep 90, öneri {v0['ikmal']}")
r = pv.siparis_ver()
pol = env['purchase.order.line'].search([('product_id', '=', vida.id), ('order_id.state', '=', 'draft')])
ok(r['sonuc'] == 'ok' and pol.product_qty == 110 and pol.partner_id == ted, f"satınalma teklifi: {pol.order_id.name} 110 vida")
ok(pv._hesapla()[pv.id][0]['ikmal'] == 0 and pv._hesapla()[pv.id][0]['gelen'] == 110, "teklif onaylı ikmale sayıldı, öneri sıfırlandı")
ok(pk.siparis_ver()['sonuc'] == 'uyari', "öneri yokken sipariş: uyarı")

pk.tahmin_yaz(str(per[2][0]), 'ikmal_miktar', 50)
d2 = pk._hesapla()[pk.id][2]
ok(d2['ikmal'] == 50 and d2['ikmal_elle'] and d2['durum'] == 'fazla', "elle ikmal 50 (ihtiyaç yokken) → fazla")
pk.oneriye_don(str(per[2][0]))
ok(pk._hesapla()[pk.id][2]['ikmal'] == 0, "öneriye dönüldü")
pk.max_ikmal = 10
pk.tahmin_yaz(str(per[3][0]), 'tahmini_talep', 40)
d3 = pk._hesapla()[pk.id][3]
ok(d3['ikmal'] == 10 and d3['durum'] == 'eksik', f"en çok ikmal 10 → dönem sonu eksik ({d3['stok_sonu']})")
pk.max_ikmal = 0
pk.tahmin_yaz(str(per[1][0]), 'ikmal_miktar', 25)
r = pk.siparis_ver(str(per[1][0]))
mo2 = env['mrp.production'].search([('product_id', '=', kombi.id), ('origin', '=', 'MPS')]) - mo
ok(len(mo2) == 1 and mo2.product_qty == 25 and mo2.date_finished.date() >= per[1][0], f"ileri dönem siparişi: {mo2.name} 25 adet, {mo2.date_finished.date()}")
ok(not pk._tahmin_haritasi(per)[1].ikmal_elle, "sipariş sonrası elle değer temizlendi")

kasa_plan = M.create({'product_id': kasa.id, 'warehouse_id': wh.id, 'ikmal_tetik': 'otomatik'})
ok('tedarikçi' in (hata(kasa_plan.siparis_ver) or ''), "tedarikçisi olmayan ürün için sipariş reddedildi")
kasa.seller_ids = [Command.create({'partner_id': ted.id, 'price': 3})]
M._cron_otomatik_ikmal()
kpol = env['purchase.order.line'].search([('product_id', '=', kasa.id)])
ok(kpol and kpol.product_qty == 45, f"otomatik ikmal görevi kasa teklifi açtı: {kpol.product_qty}")

ekran = M.ekran_verisi(wh.id)
ok(len(ekran['periyotlar']) == 6 and {s['id'] for s in ekran['satirlar']} >= {pk.id, pv.id} and ekran['yonetici'], "ekran verisi")
c.atlas_mps_periyot = 'hafta'; c.atlas_mps_periyot_sayisi = 8
pw = M._periyotlar(c)
ok(len(pw) == 8 and pw[0][0].weekday() == 0 and 'Hf' in pw[0][2], f"haftalık dönemler: {pw[0][2]} ...")
ok(len(M.ekran_verisi()['satirlar'][0]['donemler']) == 8, "ekran haftalık dönemle hesaplandı")
env.cr.rollback(); print("(geri alındı)")
