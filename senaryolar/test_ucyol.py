from odoo import fields
from odoo.exceptions import UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
sirket = env.company
tedarikci = env['res.partner'].create({'name': 'Eşleştirme Tedarikçisi'})
mal = env['product.product'].create({'name': 'Eşleştirme Malı', 'type': 'consu', 'is_storable': True, 'purchase_method': 'purchase',
                                     'standard_price': 100})
hizmet = env['product.product'].create({'name': 'Eşleştirme Hizmeti', 'type': 'service', 'purchase_method': 'purchase'})
po = env['purchase.order'].create({'partner_id': tedarikci.id, 'order_line': [
    (0, 0, {'product_id': mal.id, 'product_qty': 10, 'price_unit': 100, 'tax_ids': [(5, 0, 0)]}),
    (0, 0, {'product_id': hizmet.id, 'product_qty': 1, 'price_unit': 500, 'tax_ids': [(5, 0, 0)]})]})
po.button_confirm()
mal_satir = po.order_line.filtered(lambda l: l.product_id == mal)


def teslim_al(miktar):
    toplama = po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))[:1]
    hareket = toplama.move_ids.filtered(lambda m: m.product_id == mal)
    hareket.quantity = miktar
    hareket.picked = True
    toplama.with_context(skip_backorder=False)._action_done()


po.action_create_invoice()
fatura = po.invoice_ids
fatura.invoice_date = fields.Date.today()
s_mal = fatura.invoice_line_ids.filtered(lambda l: l.product_id == mal)
s_hiz = fatura.invoice_line_ids.filtered(lambda l: l.product_id == hizmet)
ok(s_mal.quantity == 10 and s_mal.ucyol_durum == 'hayir' and s_hiz.ucyol_durum == 'evet' and fatura.ucyol_durum == 'hayir',
   "teslim alınmadan: mal satırı bekliyor, sipariş bazlı hizmet ödenebilir; fatura bekliyor")
teslim_al(6)
ok(mal_satir.qty_received == 6 and fatura.ucyol_durum == 'hayir' and 'Teslim alınan 6' in s_mal.ucyol_aciklama, "kısmi teslim: hâlâ bekliyor")
teslim_al(4)
ok(mal_satir.qty_received == 10 and s_mal.ucyol_durum == 'evet' and fatura.ucyol_durum == 'evet', "tam teslim: ödenebilir (mal kabul sonrası kendiliğinden)")

s_mal.price_unit = 110
ok(s_mal.ucyol_durum == 'istisna' and fatura.ucyol_durum == 'istisna', "fiyat farkı: istisna")
sirket.ucyol_fiyat_tolerans = 15
ok(s_mal.ucyol_durum == 'evet', "fiyat toleransı içinde ödenebilir")
s_mal.price_unit = 100
fatura.action_post()
ok(fatura.state == 'posted' and fatura.ucyol_durum == 'evet', "onaylı fatura ödenebilir")

# fazla faturalama
fatura2 = env['account.move'].create({'move_type': 'in_invoice', 'partner_id': tedarikci.id, 'invoice_date': fields.Date.today(),
                                      'invoice_line_ids': [(0, 0, {'product_id': mal.id, 'quantity': 3, 'price_unit': 100,
                                                                   'purchase_line_id': mal_satir.id, 'tax_ids': [(5, 0, 0)]})]})
ok(fatura2.invoice_line_ids.ucyol_durum == 'istisna' and fatura2.ucyol_durum == 'istisna' and 'sipariş 10' in fatura2.invoice_line_ids.ucyol_aciklama,
   "sipariş miktarını aşan ikinci fatura: istisna")
sirket.ucyol_miktar_tolerans = 30
ok(fatura2.ucyol_durum == 'hayir', "miktar toleransı içinde: istisna değil, teslim alınandan fazla olduğu için bekliyor")
sirket.ucyol_miktar_tolerans = 0
iade = env['account.move'].create({'move_type': 'in_refund', 'partner_id': tedarikci.id, 'invoice_date': fields.Date.today(),
                                   'invoice_line_ids': [(0, 0, {'product_id': mal.id, 'quantity': 3, 'price_unit': 100,
                                                                'purchase_line_id': mal_satir.id, 'tax_ids': [(5, 0, 0)]})]})
iade.action_post()
ok(fatura2.invoice_line_ids.ucyol_durum == 'evet', "iade faturalanan miktarı düşer; ikinci fatura artık uygun")

# elle karar ve ödeme engeli
siparissiz = env['account.move'].create({'move_type': 'in_invoice', 'partner_id': tedarikci.id, 'invoice_date': fields.Date.today(),
                                         'invoice_line_ids': [(0, 0, {'name': 'Kargo', 'quantity': 1, 'price_unit': 50, 'tax_ids': [(5, 0, 0)]})]})
ok(siparissiz.ucyol_durum == 'evet' and not siparissiz.ucyol_siparisli, "siparişsiz fatura ödenebilir")
fatura2.write({'invoice_line_ids': [(1, fatura2.invoice_line_ids.id, {'price_unit': 150})]})
fatura2.action_post()
ok(fatura2.ucyol_durum == 'istisna', "istisnalı fatura")
sirket.ucyol_odeme_engeli = True
try:
    fatura2.action_register_payment(); engel = False
except UserError:
    engel = True
ok(engel, "ödeme engeli: istisnalı faturaya ödeme kaydedilemez")
fatura2.action_ucyol_serbest()
ok(fatura2.ucyol_durum == 'evet' and fatura2.ucyol_hesaplanan == 'istisna' and fatura2.ucyol_elle == 'evet', "elle serbest bırak")
eylem = fatura2.action_register_payment()
ok(eylem.get('res_model') == 'account.payment.register', "serbest bırakılan faturaya ödeme kaydı açılır")
fatura.action_ucyol_beklet()
ok(fatura.ucyol_durum == 'hayir', "elle beklet")
fatura.action_ucyol_otomatik()
ok(fatura.ucyol_durum == 'evet' and not fatura.ucyol_elle, "otomatik duruma dön")
musteri_faturasi = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': tedarikci.id,
                                               'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 1})]})
ok(not musteri_faturasi.ucyol_durum, "müşteri faturalarında eşleştirme yok")
env.cr.rollback(); print("(geri alındı)")
