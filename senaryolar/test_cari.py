from datetime import date
from odoo.exceptions import ValidationError
from stdnum.tr import vkn
P = env['res.partner']; c = env.company
def accs(p): return [(a.code, a.account_type) for a in p.atlas_account_ids]
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA") , msg)

a = P.create({'name': 'Alıcı A.Ş.', 'is_company': True, 'atlas_cari_tipi': 'alici'})
ok(a.ref == '120-00-0001' and accs(a) == [('120-00-0001','asset_receivable')] and a.property_account_receivable_id.code == '120-00-0001', f"alıcı: {a.ref} {accs(a)}")
s = P.create({'name': 'Satıcı Ltd.', 'is_company': True, 'atlas_cari_tipi': 'satici'})
ok(s.ref == '320-00-0001' and s.property_account_payable_id.code == '320-00-0001', f"satıcı: {s.ref} {accs(s)}")
g = env['atlas.cari.grup'].create({'code': '01', 'name': 'Bayiler'})
b = P.create({'name': 'Bayi', 'is_company': True, 'atlas_cari_tipi': 'alici', 'atlas_cari_grup_id': g.id})
ok(b.ref == '120-01-0001', f"grup 01: {b.ref}")
m = P.create({'name': 'Manuel', 'is_company': True, 'atlas_cari_tipi': 'alici', 'ref': '120-00-0050'})
n = P.create({'name': 'Sonraki', 'is_company': True, 'atlas_cari_tipi': 'alici'})
ok(n.ref == '120-00-0051', f"manuel kod sonrası: {n.ref}")
a.atlas_cari_tipi = 'alici_satici'
ok(sorted(accs(a)) == [('120-00-0001','asset_receivable'),('320-00-0002','liability_payable')], f"alıcı+satıcı: {accs(a)}")
a.name = 'Alıcı Yeni Unvan A.Ş.'
ok(set(a.atlas_account_ids.mapped('name')) == {'Alıcı Yeni Unvan A.Ş.'}, "unvan hesaba yansıdı")
for bad in [dict(ref='120-00-0001'), dict(ref='320-00-0099'), dict(ref='ABC')]:
    try:
        with env.cr.savepoint(): P.create({'name': 'x', 'is_company': True, 'atlas_cari_tipi': 'alici', **bad}); ok(False, f"reddedilmedi {bad}")
    except ValidationError as e: ok(True, f"reddedildi {bad['ref']}: {str(e).splitlines()[0][:70]}")
good_vkn = next(f"{i:09d}{d}" for i in range(123456789, 123456999) for d in range(10) if vkn.is_valid(f"{i:09d}{d}"))
try:
    with env.cr.savepoint(): P.create({'name': 'y', 'country_id': env.ref('base.tr').id, 'vat': '1234567891'}); ok(False, "geçersiz VKN kabul edildi")
except ValidationError: ok(True, "geçersiz VKN reddedildi")
v = P.create({'name': 'z', 'country_id': env.ref('base.tr').id, 'vat': good_vkn}); ok(True, f"geçerli VKN kabul: {good_vkn}")
k = P.create({'name': 'Ahmet', 'parent_id': a.id}); ok(not k.ref and k.atlas_cari_tipi == 'alici_satici' and not k.atlas_account_ids, "alt kontak: kod/hesap yok, tip ticari cariden")

yeni = P.create({'name': 'Tipsiz Müşteri', 'is_company': True})
tax = env['account.tax'].search([('type_tax_use','=','sale'),('amount','=',20),('amount_type','=','percent')], limit=1)
inv = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': yeni.id, 'invoice_date': date(2026,9,10), 'ref': 'FTR-001',
    'invoice_line_ids': [(0,0,{'name': 'Hizmet', 'quantity': 1, 'price_unit': 1000, 'tax_ids': [(6,0,tax.ids)]})]})
inv.action_post()
rl = inv.line_ids.filtered(lambda l: l.display_type == 'payment_term')
ok(yeni.atlas_cari_tipi == 'alici' and rl.account_id.code == yeni.ref, f"otomatik cari: {yeni.ref}, fatura alacak satırı {rl.account_id.code}, toplam {inv.amount_total}")
bill = env['account.move'].create({'move_type': 'in_invoice', 'partner_id': yeni.id, 'invoice_date': date(2026,9,12), 'ref': 'ALS-77',
    'invoice_line_ids': [(0,0,{'name': 'Malzeme', 'quantity': 1, 'price_unit': 200})]})
bill.action_post()
bl = bill.line_ids.filtered(lambda l: l.display_type == 'payment_term')
ok(yeni.atlas_cari_tipi == 'alici_satici' and bl.account_id.code.startswith('320-') and bill.date == date(2026,9,12), f"alış faturası: tip {yeni.atlas_cari_tipi}, borç satırı {bl.account_id.code}, tarih {bill.date}")
pay = env['account.payment.register'].with_context(active_model='account.move', active_ids=inv.ids).create({'payment_date': date(2026,9,20), 'amount': 500})._create_payments()
yeni2 = P.create({'name': 'Direkt Ödeme Tedarikçi', 'is_company': True})
p2 = env['account.payment'].create({'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': yeni2.id, 'amount': 300, 'date': date(2026,9,21), 'journal_id': env['account.journal'].search([('type','=','bank')], limit=1).id})
p2.action_post()
ok(yeni2.atlas_cari_tipi == 'satici' and p2.destination_account_id.code == yeni2.ref, f"ödeme ile otomatik satıcı: {yeni2.ref}, karşı hesap {p2.destination_account_id.code}")

env.flush_all()
H = env['atlas.cari.hareket']
yeni.invalidate_recordset()
ok(round(yeni.atlas_bakiye,2) == 1200 - 500 - 200, f"kart bakiyesi: borç {yeni.atlas_borc} alacak {yeni.atlas_alacak} bakiye {yeni.atlas_bakiye}")
w = env['atlas.cari.ekstre.wizard'].create({'partner_ids': [(6,0,[yeni.id, yeni2.id, a.id])], 'date_from': date(2026,9,15), 'date_to': date(2026,9,30)})
d = w._get_ekstre_data()
ok(len(d) == 2 and d[0]['devir'] == 1000.0, f"devir 15.09 öncesi (1.200 - 200 = {d[0]['devir']}), hareketsiz cari gizlendi")
xlsx = w._build_xlsx(); ok(xlsx[:2] == b'PK', f"Excel üretildi ({len(xlsx)} bayt)")
html = env['ir.actions.report']._render_qweb_html('atlas_cari.report_cari_ekstre', w.ids)[0]
ok(b'CAR\xc4\xb0 HESAP EKSTRES\xc4\xb0' in html and b'DEV\xc4\xb0R' in html, f"HTML rapor render ({len(html)} bayt)")
z = P.create({'name': 'Silinecek', 'is_company': True, 'atlas_cari_tipi': 'alici'}); zacc = z.atlas_account_ids
z.unlink(); ok(not zacc.exists(), "hareketsiz cari alt hesabıyla silindi")
env.cr.rollback(); print("(geri alındı)")
