from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k); env.flush_all()
        return None
    except (UserError, ValidationError) as e: return str(e)
P = env['res.partner']; Pl = env['atlas.irsaliye.plaka']; So = env['atlas.irsaliye.sofor']; c = env.company
arac = Pl.create({'name': '34 abc 123'})
ok(arac.name == '34ABC123' and arac.display_name == '34 ABC 123', f"plaka biçimlendi: {arac.display_name}")
ok(hata(Pl.create, {'name': '99XX1'}) is not None, "geçersiz plaka reddedildi")
dorse = Pl.create({'name': '06 D 4567', 'tip': 'dorse'})
ok(hata(So.create, {'ad': 'A', 'soyad': 'B', 'tckn': '12345678901'}) is not None, "geçersiz TCKN reddedildi")
sofor = So.create({'ad': 'Mehmet', 'soyad': 'Kaya', 'tckn': '10000000146'})
arac.sofor_id = sofor
urun = env['product.product'].create({'name': 'IRS Ürün', 'is_storable': True})
env['stock.quant']._update_available_quantity(urun, env.ref('stock.stock_location_stock'), 100)
def sevkiyat(partner):
    so = env['sale.order'].create({'partner_id': partner.id, 'order_line': [Command.create({'product_id': urun.id, 'product_uom_qty': 1, 'price_unit': 1, 'tax_ids': False})]})
    so.action_confirm(); pk = so.picking_ids; pk.move_ids.quantity = 1; return pk
mus = P.create({'name': 'IRS Müşteri', 'is_company': True})
c.atlas_eirsaliye = False
pk0 = sevkiyat(mus); pk0.button_validate()
ok(pk0.state == 'done', "e-İrsaliye kapalıyken sevk bilgisi istenmedi")
c.atlas_eirsaliye = True
pk = sevkiyat(mus)
e = hata(pk.button_validate)
ok(e and 'alıcı VKN' in e and 'araç plakası' in e and 'şoför' in e, f"eksikler listelendi: {e and e.split(':', 1)[1][:80]}")
mus.write({'vat': '1234567890', 'country_id': env.ref('base.tr').id})
with env.cr.savepoint():
    pass
pk.atlas_arac_id = arac; pk._onchange_atlas_arac_id(); pk.atlas_dorse_ids = dorse
ok(pk.atlas_sofor_ids == sofor, "araç seçilince varsayılan şoför geldi")
pk.write({'atlas_sofor_ids': [Command.set(sofor.ids)]})
pk.button_validate()
ok(pk.state == 'done' and pk.atlas_arac_plaka == '34 ABC 123' and pk.atlas_dorse_plaka == '06 D 4567' and pk.atlas_sofor_tckn == '10000000146' and pk.atlas_fiili_sevk_tarihi,
   "doğrulandı; plaka/dorse/şoför irsaliye alanlarına yazıldı")
html = env['ir.actions.report']._render_qweb_html('stock.report_deliveryslip', pk.ids)[0]
ok(b'34 ABC 123' in html and b'Mehmet Kaya' in html, "irsaliye çıktısında plaka ve şoför")
tas = P.create({'name': 'Hızlı Nakliyat', 'is_company': True})
pk2 = sevkiyat(mus); pk2.atlas_tasiyici_id = tas
ok('taşıyıcı firma VKN' in (hata(pk2.button_validate) or ''), "taşıyıcının VKN'si zorunlu")
tas.write({'vat': '1234567890', 'country_id': env.ref('base.tr').id})
pk2.button_validate()
ok(pk2.state == 'done', "taşıyıcı firmayla plaka/şoför olmadan doğrulandı")
html = env['ir.actions.report']._render_qweb_html('stock.report_deliveryslip', pk2.ids)[0]
ok('Hızlı Nakliyat'.encode() in html, "çıktıda taşıyıcı")
pk3 = sevkiyat(mus); pk3.atlas_irsaliye_tipi = 'MATBUDAN'
ok('matbu' in (hata(pk3.button_validate) or ''), "matbu irsaliyede no/tarih zorunlu")
pk3.write({'atlas_matbu_no': 'A-001234', 'atlas_matbu_tarih': '2026-10-04'}); pk3.button_validate()
ok(pk3.state == 'done', "matbu irsaliye bilgisiyle doğrulandı")
env.cr.rollback(); print("(geri alındı)")
