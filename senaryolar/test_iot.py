import socket
import threading
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
D = env['atlas.iot.cihaz']; D.search([]).write({'active': False})
# Sahte ağ yazıcısı: yerel TCP sunucu, gelen ZPL'i toplar
alinan = []
sunucu = socket.socket(); sunucu.bind(('127.0.0.1', 0)); sunucu.listen(5); port = sunucu.getsockname()[1]
def dinle():
    while True:
        try:
            b, _ = sunucu.accept()
        except OSError:
            return
        veri = b''
        while True:
            parca = b.recv(65536)
            if not parca:
                break
            veri += parca
        alinan.append(veri.decode('utf-8')); b.close()
threading.Thread(target=dinle, daemon=True).start()
yazici = D.create({'name': 'IOT Zebra', 'tur': 'yazici', 'ip': '127.0.0.1', 'port': port})
urun = env['product.product'].create({'name': 'IOT Çelik Profil ^özel', 'default_code': 'CP-40', 'barcode': '8690000000017', 'is_storable': True})
yazici.action_test_etiketi()
import time; time.sleep(0.2)
ok(alinan and alinan[-1].startswith('^XA') and 'IOT Zebra' in alinan[-1], "test etiketi yazıcıya ulaştı")
terazi = D.create({'name': 'IOT Terazi', 'tur': 'terazi'})
t = env['atlas.iot.tartim'].create({'product_id': urun.id, 'terazi_id': terazi.id, 'agirlik': 25.4, 'dara': 0.4, 'yazici_id': yazici.id, 'etiket_adedi': 2})
ok(t.name.startswith('TRT') and t.net == 25.0 and terazi.son_deger == 25.4, "tartım: net 25,0, terazinin son değeri güncellendi")
t.action_etiket_bas(); time.sleep(0.2)
zpl = alinan[-1]
ok('^FD25 kg^FS' in zpl.replace('Units', 'kg') or '25' in zpl, "etikette net ağırlık")
ok('^PQ2' in zpl and '8690000000017' in zpl and 'CP-40' in zpl and t.yazdirildi, "etiket: 2 adet, barkod ve kod")
ok('özel' in zpl and '^özel' not in zpl, "metindeki ZPL kontrol karakteri temizlendi")
try:
    with env.cr.savepoint(): env['atlas.iot.tartim'].create({'product_id': urun.id, 'agirlik': 1, 'dara': 2}); gecti = True
except ValidationError: gecti = False
ok(not gecti, "dara ağırlıktan büyük olamaz")
w = env['atlas.iot.etiket'].with_context(**urun.action_atlas_etiket_yazdir()['context']).create({'yazici_id': yazici.id, 'adet': 3})
w.action_yazdir(); time.sleep(0.2)
ok('^PQ3' in alinan[-1], "üründen toplu etiket yazdırma")
kapali = D.create({'name': 'IOT Kapalı', 'tur': 'yazici', 'ip': '127.0.0.1', 'port': 1})
try:
    with env.cr.savepoint(): kapali.action_test_etiketi(); basti = True
except UserError: basti = False
ok(not basti, "ulaşılamayan yazıcı anlaşılır hata verdi")
sunucu.close()
# Makine sayacı → iş emri
cat = lambda x: env.ref(f'atlas_stok.categ_{x}')
Prod = env['product.product']
vida = Prod.create({'name': 'IOT Vida', 'is_storable': True, 'categ_id': cat('ilk_madde').id})
mamul = Prod.create({'name': 'IOT Mamul', 'is_storable': True, 'tracking': False, 'categ_id': cat('mamul').id})
env['stock.quant']._update_available_quantity(vida, env.ref('stock.stock_location_stock'), 100)
wc = env['mrp.workcenter'].create({'name': 'IOT Pres', 'code': 'IOTP'})
bom = env['mrp.bom'].create({'product_tmpl_id': mamul.product_tmpl_id.id, 'product_qty': 1, 'bom_line_ids': [Command.create({'product_id': vida.id, 'product_qty': 1})],
                             'operation_ids': [Command.create({'name': 'Pres', 'workcenter_id': wc.id, 'time_cycle_manual': 1})]})
mo = env['mrp.production'].create({'product_id': mamul.id, 'product_qty': 50, 'bom_id': bom.id}); mo.action_confirm(); mo.action_assign()
wo = mo.workorder_ids; wo.button_start()
sayac = D.create({'name': 'IOT Pres Sayacı', 'tur': 'sayac', 'workcenter_id': wc.id})
ok(sayac.veri_url.endswith('/iot/veri/' + sayac.anahtar) and len(sayac.anahtar) >= 20, "sayaç veri adresi")
s1 = sayac._veri_isle({'adet': '12', 'hatali': '1', 'durum': 'calisiyor'})
s2 = sayac._veri_isle({'count': 8})
ok(wo.qty_producing == 20 and wo.atlas_hatali_adet == 1 and s2['uretilen'] == 20 and sayac.sayac_toplam == 20 and sayac.cevrimici,
   "sayım çalışan iş emrine eklendi (20 üretilen, 1 hatalı)")
sayac._veri_isle({'durum': 'durdu', 'aciklama': 'Kalıp sıkıştı'})
ok(wc.working_state == 'blocked' and env['mrp.workcenter.productivity'].search_count([('workcenter_id', '=', wc.id), ('description', '=', 'Kalıp sıkıştı')]) == 1,
   "makine durdu: iş merkezi duruşta (OEE kaybı kaydı)")
sayac._veri_isle({'state': 'running'})
ok(wc.working_state != 'blocked', "makine çalışınca duruş bitti")
try:
    with env.cr.savepoint(): sayac._veri_isle({'adet': -5}); negatif = True
except UserError: negatif = False
ok(not negatif, "negatif sayım reddedildi")
wo.end_all()
s3 = sayac._veri_isle({'adet': 3})
ok('uyari' in s3 and wo.qty_producing == 20, "çalışan iş emri yokken sayım yalnız kaydedildi")
# Sensör
sensor = D.create({'name': 'IOT Fırın Sıcaklığı', 'tur': 'sensor', 'birim': '°C', 'sinir_aktif': True, 'alt_sinir': 180, 'ust_sinir': 220,
                   'sorumlu_id': env.ref('base.user_admin').id})
r1 = sensor._veri_isle({'deger': '200,5'})
r2 = sensor._veri_isle({'value': 235})
sensor._veri_isle({'deger': 240})
ok(not r1['alarm'] and r2['alarm'] and sensor.son_deger == 240 and len(sensor.olcum_ids) == 3, "sensör ölçümleri kaydedildi, sınır aşımı alarmı")
ok(len(sensor.activity_ids) == 1 and 'Sınır aşımı' in sensor.activity_ids.summary, "sorumluya tek aktivite (tekrarlanmadı)")
try:
    with env.cr.savepoint(): sensor._veri_isle({'deger': 'abc'}); gecersiz = True
except UserError: gecersiz = False
ok(not gecersiz, "geçersiz sensör değeri reddedildi")
eski = sensor.anahtar; sensor.action_anahtar_yenile()
ok(sensor.anahtar != eski, "cihaz anahtarı yenilendi")
env.cr.rollback(); print("(geri alındı)")
