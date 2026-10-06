from odoo import fields
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
A = env.company
B = env['res.company'].create({'name': 'Atlas Grup Lojistik A.Ş.', 'currency_id': A.currency_id.id, 'country_id': A.country_id.id})
env['account.chart.template'].try_loading(A.chart_template or 'tr', B, install_demo=False)
env.user.company_ids |= B
if not env['stock.warehouse'].search_count([('company_id', '=', B.id)]):
    env['stock.warehouse'].create({'name': 'Lojistik Depo', 'code': 'LJS', 'company_id': B.id})
urun = env['product.product'].create({'name': 'Grup İçi Hizmet', 'type': 'consu', 'list_price': 100, 'standard_price': 60, 'company_id': False})
yetkili = env['res.partner'].create({'name': 'Lojistik Satın Alma', 'parent_id': B.partner_id.id, 'type': 'invoice'})
vergi_a = env['account.tax'].search([('company_id', '=', A.id), ('type_tax_use', '=', 'sale'), ('amount', '=', 20)], limit=1)
ok(B.chart_template and env['account.journal'].search_count([('company_id', '=', B.id), ('type', '=', 'purchase')])
   and env['stock.warehouse'].search_count([('company_id', '=', B.id)]), "ikinci grup şirketi: hesap planı, yevmiye, depo")


def fatura(tur, partner, fiyat=1000, adet=2):
    m = env['account.move'].with_company(A).create({
        'move_type': tur, 'partner_id': partner.id, 'invoice_date': fields.Date.today(),
        'invoice_line_ids': [(0, 0, {'product_id': urun.id, 'quantity': adet, 'price_unit': fiyat,
                                     'tax_ids': [(6, 0, vergi_a.ids if tur.startswith('out') else [])]})]})
    m.action_post()
    return m


# ---------------------------------------------------------------- kural kapalıyken
f0 = fatura('out_invoice', B.partner_id)
ok(not f0.sa_karsilik_ids, "kural kapalıyken karşılık oluşmaz")

# ---------------------------------------------------------------- fatura → tedarikçi faturası
B.write({'sa_fatura': True, 'sa_fatura_durum': 'taslak'})
f1 = fatura('out_invoice', yetkili)
k1 = f1.sa_karsilik_ids
ok(len(k1) == 1 and k1.company_id == B and k1.move_type == 'in_invoice' and k1.partner_id == A.partner_id and k1.state == 'draft',
   "müşteri faturası (alt kişiye) → karşı şirkette taslak tedarikçi faturası")
ok(k1.ref == f1.name and k1.invoice_line_ids.quantity == 2 and k1.invoice_line_ids.price_unit == 1000
   and k1.invoice_line_ids.tax_ids and k1.invoice_line_ids.tax_ids.company_id == B and k1.invoice_line_ids.tax_ids.type_tax_use == 'purchase',
   "satırlar, referans ve karşı şirketin alış vergisi")
ok(f1.currency_id.compare_amounts(k1.amount_total, f1.amount_total) == 0, "tutarlar eşit")
B.sa_fatura_durum = 'onayli'
f2 = fatura('out_refund', B.partner_id, fiyat=300, adet=1)
ok(f2.sa_karsilik_ids.move_type == 'in_refund' and f2.sa_karsilik_ids.state == 'posted', "iade → onaylı tedarikçi iadesi")
f3 = fatura('in_invoice', B.partner_id, fiyat=500, adet=3)
ok(f3.sa_karsilik_ids.move_type == 'out_invoice' and f3.sa_karsilik_ids.company_id == B and f3.sa_karsilik_ids.partner_id == A.partner_id,
   "tedarikçi faturası → karşı şirkette müşteri faturası")
A.write({'sa_fatura': True})
k1.with_company(B).action_post()
ok(not f3.sa_karsilik_ids.sa_karsilik_ids and not k1.sa_karsilik_ids, "oluşan belge geri dönüp yeni belge doğurmaz (döngü yok)")
musteri = env['res.partner'].create({'name': 'Dış Müşteri'})
ok(not fatura('out_invoice', musteri).sa_karsilik_ids, "grup dışı müşteriye kural uygulanmaz")

# ---------------------------------------------------------------- satış → satın alma
B.write({'sa_satin_alma_olustur': True, 'sa_otomatik_onay': True})
so = env['sale.order'].with_company(A).create({'partner_id': B.partner_id.id, 'order_line': [(0, 0, {'product_id': urun.id, 'product_uom_qty': 5, 'price_unit': 120, 'discount': 10})]})
so.action_confirm()
po = so.sa_satin_alma_ids
ok(len(po) == 1 and po.company_id == B and po.partner_id == A.partner_id and po.state == 'purchase' and po.partner_ref == so.name,
   "satış siparişi → karşı şirkette onaylı satın alma siparişi")
ok(po.order_line.product_qty == 5 and abs(po.order_line.price_unit - 108) < 0.001 and po.picking_type_id.company_id == B,
   "miktar, iskontolu fiyat, karşı şirketin giriş operasyonu")
ok(not po.sa_satis_ids, "oluşan satın alma geri satış doğurmaz")

# ---------------------------------------------------------------- satın alma → satış
B.write({'sa_satis_olustur': True, 'sa_otomatik_onay': False})
A.write({'sa_satin_alma_olustur': True})
po2 = env['purchase.order'].with_company(A).create({'partner_id': B.partner_id.id, 'order_line': [(0, 0, {
    'product_id': urun.id, 'product_qty': 7, 'price_unit': 95, 'date_planned': fields.Datetime.now()})]})
po2.button_confirm()
so2 = po2.sa_satis_ids
ok(len(so2) == 1 and so2.company_id == B and so2.partner_id == A.partner_id and so2.state == 'draft' and so2.client_order_ref == po2.name,
   "satın alma siparişi → karşı şirkette taslak satış siparişi")
ok(so2.order_line.product_uom_qty == 7 and so2.order_line.price_unit == 95 and so2.warehouse_id.company_id == B, "fiyat korunur, karşı şirket deposu")
so2.with_company(B).action_confirm()
ok(not so2.sa_satin_alma_ids, "oluşan satış onaylanınca kaynak şirkette yeniden satın alma oluşmaz")

# ---------------------------------------------------------------- oluşturan kullanıcı
B.sa_kullanici_id = env.ref('base.user_admin')
env.ref('base.user_admin').company_ids |= B
so3 = env['sale.order'].with_company(A).create({'partner_id': B.partner_id.id, 'order_line': [(0, 0, {'product_id': urun.id, 'product_uom_qty': 1})]})
so3.action_confirm()
ok(so3.sa_satin_alma_ids.create_uid == env.ref('base.user_admin'), "belgeler seçilen kullanıcı adına oluşur")

env.cr.rollback(); print("(geri alındı)")
