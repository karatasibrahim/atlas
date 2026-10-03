from datetime import date
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']; M = env['account.move']; c = env.company; A = env['account.account']; J = env['account.journal']
acc = lambda code: A.search([('code', '=', code)], limit=1)
usd = env.ref('base.USD')
R = env['res.currency.rate']
R.create([{'currency_id': usd.id, 'name': date(2025,6,9), 'rate': 1/40.0, 'company_id': c.id},
          {'currency_id': usd.id, 'name': date(2025,12,31), 'rate': 1/45.0, 'company_id': c.id}])
mavi = P.create({'name': 'Mavi', 'is_company': True, 'atlas_cari_tipi': 'alici', 'atlas_satis_kur_tipi': False})
kir = P.create({'name': 'Kırmızı', 'is_company': True, 'atlas_cari_tipi': 'satici'})
k_usd = J.create({'name': 'USD Kasa', 'code': 'KUSD', 'type': 'cash', 'currency_id': usd.id})
post = lambda m: (m.action_post(), m)[1]
post(M.create({'move_type': 'entry', 'atlas_fis_turu': 'acilis', 'date': date(2025,1,1), 'line_ids': [
    Command.create({'account_id': acc('100001').id, 'debit': 100000}), Command.create({'account_id': acc('500000').id, 'credit': 100000})]}))
inv = lambda mt, p, amt, d, cur=None, account='600000': post(M.create({'move_type': mt, 'partner_id': p.id, 'invoice_date': d, 'currency_id': (cur or c.currency_id).id,
    'invoice_line_ids': [Command.create({'name': 'K', 'quantity': 1, 'price_unit': amt, 'tax_ids': False, 'account_id': acc(account).id})]}))
inv('out_invoice', mavi, 50000, date(2025,5,1))
fusd = inv('out_invoice', mavi, 1000, date(2025,6,10), usd)
ok(fusd.amount_total_signed == 40000, f"USD fatura 1000 USD = {fusd.amount_total_signed} TL (kur 40; elle girilen kurda TCMB tipi yok → Odoo kuru)")
env['account.payment.register'].with_context(active_model='account.move', active_ids=fusd.ids).create({'journal_id': k_usd.id, 'amount': 500, 'currency_id': usd.id, 'payment_date': date(2025,7,1)})._create_payments()
inv('in_invoice', kir, 10000, date(2025,8,1), account='770000')

SK = env['atlas.sabit.kiymet']
base = {'account_id': acc('255000').id, 'birikmis_account_id': acc('257000').id, 'gider_account_id': acc('770000').id}
laptop = SK.create({**base, 'name': 'Dizüstü', 'edinme_tarihi': date(2025,3,15), 'bedel': 60000, 'faydali_omur': 3})
oto = SK.create({**base, 'account_id': acc('254000').id, 'name': 'Binek Oto', 'edinme_tarihi': date(2025,10,1), 'bedel': 120000, 'faydali_omur': 5, 'kist': True})
makine = SK.create({**base, 'account_id': acc('253000').id, 'name': 'Makine', 'edinme_tarihi': date(2025,1,10), 'bedel': 100000, 'faydali_omur': 5, 'yontem': 'azalan', 'periyot': 'aylik'})
(laptop | oto | makine).action_aktif()
ok([l.tutar for l in laptop.line_ids] == [20000, 20000, 20000], f"normal plan: {[l.tutar for l in laptop.line_ids]}")
ok([l.tutar for l in oto.line_ids] == [6000, 24000, 24000, 24000, 24000, 18000], f"kıst plan: {[(l.yil, l.tutar) for l in oto.line_ids]}")
ok([l.tutar for l in makine.line_ids] == [40000, 24000, 14400, 8640, 12960], f"azalan bakiyeler plan: {[l.tutar for l in makine.line_ids]}")
W = env['atlas.amortisman.wizard']
W.create({'date': date(2025,6,30)}).action_kaydet()
ok(makine.line_ids[0].kaydedilen == 20000 and laptop.line_ids[0].kaydedilen == 0, f"Haziran (aylık makine 6/12 = {makine.line_ids[0].kaydedilen}; yıllık dizüstü kaydedilmedi)")
am = M.browse(W.create({'date': date(2025,12,31)}).action_kaydet()['res_id'])
ok(laptop.birikmis == 20000 and oto.birikmis == 6000 and makine.birikmis == 40000, f"yıl sonu amortisman {am.name}")
try: W.create({'date': date(2025,12,31)}).action_kaydet(); ok(False, "mükerrer amortisman")
except UserError: ok(True, "aynı dönem ikinci kez amortisman ayrılmaz")

kd = env['atlas.kur.degerleme.wizard'].create({'date': date(2025,12,31)}); kd.action_hesapla()
ok(kd.toplam_kar == 5000 and kd.toplam_zarar == 0 and not kd.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_cash').partner_id,
   f"kur kârı {kd.toplam_kar} (kasa 500 USD +2.500 hesap bazında, alacak 500 USD +2.500 cari bazında)")
kd_moves = M.search(kd.action_olustur()['domain'])
ok(len(kd_moves) == 2 and set(kd_moves.mapped('date')) == {date(2025,12,31), date(2026,1,1)}, "değerleme fişi + 01.01.2026 ters kayıt")
fusd.invalidate_recordset(); ok(fusd.payment_state == 'partial', f"açık fatura etkilenmedi: {fusd.payment_state}")

