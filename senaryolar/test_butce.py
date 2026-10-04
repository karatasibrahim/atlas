from datetime import date
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; M = env['account.move']; B = env['atlas.butce']
acc = lambda code: env['account.account'].search([('code', '=', code), ('company_ids', 'in', c.root_id.id)], limit=1)
B.search([('yil', 'in', (2026, 2027))]).write({'durum': 'kapali'})
ted = env['res.partner'].create({'name': 'BTC Tedarikçi', 'is_company': True})
mus = env['res.partner'].create({'name': 'BTC Müşteri', 'is_company': True})
def fatura(mt, partner, tarih, tutar, hesap, analitik=None):
    m = M.create({'move_type': mt, 'partner_id': partner.id, 'invoice_date': tarih, 'date': tarih, 'invoice_line_ids': [Command.create({
        'name': 'Kalem', 'quantity': 1, 'price_unit': tutar, 'tax_ids': False, 'account_id': acc(hesap).id,
        'analytic_distribution': {str(analitik.id): 100} if analitik else False})]})
    m.action_post(); return m
b = B.create({'name': 'BTC 2026 Bütçe', 'yil': 2026, 'asim_kontrolu': 'uyari', 'satir_ids': [
    Command.create({'hesap_kodu': '770', **{f'ay{i:02d}': 1000 for i in range(1, 13)}}),
    Command.create({'hesap_kodu': '600', **{f'ay{i:02d}': 5000 for i in range(1, 13)}})]})
s770, s600 = b.satir_ids.sorted('hesap_kodu')[1], b.satir_ids.sorted('hesap_kodu')[0]
ok(s770.toplam == 12000 and s770.yon == 'borc' and s600.yon == 'alacak' and s770.name, f"kalemler: {s770.hesap_kodu} {s770.name} 12.000 (gider), 600 gelir")
taban770, taban600 = s770.gerceklesen, s600.gerceklesen
fatura('in_invoice', ted, date(2026, 3, 15), 3000, '770000')
fatura('out_invoice', mus, date(2026, 2, 10), 20000, '600000')
b.invalidate_recordset(); s770.invalidate_recordset(); s600.invalidate_recordset()
ok(s770.gerceklesen - taban770 == 3000 and s600.gerceklesen - taban600 == 20000, "gerçekleşen: 770 +3.000, 600 +20.000 (gelir pozitif)")
kp = M.create({'move_type': 'entry', 'atlas_fis_turu': 'kapanis', 'date': date(2026, 12, 31), 'line_ids': [
    Command.create({'account_id': acc('770000').id, 'credit': 3000}), Command.create({'account_id': acc('690000').id, 'debit': 3000})]})
kp.action_post(); s770.invalidate_recordset()
ok(s770.gerceklesen - taban770 == 3000, "kapanış fişi gerçekleşene katılmadı")
b.action_onayla()
w = env['atlas.rapor.wizard'].create({'rapor_turu': 'butce', 'butce_id': b.id, 'date_from': date(2026, 1, 1), 'date_to': date(2026, 3, 31)})
r = w._get_report()
satir = {row['cells'][0]: row['cells'] for row in r['rows'] if row['style'] == 'detail'}
ok(satir['770'][2] == 3000 and satir['600'][2] == 15000 and r['title'] == 'Bütçe - Gerçekleşen', "rapor 1. çeyrek: 770 bütçe 3.000, 600 bütçe 15.000")
ok(any(row['cells'][1] == 'NET (GELİR - GİDER)' for row in r['rows']), "net satırı")
html = env['ir.actions.report']._render_qweb_html('atlas_rapor.report_atlas_rapor', w.ids)[0]
ok(w._build_xlsx(r)[:2] == b'PK' and 'Bütçe - Gerçekleşen'.encode() in html, "ekran ve Excel çıktısı")
try:
    with env.cr.savepoint(): env['atlas.rapor.wizard'].create({'rapor_turu': 'butce', 'butce_id': b.id, 'date_from': date(2025, 1, 1), 'date_to': date(2026, 3, 31)})._get_report(); hata = False
except UserError: hata = True
ok(hata, "bütçe yılı dışındaki tarih aralığı reddedildi")
kalan = 12000 - (s770.gerceklesen) + 1
f = fatura('in_invoice', ted, date(2026, 4, 1), kalan, '770000')
ok('Bütçe aşımı' in (f.message_ids[:1].body or ''), "aşımda uyarı mesajı (fatura onaylandı)")
b.asim_kontrolu = 'engelle'
try:
    with env.cr.savepoint(): fatura('in_invoice', ted, date(2026, 4, 2), 100, '770000'); hata = False
except UserError as e: hata = 'Bütçe aşımı' in str(e)
ok(hata, "engelle modunda aşan fatura onaylanmadı")
beklenen_mart = round(s770._gerceklesen_aylik(2026)[2] * 1.1, 2)
b2 = B.browse(b.action_sonraki_yil()['res_id'])
ok(b2.yil == 2027 and b2.name == 'BTC 2027 Bütçe' and b2.durum == 'taslak' and len(b2.satir_ids) == 2, f"sonraki yıla kopya: {b2.name}")
b2.write({'artis_orani': 10}); b2.action_gerceklesenden_doldur()
k770 = b2.satir_ids.filtered(lambda s: s.hesap_kodu == '770')
mart = k770.ay03
ok(round(mart, 2) == beklenen_mart and mart >= 3300, f"geçen yıldan %10 artışla dolduruldu: Mart {mart:,.2f}")
b.action_kapat()
an_plan = env['account.analytic.plan'].create({'name': 'BTC Projeler'})
proje = env['account.analytic.account'].create({'name': 'BTC Proje A', 'plan_id': an_plan.id})
bp = B.create({'name': 'BTC Proje Bütçesi', 'yil': 2026, 'analytic_account_id': proje.id, 'asim_kontrolu': 'yok',
               'satir_ids': [Command.create({'hesap_kodu': '770', 'ay05': 1000})]})
fatura('in_invoice', ted, date(2026, 5, 3), 400, '770000', proje)
fatura('in_invoice', ted, date(2026, 5, 4), 900, '770000')
bp.satir_ids.invalidate_recordset()
ok(bp.satir_ids.gerceklesen == 400 and round(bp.satir_ids.oran) == 40, "analitik bütçe yalnızca projeye dağıtılan 400'ü saydı (%40)")
env.cr.rollback(); print("(geri alındı)")
