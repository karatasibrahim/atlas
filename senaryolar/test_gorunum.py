from datetime import datetime, timedelta
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
V = env['ir.ui.view']
for xid, mode in [('mrp.mrp_production_action', 'atlas_gantt'), ('mrp.mrp_workorder_todo', 'atlas_gantt'), ('project.action_view_all_task', 'atlas_gantt'),
                  ('hr_holidays.hr_leave_action_action_approve_department', 'atlas_gantt'), ('atlas_kiralama.action_atlas_kiralama', 'atlas_gantt'),
                  ('contacts.action_contacts', 'atlas_harita'), ('sale.action_orders', 'atlas_harita')]:
    ok(mode in env.ref(xid).view_mode.split(','), f"{xid}: {mode} görünümü eklendi")
g = env['mrp.workorder'].get_views([(False, 'atlas_gantt')])
ok(g['views']['atlas_gantt']['arch'].startswith('<atlas_gantt') and 'workcenter_id' in g['models']['mrp.workorder']['fields'], "get_views: Gantt mimarisi ve alan bilgileri geliyor")
h = env['sale.order'].get_views([(False, 'atlas_harita')])
ok('partner_shipping_id' in h['models']['sale.order']['fields'], "get_views: harita partner alanı")
ok(V.get_view_info()['atlas_gantt']['icon'] == 'view_timeline' and V.get_view_info()['atlas_harita']['icon'] == 'map', "görünüm simgeleri")
def gecersiz(arch, model='mrp.workorder', tur='atlas_gantt'):
    try:
        with env.cr.savepoint(), mute_logger('odoo.addons.base.models.ir_ui_view'):
            V.create({'name': 'deneme', 'model': model, 'type': tur, 'arch': arch})
        return False
    except ValidationError:
        return True
ok(gecersiz('<atlas_gantt date_start="date_start"/>'), "date_stop eksik Gantt reddedildi")
ok(gecersiz('<atlas_gantt date_start="date_start" date_stop="yok_alan"/>'), "olmayan alan reddedildi")
ok(gecersiz('<atlas_gantt date_start="date_start" date_stop="date_finished" bilinmeyen="1"/>'), "bilinmeyen nitelik reddedildi")
ok(gecersiz('<atlas_gantt date_start="date_start" date_stop="date_finished"><div/></atlas_gantt>'), "field dışı alt düğüm reddedildi")
ok(gecersiz('<atlas_harita/>', 'res.partner', 'atlas_harita'), "konum bilgisi olmayan harita reddedildi")
ok(not gecersiz('<atlas_harita partner="parent_id"><field name="email"/></atlas_harita>', 'res.partner', 'atlas_harita'), "geçerli harita görünümü kabul edildi")
t = env['project.task'].create({'name': 'GRN görev', 'atlas_plan_baslangic': datetime(2026, 11, 2, 8), 'date_deadline': datetime(2026, 11, 5, 17)})
ok(t.atlas_plan_baslangic, "görevde planlanan başlangıç alanı")
try:
    with env.cr.savepoint(): t.atlas_plan_baslangic = datetime(2026, 11, 9); gecti = True
except ValidationError: gecti = False
ok(not gecti, "başlangıç son tarihten sonra olamaz")
env.cr.rollback(); print("(geri alındı)")
