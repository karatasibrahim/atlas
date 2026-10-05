from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
yakin = lambda a, b: abs(a - b) < 0.01
P = env['atlas.komisyon.plan']
satis = env.ref('sales_team.group_sale_salesman')
s1 = env['res.users'].create({'name': 'Temsilci Bir', 'login': 'kom_s1', 'group_ids': [(6, 0, [satis.id])]})
s2 = env['res.users'].create({'name': 'Temsilci İki', 'login': 'kom_s2', 'group_ids': [(6, 0, [satis.id])]})
musteri = env['res.partner'].create({'name': 'Komisyon Müşterisi'})
kat = env['product.category'].create({'name': 'Komisyonlu Kategori'})
alt_kat = env['product.category'].create({'name': 'Alt Kategori', 'parent_id': kat.id})
urun_a = env['product.product'].create({'name': 'Ürün A', 'list_price': 1000, 'categ_id': alt_kat.id, 'type': 'service', 'invoice_policy': 'order'})
urun_b = env['product.product'].create({'name': 'Ürün B', 'list_price': 500, 'type': 'service', 'invoice_policy': 'order'})
ekip = env['crm.team'].create({'name': 'Kurumsal Satış', 'member_ids': [(6, 0, [s1.id])]})
bugun = fields.Date.today()
ay_bas = bugun.replace(day=1)
yerel_liste = env['product.pricelist'].create({'name': 'Şirket para birimi', 'currency_id': env.company.currency_id.id})


def siparis(kullanici, satirlar, team=False):
    so = env['sale.order'].create({'partner_id': musteri.id, 'user_id': kullanici.id, 'team_id': team.id if team else False,
                                   'pricelist_id': yerel_liste.id,
                                   'order_line': [(0, 0, {'product_id': u.id, 'product_uom_qty': m, 'price_unit': f, 'tax_ids': [(5, 0, 0)]})
                                                  for u, m, f in satirlar]})
    so.action_confirm()
    return so


so1 = siparis(s1, [(urun_a, 10, 1000), (urun_b, 4, 500)])      # 10.000 + 2.000
so2 = siparis(s2, [(urun_b, 10, 500)])                          # 5.000
taslak = env['sale.order'].create({'partner_id': musteri.id, 'user_id': s1.id, 'pricelist_id': yerel_liste.id, 'order_line': [(0, 0, {'product_id': urun_a.id, 'price_unit': 99999})]})

# ---------------------------------------------------------------- başarı bazlı (satış tutarı)
plan = P.create({'name': 'Satış Primi', 'bas': bugun.replace(month=1, day=1), 'bit': bugun.replace(month=12, day=31), 'periyot': 'ay',
                 'basari_ids': [(0, 0, {'tip': 'satis_tutar', 'oran': 5.0})],
                 'uye_ids': [(0, 0, {'user_id': s1.id}), (0, 0, {'user_id': s2.id})]})
ok(len(plan._donemler()) == 12 and plan._donemler()[0][2] == f'Ocak {bugun.year}', "aylık dönemler")
plan.action_onayla()
r1 = plan.sonuc_ids.filtered(lambda r: r.user_id == s1 and r.donem_bas == ay_bas)
r2 = plan.sonuc_ids.filtered(lambda r: r.user_id == s2 and r.donem_bas == ay_bas)
ok(plan.durum == 'onayli' and len(plan.sonuc_ids) == 24, "onay: her temsilci × dönem için sonuç")
ok(yakin(r1.komisyon, 600) and yakin(r2.komisyon, 250), "satış tutarının %5'i (taslak sipariş sayılmaz)")
ok(len(r1.satir_ids) == 2 and set(r1.satir_ids.mapped('belge')) == {so1.name}, "ayrıntı satırları kaynak siparişe bağlı")
ok(yakin(sum(plan.sonuc_ids.filtered(lambda r: r.donem_bas != ay_bas).mapped('komisyon')), 0), "diğer aylarda komisyon yok")

# ürün kategorisi ve miktar kuralları
plan.action_taslak()
ok(not plan.sonuc_ids and plan.durum == 'taslak', "taslağa alınınca sonuçlar silinir")
plan.basari_ids = [(0, 0, {'tip': 'satis_tutar', 'kategori_id': kat.id, 'oran': 2.0}), (0, 0, {'tip': 'satis_miktar', 'urun_id': urun_b.id, 'oran': 10.0})]
plan.action_onayla()
r1 = plan.sonuc_ids.filtered(lambda r: r.user_id == s1 and r.donem_bas == ay_bas)
ok(yakin(r1.komisyon, 600 + 200 + 40), "alt kategori dahil kategori kuralı (%2) ve birim başına tutar (4 × 10)")

# ---------------------------------------------------------------- fatura bazlı, iade düşer
fatura = so1._create_invoices()
fatura.action_post()
iade = fatura._reverse_moves([{'invoice_date': bugun, 'invoice_user_id': fatura.invoice_user_id.id}])  # iade sihirbazı gibi
iade.invoice_line_ids.filtered(lambda l: l.product_id == urun_a).quantity = 2
iade.invoice_line_ids.filtered(lambda l: l.product_id == urun_b).unlink()
iade.action_post()
fplan = P.create({'name': 'Tahsilat Primi', 'bas': ay_bas, 'bit': bugun.replace(month=12, day=31), 'periyot': 'ceyrek',
                  'basari_ids': [(0, 0, {'tip': 'fatura_tutar', 'oran': 3.0}), (0, 0, {'tip': 'fatura_miktar', 'urun_id': urun_a.id, 'oran': 1.0})],
                  'uye_ids': [(0, 0, {'user_id': s1.id})]})
