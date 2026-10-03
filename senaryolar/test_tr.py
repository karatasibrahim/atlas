from datetime import date
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; M = env['account.move']; P = env['res.partner']
ref = lambda x: env['account.chart.template'].with_company(c).ref(x)
code = lambda a: a.with_company(c).code
lines = lambda m: sorted((code(l.account_id), round(l.balance, 2)) for l in m.line_ids)
A = env['account.account'].with_context(lang='tr_TR')
ok(A.search([('code', '=', '391004')]).name == 'TEVKİF EDİLEN KDV (SATIŞ)' and A.search([('code', '=', '540000')]).name == 'YASAL YEDEKLER', "hesap adları Türkçe")
ok(env['atlas.gib.kod'].search_count([]) == 40, f"GİB kodları: {env['atlas.gib.kod'].search_count([])}")
fps = env['account.fiscal.position'].with_context(lang='tr_TR').search([])
print("   mali koşullar:", [(f.name, f.atlas_gib_kod_id.kod) for f in fps])
ok(c.display_invoice_amount_total_words and code(c.downpayment_account_id) == '340000' and code(c.account_discount_income_allocation_id) == '611000', "fatura ayarları: yazıyla tutar, 340 avans, 611 iskonto")

ted = P.create({'name': 'Hizmet Tedarikçisi', 'is_company': True})
mus = P.create({'name': 'Yurtdışı Müşteri', 'is_company': True})
def inv(mt, p, amount, taxes, d=date(2026, 9, 10), **kw):
    m = M.create({'move_type': mt, 'partner_id': p.id, 'invoice_date': d, **kw,
                  'invoice_line_ids': [Command.create({'name': 'Kalem', 'quantity': 1, 'price_unit': amount, 'tax_ids': [Command.set(taxes.ids)]})]})
    m.action_post(); return m
b = inv('in_invoice', ted, 1000, ref('tr_p_vat_wh_20_5_10'))
print("   tevkifatlı alış:", lines(b))
ok(('770000', 1000.0) in lines(b), "ürünsüz alış satırı 770'e (150 değil)")
ok(('360001', -100.0) in lines(b) and ('191000', 200.0) in lines(b) and b.amount_residual == 1100, "alış tevkifatı 5/10: 191 +200, 360001 -100, satıcıya 1.100")
k = inv('in_invoice', ted, 10000, ref('tr_pr_wh_20'))
print("   kira stopajı:", lines(k))
ok(('360002', -2000.0) in lines(k) and k.amount_residual == 8000, "kira stopajı 360002'ye, ödenecek 8.000")
s = inv('out_invoice', mus, 1000, ref('tr_s_wh_20_5_10'))
ok(('391001', -200.0) in lines(s) and ('391004', 100.0) in lines(s) and s.amount_residual == 1100, f"satış tevkifatı: {lines(s)}")
fp_ihr = fps.filtered(lambda f: f.atlas_gib_kod_id.kod == '301')
urun = env['product.product'].create({'name': 'İhraç Ürünü', 'type': 'consu'})
draft = M.create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 9, 10), 'fiscal_position_id': fp_ihr.id,
                  'invoice_line_ids': [Command.create({'product_id': urun.id, 'quantity': 1, 'price_unit': 1000})]})
tax = draft.invoice_line_ids.tax_ids
ok(tax.amount == 0 and tax.atlas_gib_kod_id.kod == '301' and draft.amount_total == 1000, f"ihracat mali koşulu: %20 → {tax.name}")
fp_kay = fps.filtered(lambda f: f.atlas_gib_kod_id.kod == '701')
d2 = M.create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 9, 10), 'fiscal_position_id': fp_kay.id,
               'invoice_line_ids': [Command.create({'product_id': urun.id, 'quantity': 1, 'price_unit': 1000})]})
d2.action_post()
ok(d2.amount_residual == 1000 and d2.invoice_line_ids.tax_ids.atlas_gib_kod_id.kod == '701', f"ihraç kayıtlı: KDV tahsil edilmiyor, alacak {d2.amount_residual}: {lines(d2)}")

# belge bazında kur tipi
usd = env.ref('base.USD')
r = env['res.currency.rate'].search([('currency_id', '=', usd.id), ('name', '=', date(2026, 9, 24))])
print(f"   24.09 TCMB USD: döviz alış {r.atlas_forex_buying}, döviz satış {r.atlas_forex_selling}")
mus.atlas_satis_kur_tipi = 'forex_selling'
f1 = M.create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 9, 25), 'currency_id': usd.id,
               'invoice_line_ids': [Command.create({'name': 'USD satış', 'quantity': 1, 'price_unit': 100, 'tax_ids': False})]})
ok(f1.atlas_kur_tipi == 'forex_selling' and abs(f1.amount_total_signed - 100 * r.atlas_forex_selling) < 0.01, f"cari varsayılanı döviz satış: 100 USD = {f1.amount_total_signed} TL")
f1.atlas_kur_tipi = 'forex_buying'
ok(abs(f1.amount_total_signed - 100 * r.atlas_forex_buying) < 0.01, f"faturada döviz alışa çevrilince: {f1.amount_total_signed} TL")
f2 = M.create({'move_type': 'in_invoice', 'partner_id': ted.id, 'invoice_date': date(2026, 9, 25), 'currency_id': usd.id,
               'invoice_line_ids': [Command.create({'name': 'USD alış', 'quantity': 1, 'price_unit': 100, 'tax_ids': False})]})
ok(f2.atlas_kur_tipi == c.atlas_tcmb_rate_type, f"alışta şirket varsayılanı ({f2.atlas_kur_tipi}): {f2.amount_total_signed} TL")
env.cr.rollback(); print("(geri alındı)")
