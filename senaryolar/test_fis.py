from datetime import date
from odoo.exceptions import ValidationError, UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
S = env['atlas.seri']; M = env['account.move']; P = env['res.partner']; c = env.company
alici = P.create({'name': 'Test Alıcı', 'is_company': True, 'atlas_cari_tipi': 'alici'})
satici = P.create({'name': 'Test Satıcı', 'is_company': True, 'atlas_cari_tipi': 'satici'})
def inv(mt, partner, d, amount=1000):
    return M.create({'move_type': mt, 'partner_id': partner.id, 'invoice_date': d, 'ref': 'X',
        'invoice_line_ids': [(0,0,{'name': 'Kalem', 'quantity': 1, 'price_unit': amount, 'tax_ids': False})]})
i1 = inv('out_invoice', alici, date(2026,9,1)); i2 = inv('out_invoice', alici, date(2026,9,2))
ok(i1.atlas_seri_id.on_ek == 'ATL' and i1.name_placeholder == 'ATL2026000000001', f"taslak seri {i1.atlas_seri_id.on_ek}, tahmini no {i1.name_placeholder}")
(i1 | i2).action_post()
ok((i1.name, i2.name) == ('ATL2026000000001','ATL2026000000002'), f"satış faturaları: {i1.name}, {i2.name} (GİB 16 kr: {len(i1.name)})")
i3 = inv('out_invoice', alici, date(2027,1,5)); i3.action_post()
ok(i3.name == 'ATL2027000000001', f"yeni yıl sıfırlandı: {i3.name}")
b1 = inv('in_invoice', satici, date(2026,9,3)); b1.action_post()
ok(b1.name == 'ALF2026000001', f"alış faturası: {b1.name}")
r1 = inv('out_refund', alici, date(2026,9,4)); r1.action_post()
ok(r1.name == 'SIA2026000001', f"satış iadesi: {r1.name}")
r2 = inv('in_refund', satici, date(2026,9,5)); r2.action_post()
ok(r2.name == 'ATL2026000000003', f"alış iade faturası giden fatura serisini paylaşıyor: {r2.name}")
i1.button_draft(); i1.action_post(); ok(i1.name == 'ATL2026000000001', f"taslağa alıp tekrar onay: numara korundu {i1.name}")

acc120 = alici.property_account_receivable_id; acc320 = satici.property_account_payable_id
gider = env['account.account'].search([('code','=like','770%')], limit=1)
mh = M.with_context(default_move_type='entry', default_atlas_fis_turu='mahsup').create({'date': date(2026,9,10), 'ref': 'Virman',
    'line_ids': [(0,0,{'account_id': acc320.id, 'debit': 300, 'name': 'Satıcıya borç'}), (0,0,{'account_id': acc120.id, 'credit': 300, 'name': 'Alıcıdan alacak'})]})
ok(set(mh.line_ids.mapped('partner_id').ids) == {alici.id, satici.id}, "cari hesaplarına cari otomatik atandı")
mh.action_post(); ok(mh.name == 'MHS2026000001' and mh.journal_id.type == 'general', f"mahsup: {mh.name} [{mh.journal_id.code}]")
bad = M.with_context(default_move_type='entry', default_atlas_fis_turu='mahsup').create({'date': date(2026,9,10),
    'line_ids': [(0,0,{'account_id': acc120.id, 'partner_id': satici.id, 'debit': 50}), (0,0,{'account_id': gider.id, 'credit': 50})]})
try: bad.action_post(); ok(False, "yanlış cari kabul edildi")
except UserError as e: ok(True, f"yanlış cari reddedildi: {str(e)[:80]}")

th = M.with_context(default_move_type='entry', default_atlas_fis_turu='tahsil').create({'date': date(2026,9,11), 'ref': 'Makbuz 15',
    'line_ids': [(0,0,{'account_id': acc120.id, 'credit': 700, 'name': 'Nakit tahsilat'})]})
kasa = th.line_ids.filtered('atlas_kasa_line')
ok(th.journal_id.type == 'cash' and kasa.debit == 700 and kasa.account_id == th.journal_id.default_account_id, f"tahsil: yevmiye {th.journal_id.code}, kasa satırı {kasa.account_id.code} B {kasa.debit}")
th.line_ids.filtered(lambda l: not l.atlas_kasa_line).credit = 900
ok(th.line_ids.filtered('atlas_kasa_line').debit == 900, "tutar değişince kasa satırı güncellendi")
th.action_post(); ok(th.name == 'THS2026000001', f"tahsil no: {th.name}")
td = M.with_context(default_move_type='entry', default_atlas_fis_turu='tediye').create({'date': date(2026,9,12),
    'line_ids': [(0,0,{'account_id': acc320.id, 'debit': 250, 'name': 'Nakit ödeme'})]})
