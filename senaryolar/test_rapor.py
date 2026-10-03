from datetime import date
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']; M = env['account.move']; c = env.company; A = env['account.account']
acc = lambda code: A.search([('code', '=', code)], limit=1)
mavi = P.create({'name': 'Mavi', 'is_company': True, 'atlas_cari_tipi': 'alici'})
kir = P.create({'name': 'Kırmızı', 'is_company': True, 'atlas_cari_tipi': 'satici'})
kdv20s = env['account.chart.template'].with_company(c).ref('tr_s_20')
kdv20p = env['account.chart.template'].with_company(c).ref('tr_p_20')
ac = M.create({'move_type': 'entry', 'atlas_fis_turu': 'acilis', 'date': date(2026,1,1), 'line_ids': [
    Command.create({'account_id': acc('100001').id, 'debit': 50000}), Command.create({'account_id': acc('500000').id, 'credit': 50000})]}); ac.action_post()
s1 = M.create({'move_type': 'out_invoice', 'partner_id': mavi.id, 'invoice_date': date(2026,3,10), 'invoice_line_ids': [Command.create({'name': 'Satış', 'quantity': 1, 'price_unit': 10000, 'tax_ids': [Command.set(kdv20s.ids)], 'account_id': acc('600000').id})]}); s1.action_post()
b1 = M.create({'move_type': 'in_invoice', 'partner_id': kir.id, 'invoice_date': date(2026,3,12), 'invoice_line_ids': [Command.create({'name': 'Kira', 'quantity': 1, 'price_unit': 3000, 'tax_ids': [Command.set(kdv20p.ids)], 'account_id': acc('770000').id})]}); b1.action_post()
mh = M.create({'move_type': 'entry', 'atlas_fis_turu': 'mahsup', 'date': date(2026,4,1), 'line_ids': [
    Command.create({'account_id': acc('653000').id, 'debit': 100}), Command.create({'account_id': acc('100001').id, 'credit': 100})]}); mh.action_post()

W = env['atlas.rapor.wizard']
def rep(**kw):
    w = W.create({'date_from': date(2026,1,1), 'date_to': date(2026,12,31), **kw}); return w, w._get_report()
w, m = rep(rapor_turu='mizan', seviye='3')
tot = m['rows'][-1]['cells']
ok(abs(tot[6] - tot[7]) < 0.01 and abs(tot[8] - tot[9]) < 0.01, f"mizan toplam borç = alacak ({tot[6]:,.2f}) ve borç bakiye = alacak bakiye ({tot[8]:,.2f})")
w, md = rep(rapor_turu='mizan', seviye='detay')
ok(any(r['style'] == 'group' and r['cells'][0] == '120' for r in md['rows']) and any(r['cells'][0] == mavi.ref for r in md['rows']), f"detay mizan: 120 ana hesap + {mavi.ref} alt hesap")
w, mv = rep(rapor_turu='muavin', hesap_baslangic='100', hesap_bitis='100')
last = [r for r in mv['rows'] if r['style'] == 'total'][0]['cells']
ok(last[7] == 49900 and last[8] == 'B', f"muavin 100 Kasa kapanış {last[7]:,.2f} {last[8]}")
w, y = rep(rapor_turu='yevmiye')
maddeler = [r['cells'][0] for r in y['rows'] if r['style'] == 'section']
ok(maddeler == [1, 2, 3, 4] and y['rows'][-1]['cells'][4] == y['rows'][-1]['cells'][5], f"yevmiye maddeleri {maddeler}")
w, g = rep(rapor_turu='gelir')
gt = {r['cells'][1]: r['cells'][2] for r in g['rows'] if r['style'] in ('group', 'total')}
ok(gt['BRÜT SATIŞLAR'] == 10000 and gt['FAALİYET GİDERLERİ (-)'] == -3000 and gt['DÖNEM NET KÂRI VEYA ZARARI'] == 6900, f"gelir tablosu net {gt['DÖNEM NET KÂRI VEYA ZARARI']:,.2f}")
w, g2 = rep(rapor_turu='gelir', yansitma_dahil=False)
ok({r['cells'][1]: r['cells'][2] for r in g2['rows']}['DÖNEM NET KÂRI VEYA ZARARI'] == 9900, "yansıtma hariç: 770 dahil edilmedi → 9.900")
w, b = rep(rapor_turu='bilanco', seviye='3')
totals = [r['cells'] for r in b['rows'] if r['style'] == 'total']
ok(abs(totals[0][2] - totals[1][2]) < 0.01 and 'UYARI' not in b['subtitle'], f"bilanço dengede: aktif {totals[0][2]:,.2f} = pasif {totals[1][2]:,.2f}")
w, ya = rep(rapor_turu='yaslandirma', cari_tipi='alici', date_to=date(2026,5,15))
ok(ya['rows'][0]['cells'][:2] == [mavi.ref, 'Mavi'] and ya['rows'][0]['cells'][-1] == 12000, "yaşlandırma: Mavi 12.000")
w, k = rep(rapor_turu='kdv')
kt = [r['cells'] for r in k['rows'] if r['style'] == 'total']
ok(kt[0][3] == 2000 and kt[1][3] == 600 and kt[2][3] == 1400 and kt[2][0] == 'ÖDENECEK VERGİ', f"KDV: hesaplanan {kt[0][3]}, indirilecek {kt[1][3]}, ödenecek {kt[2][3]}")
for rt in ('mizan','muavin','yevmiye','bilanco','gelir','yaslandirma','kdv'):
    w = W.create({'rapor_turu': rt, 'date_from': date(2026,1,1), 'date_to': date(2026,12,31)})
    html = env['ir.actions.report']._render_qweb_html('atlas_rapor.report_atlas_rapor', w.ids)[0]
    x = w._build_xlsx(w._get_report())
    assert x[:2] == b'PK' and len(html) > 1000, rt
ok(True, "7 rapor ekran (HTML) ve Excel çıktısı üretildi")
env.cr.rollback(); print("(geri alındı)")