y = env['atlas.yansitma.wizard'].create({'date': date(2025,12,31)}); ym = M.browse(y.action_yansit()['res_id'])
ok(sorted((l.account_id.code, l.balance) for l in ym.line_ids) == [('632000', 76000.0), ('771000', -76000.0)], f"yansıtma: {[(l.account_id.code, l.balance) for l in ym.line_ids]}")
post(M.create({'move_type': 'entry', 'atlas_fis_turu': 'mahsup', 'date': date(2025,12,31), 'ref': 'Kurumlar vergisi karşılığı', 'line_ids': [
    Command.create({'account_id': acc('691000').id, 'debit': 3800}), Command.create({'account_id': acc('370000').id, 'credit': 3800})]}))

Rw = env['atlas.rapor.wizard']
g = Rw.create({'rapor_turu': 'gelir', 'date_from': date(2025,1,1), 'date_to': date(2025,12,31)})._get_report()
gt = {r['cells'][1]: r['cells'][2] for r in g['rows'] if r['style'] in ('group', 'total')}
b0 = Rw.create({'rapor_turu': 'bilanco', 'date_to': date(2025,12,31), 'seviye': '2'})._get_report()
bt0 = [r['cells'][2] for r in b0['rows'] if r['style'] == 'total']

K = env['atlas.donem.kapanis'].create({'yil': 2025})
K.action_kapat()
ok(K.state == 'done' and K.net_sonuc == gt['DÖNEM NET KÂRI VEYA ZARARI'] == 15200, f"kapanış: net sonuç {K.net_sonuc} = gelir tablosu {gt['DÖNEM NET KÂRI VEYA ZARARI']}")
env.flush_all()
def bakiye(code_prefix, d, extra=[]):
    return sum(env['account.move.line'].search([('parent_state','=','posted'), ('date','<=',d), ('account_id.code','=like', code_prefix+'%')] + extra).mapped('balance'))
ok(bakiye('59', date(2026,1,1)) == -K.net_sonuc, f"590 dönem net kârı açılışta {-bakiye('59', date(2026,1,1))}")
allbs = sum(abs(bakiye(str(x), date(2025,12,31))) for x in range(1, 10))
ok(allbs == 0, f"31.12.2025 kapanış sonrası tüm hesaplar sıfır (toplam mutlak {allbs})")
ok(bakiye('100001', date(2026,1,1)) == bakiye('100001', date(2025,12,31), [('move_id.atlas_fis_turu','!=','kapanis')]), "açılışta kasa bakiyesi geri geldi")
fusd.invalidate_recordset(); ok(fusd.payment_state == 'partial' and fusd.amount_residual == 500, "kapanış/açılış açık faturaları bozmadı")
b1 = Rw.create({'rapor_turu': 'bilanco', 'date_to': date(2025,12,31), 'seviye': '2'})._get_report()
bt1 = [r['cells'][2] for r in b1['rows'] if r['style'] == 'total']
ok(bt1 == bt0 and abs(bt1[0] - bt1[1]) < 0.01, f"bilanço (kapanış hariç) kapanıştan önce ve sonra aynı ve dengede: {bt1}")
m26 = Rw.create({'rapor_turu': 'mizan', 'seviye': '3', 'date_from': date(2026,1,1), 'date_to': date(2026,1,31)})._get_report()
dev = sum(abs(r['cells'][2] - r['cells'][3]) for r in m26['rows'][:-1] if r['cells'][0][:1] in '12345')
ok(dev == 0, "2026 mizanında bilanço hesaplarının net devri sıfır, bakiyeler açılış fişinden geliyor")
with env.cr.savepoint(flush=False) as sp:
    lk = post(M.create({'move_type': 'entry', 'date': date(2025,12,15), 'line_ids': [Command.create({'account_id': acc('100001').id, 'debit': 1}), Command.create({'account_id': acc('500000').id, 'credit': 1})]}))
    ok(lk.date > date(2025,12,31), f"kilitli 2025'e girilen fiş {lk.date} tarihine ertelendi")
    sp.rollback()
Y = env['atlas.yevmiye.no.wizard'].create({'yil': 2025}); Y.action_numarala()
first = M.search([('date','>=',date(2025,1,1)), ('date','<=',date(2025,12,31)), ('state','=','posted')], order='atlas_yevmiye_no', limit=1)
last = M.search([('date','>=',date(2025,1,1)), ('date','<=',date(2025,12,31)), ('state','=','posted')], order='atlas_yevmiye_no desc', limit=1)
ok(first.atlas_fis_turu == 'acilis' and first.atlas_yevmiye_no == 1 and last.atlas_fis_turu == 'kapanis', f"yevmiye madde no: 1 = açılış, son ({last.atlas_yevmiye_no}) = kapanış")
K.action_geri_al()
ok(K.state == 'cancel' and all(m.state == 'cancel' for m in K.move_ids) and not c.fiscalyear_lock_date, "kapanış geri alındı, fişler iptal, kilit kalktı")
s = env['atlas.sabit.kiymet.satis.wizard'].create({'kiymet_id': laptop.id, 'date': date(2026,2,1), 'satis_bedeli': 30000, 'partner_id': mavi.id})
sm = M.browse(s.action_onayla()['res_id'])
ok(laptop.state == 'closed' and ('689000', 10000.0) in [(l.account_id.code, l.balance) for l in sm.line_ids], "dizüstü satışı: net değer 40.000, satış 30.000 → 689 zarar 10.000")
env.cr.rollback(); print("(geri alındı)")
