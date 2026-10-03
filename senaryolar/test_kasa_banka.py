import base64, io
from datetime import date, datetime
import openpyxl
from odoo.exceptions import ValidationError, UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']; M = env['account.move']; J = env['account.journal']; c = env.company
def iban(bank, acc):
    bban = f"{bank}0{acc:016d}"
    check = 98 - int(bban + '292700') % 97
    return f"TR{check:02d}{bban}"

usd = env.ref('base.USD')
k_usd = J.create({'name': 'USD Kasa', 'code': 'KUSD', 'type': 'cash', 'currency_id': usd.id})
m_lines = k_usd.inbound_payment_method_line_ids | k_usd.outbound_payment_method_line_ids
ok(k_usd.default_account_id.currency_id == usd and all(l.payment_account_id == k_usd.default_account_id for l in m_lines),
   f"USD kasa: hesap {k_usd.default_account_id.code} ({k_usd.default_account_id.currency_id.name}), ödemeler doğrudan kasaya")
g_iban = iban('00062', 123456)
garanti = J.create({'name': 'Garanti TL', 'code': 'GRN', 'type': 'bank', 'bank_account_number': g_iban})
ok(garanti.bank_name == 'Garanti BBVA' and garanti.default_account_id.code.startswith('102'), f"banka: {garanti.default_account_id.code} {garanti.bank_name} {garanti.bank_account_number}")
try:
    with env.cr.savepoint(): J.create({'name': 'x', 'code': 'XX', 'type': 'bank', 'bank_account_number': 'TR000006200000000000123456'}); ok(False, "geçersiz IBAN kabul")
except ValidationError: ok(True, "geçersiz IBAN reddedildi")
isb = J.create({'name': 'İş Bankası TL', 'code': 'ISB', 'type': 'bank', 'bank_account_number': iban('00064', 998877)})

mavi = P.create({'name': 'Mavi Tekstil A.Ş.', 'is_company': True, 'atlas_cari_tipi': 'alici'})
kirmizi = P.create({'name': 'Kırmızı Ltd', 'is_company': True, 'atlas_cari_tipi': 'satici', 'country_id': env.ref('base.tr').id, 'vat': '1234567890'})
sari = P.create({'name': 'Sarı Gıda', 'is_company': True, 'atlas_cari_tipi': 'alici'})
def inv(mt, p, amt, d=date(2026,9,5)):
    m = M.create({'move_type': mt, 'partner_id': p.id, 'invoice_date': d, 'invoice_line_ids': [(0,0,{'name': 'K', 'quantity': 1, 'price_unit': amt, 'tax_ids': False})]}); m.action_post(); return m
f_mavi = inv('out_invoice', mavi, 1000); b_kir = inv('in_invoice', kirmizi, 500); f_sari = inv('out_invoice', sari, 300)
pay = env['account.payment.register'].with_context(active_model='account.move', active_ids=f_sari.ids).create({'journal_id': garanti.id, 'payment_date': date(2026,9,20)})._create_payments()
ok(pay.outstanding_account_id.code == '102002' and not pay.move_id.line_ids.filtered(lambda l: l.account_id == pay.outstanding_account_id).reconciled, f"banka ödemesi bekleyen hesapta: {pay.outstanding_account_id.code}")
csh = J.search([('code','=','CSH1')])
v = env['atlas.virman.wizard'].create({'kaynak_journal_id': csh.id, 'hedef_journal_id': garanti.id, 'amount': 2000, 'date': date(2026,9,21), 'aciklama': 'Kasadan bankaya'})
vm = M.browse(v.action_create()['res_id'])
ok(vm.name.startswith('VRM2026') and sorted(vm.line_ids.mapped('account_id.code')) == sorted([csh.default_account_id.code, c.transfer_account_id.code]),
   f"virman {vm.name}: {[(l.account_id.code, l.balance) for l in vm.line_ids]}")

wb = openpyxl.Workbook(); ws = wb.active
ws.append(['GARANTİ BBVA']); ws.append(['Hesap Hareketleri']); ws.append([]); ws.append(['IBAN', g_iban]); ws.append(['Dönem', '01.09.2026 - 25.09.2026']); ws.append([]); ws.append([])
ws.append(['Tarih', 'Açıklama', 'Etiket', 'Tutar', 'Bakiye', 'Dekont No'])
rows = [('25.09.2026', 'GELEN EFT bilinmeyen gönderen', '', '45,00', '2.830,00', 'D7'),
        ('24.09.2026', 'BSMV', '', '-2,50', '2.785,00', 'D6'),
        ('24.09.2026', 'EFT MASRAFI', '', '-12,50', '2.787,50', 'D5'),
        ('23.09.2026', 'GİDEN EFT KIRMIZI LTD VKN 1234567890 fatura ödemesi', '', '-500,00', '2.800,00', 'D4'),
        ('22.09.2026', 'NAKİT YATAN', '', '2.000,00', '3.300,00', 'D3'),
        ('21.09.2026', 'HAVALE SARI GIDA', '', '300,00', '1.300,00', 'D2'),
        ('20.09.2026', 'GELEN EFT MAVI TEKSTIL ATL2026000000001 ÖDEMESİ', '', '1.000,00', '1.000,00', 'D1')]
