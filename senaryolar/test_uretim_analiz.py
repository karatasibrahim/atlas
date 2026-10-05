from datetime import datetime, timedelta
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
yak = lambda a, b, t=0.05: abs((a or 0) - b) <= t
U = env['product.product']
urun = U.create({'name': 'UA Pano', 'is_storable': True})
celik = U.create({'name': 'UA Çelik Sac', 'is_storable': True, 'standard_price': 50})
vida = U.create({'name': 'UA Vida', 'is_storable': True, 'standard_price': 0.5})
stok = env.ref('stock.stock_location_stock')
env['stock.quant']._update_available_quantity(celik, stok, 100)
env['stock.quant']._update_available_quantity(vida, stok, 1000)
wc = env['mrp.workcenter'].create({'name': 'UA Kaynak', 'code': 'UAK', 'costs_hour': 120})
bom = env['mrp.bom'].create({'product_tmpl_id': urun.product_tmpl_id.id, 'product_qty': 1, 'bom_line_ids': [
    Command.create({'product_id': celik.id, 'product_qty': 2}), Command.create({'product_id': vida.id, 'product_qty': 8})],
    'operation_ids': [Command.create({'name': 'Kaynak', 'workcenter_id': wc.id, 'time_mode': 'manual', 'time_cycle_manual': 15})]})
calisan = env['hr.employee'].create({'name': 'UA Operatör', 'hourly_cost': 300, 'user_id': env.user.id}) if not env.user.employee_id else env.user.employee_id
calisan.hourly_cost = 300
mo = env['mrp.production'].create({'product_id': urun.id, 'product_qty': 10, 'bom_id': bom.id})
mo.action_confirm()
mo.action_assign()
wo = mo.workorder_ids
simdi = datetime.now()
env['mrp.workcenter.productivity'].create({'workorder_id': wo.id, 'workcenter_id': wc.id, 'user_id': env.user.id,
                                           'loss_id': env.ref('mrp.block_reason7').id, 'date_start': simdi - timedelta(minutes=180), 'date_end': simdi})
mo.qty_producing = 9
mo._set_qty_producing(False) if hasattr(mo, '_set_qty_producing') else None
for m in mo.move_raw_ids:
    m.quantity = m.product_uom_qty * 0.9
    m.picked = True
mo.with_context(skip_backorder=True, mo_ids_to_backorder=[]).button_mark_done()
a = env['atlas.uretim.analiz'].search([('production_id', '=', mo.id)])
ok(mo.state == 'done' and a, "üretim emri bitince analiz satırı oluştu")
ok(a.qty_demanded == 10 and a.qty_produced == 9 and yak(a.yield_rate, 90), f"talep 10, üretilen 9, verim %{a.yield_rate}")
ok(yak(a.component_cost, 9 * (2 * 50 + 8 * 0.5)), f"bileşen maliyeti 9 × 104 = 936 ({a.component_cost})")
ok(yak(a.workcenter_cost, 3 * 120) and yak(a.employee_cost, 3 * 300) and yak(a.duration, 180),
   f"iş merkezi 3 saat × 120 = 360 ({a.workcenter_cost}), işçilik 3 × 300 = 900 ({a.employee_cost})")
ok(yak(a.total_cost, 936 + 360 + 900) and yak(a.unit_cost, (936 + 360 + 900) / 9), f"toplam {a.total_cost}, birim {a.unit_cost:.2f}")
ok(yak(a.expected_component_cost_unit, 104) and yak(a.expected_operation_cost_unit, 15 / 60 * 120) and yak(a.expected_total_cost_unit, 134),
   f"beklenen birim: bileşen 104 + operasyon 30 = 134 ({a.expected_total_cost_unit})")
ok(yak(a.sapma_unit, a.unit_cost - 134) and a.sapma_yuzde > 0, f"sapma %{a.sapma_yuzde:.1f} (işçilik ve süre beklenenden fazla)")
veri = mo._atlas_maliyet_yapisi()
ok(len(veri) == 1 and {b['urun'] for b in veri[0]['bilesenler']} == {celik, vida} and veri[0]['operasyonlar'][0]['saat_ucreti'] == 120,
   "maliyet yapısı: bileşen ve operasyon dökümü")
html = env['ir.actions.report']._render_qweb_html('atlas_uretim_analiz.action_report_maliyet_yapisi', mo.ids)[0]
ok(b'UA Pano' in html and b'Birim maliyet' in html, "Maliyet Yapısı raporu oluşuyor")
env['atlas.uretim.analiz'].action_yenile()
ok(env['atlas.uretim.analiz'].search_count([('production_id', '=', mo.id)]) == 1, "yenile: satır tekrarlanmadan güncellenir")
env.cr.rollback(); print("(geri alındı)")
