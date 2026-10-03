from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k)
        return None
    except UserError as e: return str(e)
B = env['atlas.barkod']; P = env['res.partner']; Prod = env['product.product']
assert env.ref('atlas_stok.categ_mamul').atlas_varsayilan_takip == 'serial'
ted = P.create({'name': 'Tedarikçi', 'is_company': True}); mus = P.create({'name': 'Müşteri', 'is_company': True})
tm = Prod.create({'name': 'Klima', 'default_code': 'KLM-01', 'is_storable': True, 'categ_id': env.ref('atlas_stok.categ_ticari_mal').id})
hm = Prod.create({'name': 'Vida', 'default_code': 'VD-5', 'barcode': '8690000000017', 'is_storable': True, 'categ_id': env.ref('atlas_stok.categ_ilk_madde').id})
mm = Prod.create({'name': 'Kombi', 'default_code': 'KMB-1', 'is_storable': True, 'categ_id': env.ref('atlas_stok.categ_mamul').id})
tm.product_tmpl_id.serial_prefix_format = 'KLM'
ok(tm.tracking == 'serial' and mm.tracking == 'serial' and not hm.tracking, f"kategoriden varsayılan takip: klima {tm.tracking}, kombi {mm.tracking}, vida {hm.tracking or 'yok'}")

po = env['purchase.order'].create({'partner_id': ted.id, 'order_line': [
    Command.create({'product_id': tm.id, 'product_qty': 3, 'price_unit': 100, 'tax_ids': False}),
    Command.create({'product_id': hm.id, 'product_qty': 20, 'price_unit': 1, 'tax_ids': False})]})
po.button_confirm(); rec = po.picking_ids
ok(any(x['id'] == rec.id for x in B.belge_listesi('mal_kabul')) and B.ana_ekran()['mal_kabul'] >= 1, f"mal kabul listesinde: {rec.name}")
r = B.okut('mal_kabul', rec.id, '8690000000017', 12)
ok(r['sonuc'] == 'ok' and [s['okutulan'] for s in r['belge']['satirlar'] if s['urun']['kod'] == 'VD-5'] == [12], f"vida barkodu 12 adet: {r['mesaj']}")
B.okut('mal_kabul', rec.id, 'VD-5', 8)
ok('seri' in (hata(B.okut, 'mal_kabul', rec.id, 'KLM-01') or ''), "seri takipli ürün barkodu reddedildi (seri istenir)")
mv = rec.move_ids.filtered(lambda m: m.product_id == tm)
r = B.seri_uret('mal_kabul', rec.id, mv.id)
lots = env['stock.lot'].browse(r['seri_ids'])
ok(len(lots) == 3 and all(l.name.startswith('KLM') for l in lots), f"3 seri üretildi: {lots.mapped('name')}")
ok('zaten' in (hata(B.okut, 'mal_kabul', rec.id, lots[0].atlas_qr) or ''), "aynı seri ikinci kez okutulamaz")
url = B.etiket_url(lots.ids); ok(url.endswith(','.join(map(str, lots.ids))), f"etiket: {url}")
r = B.dogrula('mal_kabul', rec.id)
ok(rec.state == 'done' and tm.qty_available == 3 and hm.qty_available == 20, f"mal kabul tamam: {r['mesaj']}")

so = env['sale.order'].create({'partner_id': mus.id, 'order_line': [Command.create({'product_id': tm.id, 'product_uom_qty': 2, 'price_unit': 300, 'tax_ids': False})]})
so.action_confirm(); out = so.picking_ids
r = B.okut('sevkiyat', out.id, lots[0].atlas_qr)
ok(r['sonuc'] == 'ok' and r['belge']['satirlar'][0]['seriler'] == [lots[0].name], f"QR ile seri okutuldu: {r['mesaj']}")
ok(hata(B.okut, 'sevkiyat', out.id, 'ATL:LOT:KLM-01:YOKBOYLE') is not None, "stokta olmayan seri reddedildi")
ok('zaten' in (hata(B.okut, 'sevkiyat', out.id, lots[0].name) or ''), "düz seri no ile aynı seri tekrar reddedildi")
ok('belgede yok' in (hata(B.okut, 'sevkiyat', out.id, '8690000000017') or ''), "belgede olmayan ürün reddedildi")
r = B.dogrula('sevkiyat', out.id, kalan_icin_belge=True)
bo = env['stock.picking'].browse(r['kalan_belge_id'])
ok(out.state == 'done' and out.atlas_irsaliye_no and bo and bo.move_ids.product_uom_qty == 1, f"sevkiyat: {r['mesaj']}")
ok(B.cozumle(out.atlas_irsaliye_no)['belge']['id'] == out.id, "irsaliye no okutunca belge bulunuyor")