for r in rows: ws.append(list(r))
buf = io.BytesIO(); wb.save(buf)
imp = env['atlas.banka.ekstre.import'].create({'journal_id': garanti.id, 'file': base64.b64encode(buf.getvalue()).decode(), 'filename': 'garanti.xlsx'})
act = imp.action_import()
st = env['account.bank.statement.line'].search([('statement_id', '=', act['domain'][0][2])], order='date, id')
ok(len(st) == 7 and st[0].amount == 1000 and st.statement_id.balance_end_real == 2830 and st.statement_id.balance_start == 0, f"7 satır, sıra eskiden yeniye, açılış {st.statement_id.balance_start} kapanış {st.statement_id.balance_end_real}")
by = {l.atlas_referans: l for l in st}
ok(by['D1'].atlas_fatura_id == f_mavi, "D1 fatura no ile eşleşti")
ok(by['D2'].atlas_bekleyen_line_id.payment_id == pay, "D2 bekleyen banka ödemesi bulundu")
ok(by['D3'].atlas_bekleyen_line_id.move_id == vm, "D3 virman transit kaydı bulundu")
ok(by['D4'].partner_id == kirmizi and by['D4'].atlas_fatura_id == b_kir, "D4 VKN ile cari + tutar tutan alış faturası")
ok(by['D5'].atlas_karsi_hesap_id.code == '653000' and by['D6'].atlas_karsi_hesap_id.code == '653000', "D5/D6 masraf kuralları → 653")
ok(not by['D7'].partner_id and not by['D7'].atlas_karsi_hesap_id, "D7 öneri yok")
(st - by['D7']).action_atlas_eslestir()
ok(all((st - by['D7']).mapped('is_reconciled')), "6 satır eşleşti")
ok(f_mavi.payment_state == 'paid' and b_kir.payment_state == 'paid', f"faturalar kapandı: {f_mavi.payment_state}, {b_kir.payment_state}")
pay.invalidate_recordset(); ok(pay.state == 'reconciled' and f_sari.payment_state == 'paid', f"banka ödemesi mutabık: {pay.state}, fatura {f_sari.payment_state}")
ok(vm.line_ids.filtered(lambda l: l.account_id == c.transfer_account_id).reconciled, "virman transit satırı kapandı")
try: by['D7'].action_atlas_eslestir(); ok(False, "boş satır eşleşti")
except UserError: ok(True, "öneri/seçim olmayan satır uyarı verdi")
by['D7'].write({'partner_id': mavi.id}); by['D7'].action_atlas_eslestir()
ok(by['D7'].is_reconciled, "D7 elle cari seçilip eşleşti")
try: env['atlas.banka.ekstre.import'].create({'journal_id': garanti.id, 'file': base64.b64encode(buf.getvalue()).decode(), 'filename': 'g.xlsx'}).action_import(); ok(False, "tekrar aktarıldı")
except UserError as e: ok(True, f"aynı ekstre tekrar: {e}")
by['D1'].action_atlas_geri_al(); ok(not by['D1'].is_reconciled and f_mavi.payment_state == 'not_paid', "geri al: fatura tekrar açık")
by['D1'].action_atlas_eslestir(); ok(f_mavi.payment_state == 'paid', "yeniden eşleştirildi")
garanti.invalidate_recordset(); ok(round(garanti.atlas_bakiye, 2) == 2830.0, f"Garanti bakiye = ekstre kapanışı: {garanti.atlas_bakiye}")

wb = openpyxl.Workbook(); ws = wb.active
ws.append(['İşlem Tarihi', 'Valör', 'Açıklama', 'Borç', 'Alacak', 'Bakiye'])
ws.append([datetime(2026,9,10,14,30), datetime(2026,9,10), 'EFT ÜCRETİ', 5.5, None, -5.5])
ws.append([datetime(2026,9,11,9,0), datetime(2026,9,11), 'FAİZ TAHAKKUKU', None, 12.25, 6.75])
buf2 = io.BytesIO(); wb.save(buf2)
act2 = env['atlas.banka.ekstre.import'].create({'journal_id': isb.id, 'file': base64.b64encode(buf2.getvalue()).decode(), 'filename': 'is.xlsx'}).action_import()
st2 = env['account.bank.statement.line'].search([('statement_id', '=', act2['domain'][0][2])], order='date')
ok([l.amount for l in st2] == [-5.5, 12.25] and [l.atlas_karsi_hesap_id.code for l in st2] == ['653000', '642000'], f"borç/alacak biçimi: {[(l.amount, l.atlas_karsi_hesap_id.code) for l in st2]}")

cp = env['account.payment'].create({'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': mavi.id, 'amount': 100, 'currency_id': usd.id, 'journal_id': k_usd.id, 'date': date(2026,9,22)})
cp.action_post()
v2 = env['atlas.virman.wizard'].create({'kaynak_journal_id': k_usd.id, 'hedef_journal_id': csh.id, 'amount': 40, 'date': date(2026,9,23)})
ok(round(v2.hedef_amount, 2) > 1900, f"döviz bozdurma: 40 USD → {v2.hedef_amount:.2f} TL önerildi")
v2.action_create()
env.flush_all()
H = env['atlas.kasa.banka.hareket']
k_usd.invalidate_recordset(); ok(k_usd.atlas_bakiye == 60 and k_usd.atlas_currency_id == usd, f"USD kasa bakiyesi {k_usd.atlas_bakiye} USD (TL {k_usd.atlas_bakiye_tl:.2f})")
ok(set(H.search([('journal_id','=',garanti.id)]).mapped('hareket_turu')) == {'ekstre'}, "Garanti hareketleri 'Banka Ekstresi' türünde")
env.cr.rollback(); print("(geri alındı)")
