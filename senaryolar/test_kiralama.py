from datetime import datetime, timedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
SO = env['sale.order']; Prod = env['product.product']; c = env.company
stok = env['stock.warehouse'].search([('company_id', '=', c.id)], limit=1).lot_stock_id
jen = Prod.create({'name': 'KRA Jeneratör', 'is_storable': True, 'tracking': False, 'atlas_kiralik': True, 'invoice_policy': 'order',
                   'atlas_gecikme_ucreti': 800, 'atlas_kira_fiyat_ids': [Command.create({'sure': 1, 'birim': 'gun', 'fiyat': 1000}),
                                                                        Command.create({'sure': 1, 'birim': 'hafta', 'fiyat': 5000})]})
env['stock.quant']._update_available_quantity(jen, stok, 2)
mus = env['res.partner'].create({'name': 'KRA Müşteri', 'is_company': True, 'atlas_cari_tipi': 'alici'})
def kira(bas, gun, adet=1, urun=jen):
    return SO.create({'partner_id': mus.id, 'atlas_kiralama': True, 'atlas_kira_bas': bas, 'atlas_kira_bit': bas + timedelta(days=gun),
                      'order_line': [Command.create({'product_id': urun.id, 'product_uom_qty': adet, 'tax_ids': False})]})
t = datetime(2026, 11, 2, 8, 0)
s1 = kira(t, 3)
ok(s1.order_line.price_unit == 3000 and s1.atlas_kira_sure.strip() == '3 gün', f"3 gün: 3 × 1.000 = {s1.order_line.price_unit:,.0f}")
ok(kira(t, 9).order_line.price_unit == 9000 and kira(t, 12).order_line.price_unit == 10000, "9 gün 9.000 (günlük), 12 gün 10.000 (2 hafta)")
s1.write({'atlas_kira_bit': t + timedelta(days=6)})
ok(s1.order_line.price_unit == 5000, "tarih değişince fiyat yeniden hesaplandı (6 gün → 1 hafta 5.000)")
s1.write({'atlas_kira_bit': t + timedelta(days=3)})
s1.action_confirm()
ok(s1.atlas_kira_durum == 'rezervasyon' and not s1.picking_ids, "onay: rezerve, teslimat transferi oluşmadı")
s2 = kira(t + timedelta(days=1), 2, adet=2)
try:
    with env.cr.savepoint(): s2.action_confirm(); hata = None
except UserError as e: hata = str(e)
ok(hata and 'müsait değil' in hata, "çakışan dönemde 2 adet: müsait değil (filo 2, 1 kirada)")
s3 = kira(t + timedelta(days=4), 2, adet=2); s3.action_confirm()
ok(s3.atlas_kira_durum == 'rezervasyon', "çakışmayan dönemde 2 adet kiralandı")
s1.action_atlas_teslim_et()
kirada = c.atlas_kirada_lokasyon_id
ok(s1.atlas_kira_durum == 'teslim' and jen.with_context(location=stok.id).qty_available == 1 and jen.with_context(location=kirada.id).qty_available == 1,
   "teslim: 1 adet 'Kirada' lokasyonuna geçti")
simdi = fields.Datetime.now()
s1.atlas_kira_bit = simdi - timedelta(days=1, hours=12)
ok(s1 in SO.search([('atlas_gecikmis', '=', True)]), "gecikmiş kiralama listede")
s1.action_atlas_iade_al()
gec = s1.order_line.filtered(lambda l: l.product_id == env.ref('atlas_kiralama.urun_gecikme'))
ok(s1.atlas_kira_durum == 'iade' and jen.with_context(location=stok.id).qty_available == 2 and gec.product_uom_qty == 2 and gec.price_unit == 800,
   "iade: stoğa döndü, 2 gün gecikme bedeli (800/gün) eklendi")
inv = s1._create_invoices(); inv.action_post()
ok(inv.amount_untaxed == 3000 + 1600, f"fatura: kira 3.000 + gecikme 1.600 = {inv.amount_untaxed:,.0f}")
iskele = Prod.create({'name': 'KRA İskele', 'is_storable': True, 'tracking': 'serial', 'atlas_kiralik': True, 'invoice_policy': 'order',
                      'atlas_kira_fiyat_ids': [Command.create({'sure': 1, 'birim': 'gun', 'fiyat': 200})]})
lot = env['stock.lot'].create({'name': 'ISK-001', 'product_id': iskele.id, 'company_id': c.id})
env['stock.quant']._update_available_quantity(iskele, stok, 1, lot_id=lot)
s4 = kira(t + timedelta(days=20), 2, urun=iskele); s4.action_confirm(); s4.action_atlas_teslim_et()
q = env['stock.quant'].search([('lot_id', '=', lot.id), ('quantity', '>', 0)])
ok(q.location_id == kirada, "seri takipli ürün (ISK-001) kirada")
s4.action_atlas_iade_al()
q = env['stock.quant'].search([('lot_id', '=', lot.id), ('quantity', '>', 0)])
ok(q.location_id == stok and len(s4.atlas_kira_picking_ids) == 2, "aynı seri numarasıyla stoğa döndü (2 transfer)")
cok = SO.create({'partner_id': mus.id, 'atlas_kiralama': True, 'atlas_kira_bas': t, 'atlas_kira_bit': t + timedelta(days=2),
                 'order_line': [Command.create({'product_id': jen.id, 'product_uom_qty': 1, 'tax_ids': False}),
                                Command.create({'product_id': jen.id, 'product_uom_qty': 1, 'tax_ids': False})]})
cok.write({'atlas_kira_bit': t + timedelta(days=4)})
ok(cok.order_line.mapped('price_unit') == [4000, 4000], "çok satırlı siparişte tarih değişince tüm kira fiyatları güncellendi")
yeni = SO.new({'partner_id': mus.id, 'atlas_kiralama': True}); yeni.atlas_kira_bas = t; yeni._onchange_atlas_kira_tarih()
ok(True, "satırsız yeni siparişte tarih onchange hatasız")
env.cr.rollback(); print("(geri alındı)")