ok(fplan._donemler()[0][0] == ay_bas and '' not in [d[2] for d in fplan._donemler()], "çeyrek dönemler plan başına kırpılır")
fplan.action_onayla()
fr = fplan.sonuc_ids.filtered(lambda r: r.donem_bas <= bugun <= r.donem_bit)
ok(yakin(fr.basari, (12000 - 2000) * 0.03 + (10 - 2) * 1.0), "faturalanan tutar %3, iade düşüldü; faturalanan miktar")

# ---------------------------------------------------------------- hedef bazlı, kademeler, düzeltme
hplan = P.create({'name': 'Hedef Primi', 'bas': ay_bas, 'bit': ay_bas.replace(day=28), 'periyot': 'ay', 'tur': 'hedef', 'hedef_komisyon': 1000,
                  'basari_ids': [(0, 0, {'tip': 'satis_tutar', 'oran': 100.0})],
                  'uye_ids': [(0, 0, {'user_id': s1.id}), (0, 0, {'user_id': s2.id})]})
hplan.action_hedefleri_olustur()
hplan.hedef_ids.tutar = 10000
hplan.action_kademe_varsayilan()
ok([(k.oran, k.tutar) for k in hplan.kademe_ids] == [(0.5, 0), (1.0, 1000), (1.5, 1800)], "varsayılan kademeler")
env['atlas.komisyon.duzeltme'].create({'name': 'Kampanya primi', 'plan_id': hplan.id, 'user_id': s2.id, 'tarih': bugun, 'tutar': 3000})
hplan.action_onayla()
h1 = hplan.sonuc_ids.filtered(lambda r: r.user_id == s1)
h2 = hplan.sonuc_ids.filtered(lambda r: r.user_id == s2)
ok(yakin(h1.gerceklesme, 120) and yakin(h1.komisyon, 1000 + 800 * 0.2 / 0.5), "hedefin %120'si: kademeler arası doğrusal")
ok(yakin(h2.basari, 8000) and yakin(h2.komisyon, 1000 * 0.3 / 0.5) and 'duzeltme' in h2.satir_ids.mapped('kaynak'), "düzeltme başarıya eklenir (%80)")
ok(yakin(hplan._kademe_komisyon(0.4), 0) and yakin(hplan._kademe_komisyon(2.0), 1800), "ilk kademenin altı 0, son kademenin üstü sabit")
try:
    P.create({'name': 'Eksik', 'bas': ay_bas, 'bit': ay_bas, 'basari_ids': [(0, 0, {'tip': 'satis_tutar'})]}).action_onayla(); eksik = True
except UserError:
    eksik = False
ok(not eksik, "temsilcisiz plan onaylanamaz")

# ---------------------------------------------------------------- ekip planı
siparis(s2, [(urun_a, 1, 2000)], team=ekip)
eplan = P.create({'name': 'Ekip Primi', 'bas': ay_bas, 'bit': ay_bas.replace(day=28), 'kullanici_tipi': 'ekip',
                  'basari_ids': [(0, 0, {'tip': 'satis_tutar', 'oran': 1.0})], 'uye_ids': [(0, 0, {'team_id': ekip.id})]})
eplan.action_onayla()
ok(yakin(eplan.sonuc_ids.komisyon, 20) and eplan.sonuc_ids.team_id == ekip, "ekip planı: ekibin siparişleri")

# ---------------------------------------------------------------- döviz
usd = env['res.currency'].create({'name': 'XKM', 'symbol': 'K', 'rounding': 0.01})
env['res.currency.rate'].create({'currency_id': usd.id, 'name': bugun - timedelta(days=1), 'rate': 1 / 40.0})
liste = env['product.pricelist'].create({'name': 'USD', 'currency_id': usd.id})
so_usd = env['sale.order'].create({'partner_id': musteri.id, 'user_id': s2.id, 'pricelist_id': liste.id,
                                   'order_line': [(0, 0, {'product_id': urun_b.id, 'product_uom_qty': 1, 'price_unit': 100, 'tax_ids': [(5, 0, 0)]})]})
so_usd.action_confirm()
plan.action_hesapla()
r2 = plan.sonuc_ids.filtered(lambda r: r.user_id == s2 and r.donem_bas == ay_bas)
usd_satir = r2.satir_ids.filtered(lambda s: s.belge == so_usd.name and s.kural_id.tip == 'satis_tutar' and not s.kural_id.kategori_id)
ok(yakin(usd_satir.tutar, 4000), "döviz siparişi şirket para birimine çevrilir (100 × 40)")

# ---------------------------------------------------------------- erişim
gorulen = env['atlas.komisyon.sonuc'].with_user(s2).search([])
ok(gorulen and all(r.user_id == s2 for r in gorulen), "temsilci yalnız kendi komisyonunu görür")
ok(env['atlas.komisyon.sonuc'].with_user(s1).search_count([('team_id', '=', ekip.id)]) == 1, "ekip üyesi ekip sonucunu görür")
try:
    plan.with_user(s1).write({'name': 'x'}); yazdi = True
except AccessError:
    yazdi = False
ok(not yazdi, "temsilci planı değiştiremez")

plan.action_kapat()
ok(plan.durum == 'kapali' and plan.sonuc_ids, "kapat: sonuçlar sabitlenir")
env.cr.rollback(); print("(geri alındı)")
