from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k)
        return None
    except UserError as e: return str(e)
SF = env['atlas.shopfloor']; Prod = env['product.product']
cat = lambda x: env.ref(f'atlas_stok.categ_{x}')
vida = Prod.create({'name': 'SF Vida', 'is_storable': True, 'categ_id': cat('ilk_madde').id})
kombi = Prod.create({'name': 'SF Kombi', 'is_storable': True, 'tracking': False, 'categ_id': cat('mamul').id})
env['stock.quant']._update_available_quantity(vida, env.ref('stock.stock_location_stock'), 100)
wc = env['mrp.workcenter'].create({'name': 'SF Montaj Hattı', 'code': 'SFM'})
bom = env['mrp.bom'].create({'product_tmpl_id': kombi.product_tmpl_id.id, 'product_qty': 1,
    'bom_line_ids': [Command.create({'product_id': vida.id, 'product_qty': 4})],
    'operation_ids': [Command.create({'name': 'Kesim', 'workcenter_id': wc.id, 'time_cycle_manual': 30, 'sequence': 1,
                                      'atlas_talimat': '<p>Sacı <b>2 mm</b> kes</p>'}),
                      Command.create({'name': 'Montaj', 'workcenter_id': wc.id, 'time_cycle_manual': 60, 'sequence': 2})]})
bom.bom_line_ids.operation_id = bom.operation_ids.sorted('sequence')[0]
env['atlas.kalite.nokta'].search([]).active = False
env['atlas.kalite.nokta'].create({'name': 'SF Kesim kontrol', 'asama': 'ara', 'test_tipi': 'gecti_kaldi', 'olcum_yeri': 'islem',
                                  'operation_ids': [Command.set(bom.operation_ids.sorted('sequence')[:1].ids)]})
ali = env['hr.employee'].create({'name': 'SF Ali', 'pin': '1234'})
mo = env['mrp.production'].create({'product_id': kombi.id, 'product_qty': 5, 'bom_id': bom.id}); mo.action_confirm(); mo.action_assign()
w1, w2 = mo.workorder_ids.sorted(lambda w: w.operation_id.sequence)
m = {x['id']: x for x in SF.merkezler()}[wc.id]
ok(m['hazir'] + m['bekleyen'] >= 1 and m['durum'] == 'normal', f"iş merkezi listesi: {m['hazir']} hazır, {m['bekleyen']} bekleyen")
ok(any(o['id'] == ali.id and o['pin'] for o in SF.operatorler()), "operatör listesinde PIN'li çalışan")
ok('PIN' in (hata(SF.operator_dogrula, ali.id, '0000') or '') and SF.operator_dogrula(ali.id, '1234')['ad'] == 'SF Ali', "yanlış PIN reddedildi, doğru PIN kabul")
liste = SF.is_emirleri(wc.id)
ok({x['id'] for x in liste['is_emirleri']} >= {w1.id, w2.id} and liste['kayip_nedenleri'], "iş emri listesi ve duruş nedenleri")
d = SF.is_emri_ac(w1.id)
ok('2 mm' in d['talimat'] and d['bilesenler'][0]['gereken'] == 20 and len(d['kalite']) == 1 and not d['son_islem'], "iş emri ekranı: talimat, bileşen (20 vida), 1 kalite adımı")
d = SF.baslat(w1.id, ali.id)
ok(w1.state == 'progress' and d['calisiyor'] and d['operatorler'] == ['SF Ali'] and w1.time_ids.atlas_employee_id == ali, "başlatıldı, zaman kaydında operatör")
d = SF.duraklat(w1.id)
ok(not d['calisiyor'] and all(t.date_end for t in w1.time_ids), "duraklatıldı, sayaç durdu")
loss = env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'availability'), ('manual', '=', True)], limit=1)
SF.durus_bildir(wc.id, loss.id, 'Motor arızası', ali.id)
ok(wc.working_state == 'blocked' and 'duruşta' in (hata(SF.baslat, w1.id, ali.id) or ''), f"duruş ({loss.name}): iş merkezi engellendi, başlatılamadı")
SF.durus_bitir(wc.id)
ok(wc.working_state != 'blocked', "duruş bitti")
SF.baslat(w1.id, ali.id)
d = SF.tuketim_yaz(w1.id, d['bilesenler'][0]['id'], 20)
ok(d['bilesenler'][0]['tuketilen'] == 20, "bileşen tüketimi girildi")
r = SF.hurda(w1.id, vida.id, 2, 'çapak')
hurda = env['stock.move'].search([('is_scrap', '=', True), ('product_id', '=', vida.id), ('state', '=', 'done')])
ok(r['sonuc'] == 'ok' and hurda.quantity == 2, "2 vida hurdaya ayrıldı")
r = SF.sorun_bildir(w1.id, 'Kalıp aşınmış', 'kontrol edilsin', ali.id)
u = env['atlas.kalite.uyari'].search([('workorder_id', '=', w1.id)])
ok(u.workcenter_id == wc and u.oncelik == '2', f"sorun bildirimi: {u.name}")
ok('kalite' in (hata(SF.bitir, w1.id, 5, 1) or ''), "kalite adımı beklerken iş emri bitirilemedi")
k = d['kalite'][0]
SF.kalite_sonuc(k['id'], 'gecti')
d = SF.bitir(w1.id, 5, 1)
ok(w1.state == 'done' and w1.qty_produced == 5 and w1.atlas_hatali_adet == 1, "iş emri 1 bitti: 5 sağlam, 1 hatalı")
SF.baslat(w2.id, ali.id); d = SF.bitir(w2.id, 5, 0)
ok(d['son_islem'] and w2.state == 'done', "son iş emri bitti")
r = SF.uretimi_tamamla(w2.id)
ok(mo.state == 'done' and kombi.qty_available == 5, f"üretim tamamlandı: {r['mesaj']}")
env.cr.rollback(); print("(geri alındı)")