stock = env.ref('stock.stock_location_stock')
for _ in range(3): B.sayim_okut(stock.id, '8690000000017')
r = B.sayim_okut(stock.id, lots[1].atlas_qr)
satir = {(s['urun']['kod'], s['seri']): s for s in r['belge']['satirlar']}
ok(satir[('VD-5', '')]['sayilan'] == 3 and satir[('VD-5', '')]['sistem'] == 20 and satir[('KLM-01', lots[1].name)]['sayilan'] == 1, "sayım: vida 3 (sistem 20), seri 1")
ok('zaten' in (hata(B.sayim_okut, stock.id, lots[1].atlas_qr) or ''), "sayımda aynı seri iki kez sayılmaz")
r = B.sayim_uygula(stock.id)
ok(hm.qty_available == 3 and tm.qty_available == 2, f"sayım uygulandı: vida {hm.qty_available}, klima {tm.qty_available} (sayılmayan seri dokunulmadı)")
B.sayim_okut(stock.id, lots[1].atlas_qr); B.sayim_uygula(stock.id, sifirla=True)
ok(tm.qty_available == 1 and hm.qty_available == 0, f"'sayılmayanları sıfırla': klima {tm.qty_available}, vida {hm.qty_available}")

B.sayim_okut(stock.id, '8690000000017', 10); B.sayim_uygula(stock.id)
bom = env['mrp.bom'].create({'product_tmpl_id': mm.product_tmpl_id.id, 'product_qty': 1, 'bom_line_ids': [Command.create({'product_id': hm.id, 'product_qty': 2})]})
mo = env['mrp.production'].create({'product_id': mm.id, 'product_qty': 2, 'bom_id': bom.id}); mo.action_confirm()
cz = B.cozumle(mo.atlas_qr)
ok(cz['tip'] == 'uretim' and cz['belge']['id'] == mo.id and cz['belge']['islem'] == 'uretim', f"üretim emri QR'ı çözüldü: {mo.atlas_qr}")
r = B.uretim_okut(mo.id, '8690000000017', 4)
ok(r['belge']['satirlar'][0]['okutulan'] == 4, f"malzeme okutuldu: {r['mesaj']}")
r = B.uretim_seri_uret(mo.id)
ok(len(r['seri_ids']) == 2 and all(s.startswith('KMB-1-') for s in r['belge']['mamul']['seriler']), f"mamul serileri (stok kodu ön ekli): {r['belge']['mamul']['seriler']}")
r = B.uretim_tamamla(mo.id)
ok(mo.state == 'done' and mm.qty_available == 2 and hm.qty_available == 6, f"üretim tamam: {r['mesaj']} (vida kalan {hm.qty_available})")
ml = env['stock.lot'].browse(r['seri_ids'])
ok(B.cozumle(ml[0].atlas_qr)['stok'][0]['miktar'] == 1, f"mamul seri QR'ı stokta görünüyor: {ml[0].atlas_qr}")
html = env['ir.actions.report']._render_qweb_html('atlas_barkod.report_seri_etiket', lots.ids)[0]
ok(html.count(b'barcode_type=QR') == 3 and lots[0].name.encode() in html, "seri etiketleri (3 adet QR)")
html = env['ir.actions.report']._render_qweb_html('mrp.report_mrporder', mo.ids)[0]
ok(b'barcode_type=QR' in html and b'ATL%3AMO%3A' in html, "üretim emri çıktısında QR")
env.cr.rollback(); print("(geri alındı)")