td.action_post(); ok(td.name == 'TDY2026000001' and td.line_ids.filtered('atlas_kasa_line').credit == 250, f"tediye: {td.name}, kasa A 250")
td_bad = M.with_context(default_move_type='entry', default_atlas_fis_turu='tediye').create({'date': date(2026,9,12),
    'line_ids': [(0,0,{'account_id': acc120.id, 'credit': 10})]})
try: td_bad.action_post(); ok(False, "ters yönlü tediye kabul edildi")
except UserError: ok(True, "ters yönlü tediye reddedildi")

S.search([('on_ek','=','DKN')]).baslangic_no = 500
dk = M.with_context(default_move_type='entry', default_atlas_fis_turu='dekont').create({'date': date(2026,9,13),
    'line_ids': [(0,0,{'account_id': acc120.id, 'debit': 10}), (0,0,{'account_id': gider.id, 'credit': 10})]})
dk.action_post(); ok(dk.name == 'DKN2026000500', f"başlangıç no 500: {dk.name}")

std = M.create({'move_type': 'entry', 'date': date(2026,9,14), 'line_ids': [(0,0,{'account_id': gider.id, 'debit': 5}), (0,0,{'account_id': acc120.id, 'credit': 5})]})
std.action_post(); ok(not std.atlas_seri_id and std.name.startswith('MISC/'), f"fiş türsüz kayıt Odoo numarası: {std.name}")
cash_j = th.journal_id
pay = env['account.payment'].create({'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': alici.id, 'amount': 50, 'date': date(2026,9,15), 'journal_id': cash_j.id})
pay.action_post(); ok(not pay.move_id.atlas_seri_id and not pay.move_id.name.startswith('THS'), f"kasa yevmiyesinde ödeme kendi numarası: {pay.move_id.name}")

ear = S.create({'name': 'e-Arşiv', 'on_ek': 'EAR', 'hane': 9, 'belge_turu_ids': [(6,0,env.ref('atlas_fis.belge_satis_fatura').ids)]})
i4 = inv('out_invoice', alici, date(2026,9,20)); i4.atlas_seri_id = ear; i4.action_post()
ok(i4.name == 'EAR2026000000001' and ear.gib_uyumlu, f"elle seçilen e-Arşiv serisi: {i4.name}")
for vals, label in [({'name': 'dup', 'on_ek': 'ATL', 'hane': 9, 'belge_turu_ids': [(6,0,env.ref('atlas_fis.belge_satis_fatura').ids)]}, 'aynı ön ek'),
                    ({'name': 'def2', 'on_ek': 'ZZZ', 'hane': 9, 'varsayilan': True, 'belge_turu_ids': [(6,0,env.ref('atlas_fis.belge_satis_fatura').ids)]}, 'ikinci varsayılan'),
                    ({'name': 'x', 'on_ek': 'A1', 'yil_ekle': False, 'hane': 5, 'belge_turu_ids': [(6,0,env.ref('atlas_fis.belge_mahsup').ids)]}, 'rakamla biten ön ek')]:
    try:
        with env.cr.savepoint(): S.create(vals); ok(False, f"{label} kabul edildi")
    except ValidationError: ok(True, f"{label} reddedildi")
y = S.create({'name': 'Yılsız', 'on_ek': 'M-', 'yil_ekle': False, 'hane': 5, 'belge_turu_ids': [(6,0,env.ref('atlas_fis.belge_kapanis').ids)]})
S.search([('on_ek','=','KPN')]).varsayilan = False; y.varsayilan = True
kp = M.with_context(default_move_type='entry', default_atlas_fis_turu='kapanis').create({'date': date(2026,12,31),
    'line_ids': [(0,0,{'account_id': acc120.id, 'debit': 1}), (0,0,{'account_id': gider.id, 'credit': 1})]})
kp.action_post(); ok(kp.name == 'M-00001', f"yılsız seri: {kp.name}")
env.flush_all()
H = env['atlas.cari.hareket']
turler = {h.move_name: h.hareket_turu for h in H.search([('partner_id','=',alici.id)])}
ok(turler.get('THS2026000001') == 'fis_tahsil' and turler.get('DKN2026000500') == 'fis_dekont' and turler.get('M-00001') == 'fis_kapanis', "cari hareketinde fiş türleri")
env.cr.rollback(); print("(geri alındı)")
