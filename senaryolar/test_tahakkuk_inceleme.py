ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']
urun = env['product.product'].create({'name': 'TI Malzeme', 'is_storable': True, 'purchase_method': 'receive', 'invoice_policy': 'delivery',
                                      'standard_price': 10, 'list_price': 25})
tedarikci = P.create({'name': 'TI Tedarikçi'})
musteri = P.create({'name': 'TI Müşteri'})
POL = env['purchase.order.line']
SOL = env['sale.order.line']


def teslim(picking, miktar):
    for m in picking.move_ids:
        m.quantity = miktar
    picking.with_context(skip_backorder=True, cancel_backorder=True).button_validate()


# Alım 1: 10 sipariş, 6 teslim alındı, fatura yok → faturası gelecek 6 × 10
po = env['purchase.order'].create({'partner_id': tedarikci.id, 'order_line': [(0, 0, {'product_id': urun.id, 'product_qty': 10, 'price_unit': 10})]})
po.button_confirm()
teslim(po.picking_ids, 6)
satir = po.order_line
ok(satir in POL.search([('atlas_fatura_gelecek', '=', True)]) and satir.atlas_tahakkuk_miktar == 6 and satir.atlas_tahakkuk_tutar == 60,
   f"faturası gelecek alım: 6 adet / 60 TL ({satir.atlas_tahakkuk_miktar}, {satir.atlas_tahakkuk_tutar})")
ok(satir not in POL.search([('atlas_teslim_alinmamis', '=', True)]), "teslim alınıp faturası gelmeyen 'faturalanıp teslim alınmayan' listesinde değil")

# Alım 2: sipariş miktarı üzerinden faturalandı, teslim yok → faturalanıp teslim alınmayan
urun2 = env['product.product'].create({'name': 'TI Malzeme 2', 'is_storable': True, 'purchase_method': 'purchase', 'standard_price': 5})
po2 = env['purchase.order'].create({'partner_id': tedarikci.id, 'order_line': [(0, 0, {'product_id': urun2.id, 'product_qty': 4, 'price_unit': 5})]})
po2.button_confirm()
po2.action_create_invoice()
po2.invoice_ids.write({'invoice_date': po2.date_order.date()})
po2.invoice_ids.action_post()
ok(po2.order_line in POL.search([('atlas_teslim_alinmamis', '=', True)]) and po2.order_line.atlas_tahakkuk_tutar == -20,
   "faturalanıp teslim alınmayan alım: -4 adet / -20 TL (peşin ödenmiş gider)")

# Satış: 5 teslim edildi, fatura yok → düzenlenecek fatura
so = env['sale.order'].create({'partner_id': musteri.id, 'order_line': [(0, 0, {'product_id': urun.id, 'product_uom_qty': 8, 'price_unit': 25})]})
so.action_confirm()
env['stock.quant']._update_available_quantity(urun, so.warehouse_id.lot_stock_id, 20)
so.picking_ids.action_assign()
teslim(so.picking_ids, 5)
ok(so.order_line in SOL.search([('atlas_fatura_kesilecek', '=', True)]) and so.order_line.atlas_tahakkuk_tutar == 125,
   f"düzenlenecek fatura: 5 × 25 = 125 ({so.order_line.atlas_tahakkuk_tutar})")
# Odoo 20'nin 'in' biçimindeki boolean araması da çalışmalı
ok(so.order_line in SOL.search([('atlas_fatura_kesilecek', 'in', [True])]), "boolean aramanın 'in' biçimi")

# Menüler ve tahakkuk sihirbazı (Community) bağlantısı
ok(env.ref('atlas_satinalma_tahakkuk.menu_fatura_gelecek').parent_id.parent_id == env.ref('account.account_audit_menu')
   and env.ref('atlas_satis_tahakkuk.menu_fatura_kesilecek').action, "Muhasebe › İnceleme altında Satınalma ve Satış listeleri")
eylem = satir.action_open_accrual_wizard()
ok(eylem.get('res_model') == 'account.accrued.orders.wizard', "satırlardan tahakkuk fişi sihirbazı açılıyor")
w = env['account.accrued.orders.wizard'].with_context(**eylem['context']).create({'date': po.date_order.date()})
w.create_entries()
fis = satir.accrual_move_ids[:1]
ok(fis.state == 'posted' and abs(sum(fis.line_ids.filtered(lambda l: l.debit).mapped('debit')) - 60) < 0.01,
   f"tahakkuk fişi oluştu ve işlendi: 60 TL (iptali sonraki gün otomatik) — {fis.name}")
env.cr.rollback(); print("(geri alındı)")
