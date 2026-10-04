from datetime import date
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; M = env['account.move']; T = env['atlas.tahakkuk']
acc = lambda code: env['account.account'].search([('code', '=', code), ('company_ids', 'in', c.root_id.id)], limit=1)
ok(c.atlas_gag_hesap_id.code == '180000' and c.atlas_gya_gelir_hesap_id.code == '480000', "erteleme hesapları: 180/280/380/480 (480 oluşturuldu)")
ted = env['res.partner'].create({'name': 'TAH Sigorta', 'is_company': True})
mus = env['res.partner'].create({'name': 'TAH Müşteri', 'is_company': True})
def fatura(mt, partner, tarih, tutar, hesap, bas, bit):
    m = M.create({'move_type': mt, 'partner_id': partner.id, 'invoice_date': tarih, 'date': tarih, 'invoice_line_ids': [Command.create({
        'name': 'Hizmet', 'quantity': 1, 'price_unit': tutar, 'tax_ids': False, 'account_id': acc(hesap).id,
        'atlas_ertele_bas': bas, 'atlas_ertele_bit': bit})]})
    m.action_post(); return m
def bakiye(moves, kod):
    return round(sum(moves.line_ids.filtered(lambda l: l.parent_state == 'posted' and l.account_id.code == kod).mapped('balance')), 2)

f1 = fatura('in_invoice', ted, date(2026, 10, 1), 24000, '770000', date(2026, 10, 1), date(2028, 9, 30))
t1 = f1.atlas_tahakkuk_ids
fis = t1.move_ids
er = fis.filtered(lambda m: m.atlas_tahakkuk_rol == 'erteleme'); vir = fis.filtered(lambda m: m.atlas_tahakkuk_rol == 'virman'); tan = fis.filtered(lambda m: m.atlas_tahakkuk_rol == 'tanima')
plan = t1._aylik_plan(); uzun = round(sum(t for d, t in plan if d.year == 2028), 2)
ok(len(t1) == 1 and len(tan) == 24 and len(vir) == 1 and er.state == 'posted' and er.atlas_fis_turu == 'mahsup', f"24 aylık plan: erteleme fişi {er.name}, 1 vade virmanı, 24 tahakkuk")
ok(bakiye(er, '180000') == round(24000 - uzun, 2) and bakiye(er, '280000') == uzun and bakiye(er, '770000') == -24000, f"erteleme: 180 {24000-uzun:,.2f}, 280 {uzun:,.2f}, 770'ten 24.000 çıktı")
ok(round(sum(t for d, t in plan), 2) == 24000 and plan[0][0] == date(2026, 10, 31) and plan[-1][0] == date(2028, 9, 30), "aylık dağılım toplamı 24.000, ilk ay sonu 31.10.2026")
ok(vir.date == date(2027, 12, 31) and vir.state == 'draft' and vir.auto_post == 'at_date' and round(vir.amount_total, 2) == uzun, "280 → 180 virmanı 31.12.2027'de otomatik onaylanacak")
ok(all(m.state == 'draft' and m.auto_post == 'at_date' for m in tan), "gelecek ayların tahakkukları taslak, tarihinde otomatik onay")
ok(t1.durum == 'devam' and t1.taninan == 0 and t1.kalan == 24000, "durum: devam, tanınan 0")
ekim = tan.sorted('date')[0]; ekim.auto_post = 'no'; ekim.action_post()
ok(bakiye(ekim, '770000') == round(plan[0][1], 2) and t1.taninan == round(plan[0][1], 2), f"Ekim tahakkuku onaylanınca 770'e {plan[0][1]:,.2f}")

f2 = fatura('in_invoice', ted, date(2026, 7, 1), 6000, '770000', date(2026, 7, 1), date(2026, 12, 31))
t2 = f2.atlas_tahakkuk_ids; tan2 = t2.move_ids.filtered(lambda m: m.atlas_tahakkuk_rol == 'tanima').sorted('date')
ok([m.state for m in tan2] == ['posted'] * 3 + ['draft'] * 3 and round(t2.taninan, 2) == round(6000 * 92 / 184, 2), f"geriye dönük fatura: geçmiş 3 ay hemen tanındı ({t2.taninan:,.2f})")

f3 = fatura('out_invoice', mus, date(2026, 10, 1), 12000, '600000', date(2026, 10, 1), date(2027, 9, 30))
t3 = f3.atlas_tahakkuk_ids; er3 = t3.move_ids.filtered(lambda m: m.atlas_tahakkuk_rol == 'erteleme')
ok(t3.tip == 'gelir' and bakiye(er3, '380000') == -12000 and bakiye(er3, '600000') == 12000 and not t3.move_ids.filtered(lambda m: m.atlas_tahakkuk_rol == 'virman'),
   "satış faturası: 600'den 380'e 12.000 (12 ay içinde, virman yok)")
tan3 = t3.move_ids.filtered(lambda m: m.atlas_tahakkuk_rol == 'tanima').sorted('date')[0]
ok(bakiye(tan3.line_ids.move_id, '380000') == 0 or tan3.line_ids.filtered(lambda l: l.account_id.code == '600000').balance < 0, "gelir tahakkuku: 380 borç / 600 alacak")

f1.button_draft()
ters = M.search([('reversed_entry_id', '=', er.id)])
ok(not f1.atlas_tahakkuk_ids and ters.state == 'posted' and not M.search_count([('id', 'in', vir.ids)]) and ekim.reversal_move_ids,
   "fatura taslağa alındı: erteleme ve onaylı tahakkuk ters kayıtla iptal, taslaklar silindi")
f1.action_post()
ok(len(f1.atlas_tahakkuk_ids) == 1 and len(f1.atlas_tahakkuk_ids.move_ids) == 26, "yeniden onayda plan yeniden oluştu")

t4 = T.create({'name': 'Peşin kira (6 ay)', 'tip': 'gider', 'hesap_id': acc('770000').id, 'tutar': 1200,
               'tarih': date(2026, 10, 4), 'bas': date(2026, 10, 1), 'bit': date(2027, 3, 31)})
t4.action_onayla()
ok(len(t4.move_ids) == 7 and t4.durum == 'devam' and t4.kisa_hesap_id.code == '180000', "elle erteleme: 1 erteleme + 6 tahakkuk")
try:
    with env.cr.savepoint(): t4.action_onayla(); hata = False
except UserError: hata = True
ok(hata, "ikinci onay reddedildi")
try:
    with env.cr.savepoint():
        M.create({'move_type': 'in_invoice', 'partner_id': ted.id, 'invoice_date': date(2026, 10, 1), 'invoice_line_ids': [Command.create({
            'name': 'x', 'quantity': 1, 'price_unit': 1, 'atlas_ertele_bas': date(2026, 10, 1)})]}); env.flush_all(); hata = False
except ValidationError: hata = True
ok(hata, "yalnızca başlangıç tarihi girilen satır reddedildi")
env.cr.rollback(); print("(geri alındı)")
