from odoo.fields import Command, Date
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; P = env['res.partner']
code = lambda a: a.with_company(c).code
cats = {x: env.ref(f'atlas_stok.categ_{x}') for x in ('ticari_mal', 'ilk_madde', 'yari_mamul', 'mamul', 'diger_stok')}
ok(c.cost_method == 'average' and c.inventory_valuation == 'periodic', f"şirket: {c.cost_method} / {c.inventory_valuation}")
ok(all(env.user.has_group(g) for g in ('stock.group_production_lot', 'stock.group_stock_multi_locations', 'uom.group_uom', 'mrp.group_mrp_routings')), "lot/seri, çoklu lokasyon, ölçü birimi, iş emri açık")
hiz = env.ref('product.product_category_services')
ok(code(hiz.with_company(c).property_account_expense_categ_id) == '770000' and code(env.ref('product.product_category_goods').with_company(c).property_account_expense_categ_id) == '153000', "Hizmetler gideri 770, varsayılan Mallar kategorisi 153")

ted = P.create({'name': 'Tedarikçi', 'is_company': True, 'atlas_cari_tipi': 'satici'})
mus = P.create({'name': 'Müşteri', 'is_company': True, 'atlas_cari_tipi': 'alici'})
Prod = env['product.product']
def urun(name, cat, price=0):
    return Prod.create({'name': name, 'is_storable': True, 'tracking': False, 'categ_id': cats[cat].id, 'list_price': price, 'purchase_ok': True, 'sale_ok': True})
def satinal(product, qty, price):
    po = env['purchase.order'].create({'partner_id': ted.id, 'order_line': [Command.create({'product_id': product.id, 'product_qty': qty, 'price_unit': price, 'tax_ids': False})]})
    po.button_confirm()
    for pk in po.picking_ids:
        pk.move_ids.quantity = qty; pk.button_validate()
    po.action_create_invoice(); bill = po.invoice_ids; bill.invoice_date = Date.today(); bill.action_post()
    return po, bill
def sat(product, qty, price):
    so = env['sale.order'].create({'partner_id': mus.id, 'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': qty, 'price_unit': price, 'tax_ids': False})]})
    so.action_confirm()
    for pk in so.picking_ids:
        pk.move_ids.quantity = qty; pk.button_validate()
    inv = so._create_invoices(); inv.action_post()
    return so, inv

tm = urun('Ticari Ürün', 'ticari_mal', 200)
po, bill = satinal(tm, 10, 100)
ok([code(l.account_id) for l in bill.invoice_line_ids] == ['153000'], f"alış faturası satırı 153'e: {bill.name}")
so, inv = sat(tm, 4, 200)
pk = so.picking_ids
ok(pk.atlas_irsaliye_no == f'IRS{Date.today().year}000000001' and len(pk.atlas_irsaliye_no) == 16 and pk.atlas_fiili_sevk_tarihi, f"sevkiyat irsaliye no: {pk.atlas_irsaliye_no}")
ok(not po.picking_ids.atlas_irsaliye_no, "mal kabule irsaliye numarası verilmedi")
ok([code(l.account_id) for l in inv.invoice_line_ids] == ['600000'], f"satış faturası 600: {inv.name}")
so2, _i2 = sat(tm, 1, 200)
ok(so2.picking_ids.atlas_irsaliye_no == f'IRS{Date.today().year}000000002', f"ikinci irsaliye: {so2.picking_ids.atlas_irsaliye_no}")

hm = urun('Hammadde', 'ilk_madde'); mm = urun('Mamul', 'mamul', 100)
satinal(hm, 20, 10)
bom = env['mrp.bom'].create({'product_tmpl_id': mm.product_tmpl_id.id, 'product_qty': 1, 'bom_line_ids': [Command.create({'product_id': hm.id, 'product_qty': 2})]})
mo = env['mrp.production'].create({'product_id': mm.id, 'product_qty': 5, 'bom_id': bom.id})
mo.action_confirm(); mo.action_assign(); mo.qty_producing = 5
mo.move_raw_ids.quantity = 10; mo.move_raw_ids.picked = True
mo.button_mark_done()
ok(mo.state == 'done' and hm.qty_available == 10 and mm.qty_available == 5, f"üretim {mo.name}: hammadde kalan {hm.qty_available}, mamul {mm.qty_available}")
sat(mm, 3, 100)

env.flush_all()
bal = lambda cd: sum(env['account.move.line'].search([('parent_state','=','posted'), ('account_id.code','=like', cd + '%')]).mapped('balance'))
w = env['atlas.stok.kapanis.wizard'].create({'date': Date.today()})
moves = env['account.move'].search(w.action_kapat()['domain'])
env.flush_all()
after = {k: bal(k) for k in ('150', '151', '152', '153', '620', '621', '710', '711')}
print("   kapanış sonrası:", after)
tm_val, hm_val, mm_val = tm.total_value, hm.total_value, mm.total_value
ok(after['153'] == tm_val == 500 and after['621'] == 500, f"ticari: 153 = stok değeri {tm_val}, 621 SMM {after['621']}")
ok(after['150'] == hm_val == 100, f"hammadde: 150 = stok değeri {hm_val}")
ok(after['152'] == mm_val == 40 and after['151'] == 0, f"mamul: 152 = stok değeri {mm_val}, 151 sıfır")
ok(after['620'] == 60 and after['710'] + after['711'] == 0, f"620 satılan mamul maliyeti {after['620']} (3 x 20), 710/711 yansıtıldı")
ok(not any(len(m.line_ids.filtered(lambda l: code(l.account_id) == '710000')) > 1 and m.ref == 'Stock Closing' for m in moves), "kapanışta gereksiz 710 ± satırları yok")

c.inventory_valuation = 'real_time'; c._atlas_apply_inventory_mode()
ok(code(cats['ticari_mal'].with_company(c).property_account_expense_categ_id) == '621000', "sürekli envantere geçince ticari mal gideri 621")
c.inventory_valuation = 'periodic'; c._atlas_apply_inventory_mode()
ok(code(cats['ticari_mal'].with_company(c).property_account_expense_categ_id) == '153000', "aralıklıya dönünce tekrar 153")
html = env['ir.actions.report']._render_qweb_html('stock.report_deliveryslip', pk.ids)[0]
ok(pk.atlas_irsaliye_no.encode() in html, "irsaliye çıktısında irsaliye no var")
env.cr.rollback(); print("(geri alındı)")
