from datetime import date
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']; B = env['atlas.cek.bordro']; c = env.company; J = env['account.journal']
def iban(bank, acc):
    bban = f"{bank}0{acc:016d}"; return f"TR{98 - int(bban + '292700') % 97:02d}{bban}"
garanti = J.create({'name': 'Garanti TL', 'code': 'GRN', 'type': 'bank', 'bank_account_number': iban('00062', 1)})
isb = J.create({'name': 'İş TL', 'code': 'ISB', 'type': 'bank', 'bank_account_number': iban('00064', 2)})
banka = env['atlas.banka'].search([('eft_kodu','=','00046')])
mavi = P.create({'name': 'Mavi Tekstil', 'is_company': True, 'atlas_cari_tipi': 'alici'})
kir = P.create({'name': 'Kırmızı Ltd', 'is_company': True, 'atlas_cari_tipi': 'satici'})
sari = P.create({'name': 'Sarı Gıda', 'is_company': True, 'atlas_cari_tipi': 'alici'})

g = B.create({'islem': 'giris', 'evrak_tipi': 'cek', 'partner_id': mavi.id, 'date': date(2026,9,10), 'line_ids': [
    Command.create({'seri_no': 'A-1001', 'banka_id': banka.id, 'sube': 'Kadıköy', 'kesideci': 'Mavi Tekstil', 'vade': date(2026,10,30), 'tutar': 4000}),
    Command.create({'seri_no': 'A-1002', 'banka_id': banka.id, 'vade': date(2026,11,30), 'tutar': 6000})]})
ok(str(g.ortalama_vade) == '2026-11-18', f"ortalama vade {g.ortalama_vade}")
g.action_post()
c1, c2 = g.line_ids.cek_id.sorted('vade')
ok(g.name.startswith('CSB2026') and c1.durum == 'portfoy' and c1.name.startswith('PRT2026'), f"giriş {g.name}: evraklar {c1.name}, {c2.name} portföyde")
ok(sorted((l.account_id.code, l.balance) for l in g.move_id.line_ids) == sorted([('101000', 4000), ('101000', 6000), (mavi.ref, -4000), (mavi.ref, -6000)]), "giriş fişi: 101 borç / 120 cari alacak")
mavi.invalidate_recordset(); ok(mavi.atlas_bakiye == -10000, f"Mavi cari bakiye {mavi.atlas_bakiye} (alacaklı)")

cr = B.with_context(**c1.action_ciro()['context']).create({'partner_id': kir.id, 'date': date(2026,9,12)}); cr.action_post()
ok(c1.durum == 'ciro' and c1.ciro_partner_id == kir and cr.move_id.line_ids.filtered(lambda l: l.debit).account_id.code == kir.ref, f"ciro: {c1.durum} → {kir.ref}")
try:
    with env.cr.savepoint(): B.with_context(**c1.action_ciro()['context']).create({'partner_id': kir.id}).action_post(); ok(False, "ikinci ciro kabul")
except UserError: ok(True, "ciro edilmiş çek tekrar ciro edilemez")

tv = B.with_context(**c2.action_tahsile_ver()['context']).create({'journal_id': garanti.id, 'date': date(2026,9,15)}); tv.action_post()
ok(c2.durum == 'tahsilde' and c2.konum_journal_id == garanti and sorted(tv.move_id.line_ids.mapped('account_id.code')) == ['101000', '101001'], f"tahsile verildi: {c2.konum_journal_id.name}, 101000 → 101001")
try:
    with env.cr.savepoint(): B.with_context(**c2.action_tahsil()['context']).create({'journal_id': isb.id}).action_post(); ok(False, "yanlış bankadan tahsil")
except UserError: ok(True, "başka bankadan tahsil engellendi")
th = B.with_context(**c2.action_tahsil()['context']).create({'journal_id': garanti.id, 'date': date(2026,11,30)}); th.action_post()
tl = th.move_id.line_ids.filtered(lambda l: l.debit)
ok(c2.durum == 'tahsil' and tl.account_id == c.transfer_account_id and tl.atlas_banka_journal_id == garanti, f"tahsil: transit {tl.account_id.code}")
st = env['account.bank.statement.line'].create({'journal_id': garanti.id, 'date': date(2026,11,30), 'payment_ref': 'CEK TAHSILATI A-1002', 'amount': 6000})
st.action_atlas_oner(); ok(st.atlas_bekleyen_line_id == tl, f"ekstre önerisi: {st.atlas_oneri}")
st.action_atlas_eslestir(); ok(st.is_reconciled and tl.reconciled, "banka ekstresiyle kapandı")

sg = B.create({'islem': 'giris', 'evrak_tipi': 'senet', 'partner_id': sari.id, 'date': date(2026,9,10), 'line_ids': [Command.create({'seri_no': 'S-1', 'vade': date(2026,9,20), 'tutar': 3000})]})
sg.action_post(); s1 = sg.line_ids.cek_id
ok(s1.evrak_turu == 'musteri_senet' and sg.move_id.line_ids.filtered(lambda l: l.debit).account_id.code == '121000', "senet girişi 121000")
ks = B.with_context(**s1.action_karsiliksiz()['context']).create({'date': date(2026,9,25)}); ks.action_post()
sari.invalidate_recordset(); ok(s1.durum == 'karsiliksiz' and sari.atlas_bakiye == 0 and ks.partner_id == sari, f"protesto: cari tekrar borçlandı, Sarı bakiye {sari.atlas_bakiye}")

fc = B.create({'islem': 'firma_cikis', 'evrak_tipi': 'cek', 'partner_id': kir.id, 'date': date(2026,9,18), 'line_ids': [Command.create({'seri_no': 'F-501', 'vade': date(2026,12,15), 'tutar': 2500})]})
fc.action_post(); f1 = fc.line_ids.cek_id
ok(f1.durum == 'verildi' and f1.kesideci == c.name and sorted((l.account_id.code, l.balance) for l in fc.move_id.line_ids) == sorted([(kir.ref, 2500), ('103000', -2500)]), "firma çeki çıkışı: 320 borç / 103 alacak")
fo = B.with_context(**f1.action_firma_odeme()['context']).create({'journal_id': garanti.id, 'date': date(2026,12,15)}); fo.action_post()
ok(f1.durum == 'odendi', "firma çeki ödendi (bankadan, transit)")
try: fc.action_cancel(); ok(False, "sonraki bordro varken iptal")
except UserError: ok(True, "sonraki bordrosu olan bordro iptal edilemez")
fo.action_cancel(); ok(f1.durum == 'verildi' and fo.move_id.state == 'cancel', "son bordro iptal: evrak 'verildi'ye döndü, fiş iptal")
try:
    with env.cr.savepoint(): B.create({'islem': 'giris', 'evrak_tipi': 'cek', 'partner_id': mavi.id, 'line_ids': [Command.create({'seri_no': 'A-1001', 'banka_id': banka.id, 'vade': date(2026,10,1), 'tutar': 1})]}).action_post(); ok(False, "mükerrer çek no")
except Exception: ok(True, "aynı banka + çek no reddedildi")
env.flush_all()
H = env['atlas.cari.hareket']
ok(set(H.search([('partner_id','=',mavi.id)]).mapped('hareket_turu')) == {'cek_senet'}, "cari hareketinde 'Çek / Senet' türü")
html = env['ir.actions.report']._render_qweb_html('atlas_cek_senet.report_cek_bordro', g.ids)[0]
ok(b'A-1002' in html and b'TOPLAM' in html, "bordro çıktısı render")
env.cr.rollback(); print("(geri alındı)")
