from datetime import timedelta
from odoo import fields
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
SF = env['atlas.shopfloor']; Prod = env['product.product']
urun = Prod.create({'name': 'OEE Ürün', 'is_storable': True, 'tracking': False})
wc = env['mrp.workcenter'].create({'name': 'OEE Pres', 'code': 'OEP'})
wc2 = env['mrp.workcenter'].create({'name': 'OEE Boş Hat', 'code': 'OEB'})
bom = env['mrp.bom'].create({'product_tmpl_id': urun.product_tmpl_id.id, 'operation_ids': [Command.create({'name': 'Pres', 'workcenter_id': wc.id, 'time_cycle_manual': 30})]})
mo = env['mrp.production'].create({'product_id': urun.id, 'product_qty': 10, 'bom_id': bom.id}); mo.action_confirm()
wo = mo.workorder_ids
emp = env['hr.employee'].create({'name': 'OEE Operatör'})
SF.baslat(wo.id, emp.id)
simdi = fields.Datetime.now().replace(microsecond=0)
wo.time_ids.write({'date_start': simdi - timedelta(hours=8), 'date_end': simdi - timedelta(hours=2)})  # 6 saat çalışma
ariza = env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'availability'), ('manual', '=', True)], limit=1)
env['mrp.workcenter.productivity'].create({'workcenter_id': wc.id, 'loss_id': ariza.id, 'date_start': simdi - timedelta(hours=2), 'date_end': simdi})
SF.bitir(wo.id, 9, 1)
ok(wo.duration_expected == 300 and wo.qty_produced == 9 and wo.atlas_hatali_adet == 1, "iş emri: beklenen 300 dk, 9 sağlam + 1 hatalı")
bugun = fields.Date.context_today(env['atlas.rapor.wizard'])
w = env['atlas.rapor.wizard'].create({'rapor_turu': 'oee', 'date_from': bugun - timedelta(days=1), 'date_to': bugun + timedelta(days=1),
                                      'workcenter_ids': [Command.set((wc | wc2).ids)], 'sadece_hareketli': False})
r = w._get_report()
satir = {}
for row in r['rows']:
    if row['style'] == 'detail' and row['cells'][0] in ('OEP', 'OEB'):
        satir.setdefault(row['cells'][0], row['cells'])
p = satir['OEP']
ok(p[2] == 8 and p[3] == 6 and p[4] == 2 and p[5] == 75.0, f"kullanılabilirlik: 6 sa çalışma / 8 sa planlanan = %{p[5]}")
ok(p[6] == 83.3 and p[9] == 90.0, f"performans %{p[6]} (300 dk ideal / 360 dk), kalite %{p[9]} (9/10)")
ok(p[10] == 56.2 or p[10] == 56.3, f"OEE %{p[10]} (0,75 × 0,833 × 0,90)")
ok(satir['OEB'][10] is None, "çalışmayan hat: OEE boş")
pareto = [row['cells'] for row in r['rows'] if row['cells'][0] == 'OEP' and row['style'] == 'detail' and 'kez' in str(row['cells'][1])]
ok(len(pareto) == 1 and pareto[0][4] == 2 and pareto[0][5] == 100.0, f"duruş nedenleri: {pareto[0][1]} 2 sa (%100)")
w.sadece_hareketli = True
ok('OEB' not in {row['cells'][0] for row in w._get_report()['rows']}, "hareketsiz hat gizlenebiliyor")
html = env['ir.actions.report']._render_qweb_html('atlas_rapor.report_atlas_rapor', w.ids)[0]
ok(w._build_xlsx(w._get_report())[:2] == b'PK' and b'OEE' in html, "ekran / Excel çıktısı")
env.cr.rollback(); print("(geri alındı)")
