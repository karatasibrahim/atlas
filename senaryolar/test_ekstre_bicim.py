import base64
from datetime import date
from odoo.exceptions import UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
J = env['account.journal']
W = env['atlas.banka.ekstre.import']
yev = J.create({'name': 'EB Banka', 'code': 'EBB', 'type': 'bank'})
aktar = lambda ad, icerik: W.create({'journal_id': yev.id, 'file': base64.b64encode(icerik).decode(), 'filename': ad, 'oner': False}).action_import()
satirlar = lambda eylem: env['account.bank.statement.line'].search(eylem['domain'], order='date, id')

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt><Id>1</Id>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="TRY">1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2025-10-01</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="TRY">1450.50</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2025-10-03</Dt></Dt></Bal>
<Ntry><Amt Ccy="TRY">500.50</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2025-10-02</Dt></BookgDt><AcctSvcrRef>REF-1</AcctSvcrRef>
 <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Mavi Tekstil</Nm></Dbtr></RltdPties><RmtInf><Ustrd>ATL2025000000001 nolu fatura</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="TRY">50.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2025-10-03</Dt></BookgDt><AcctSvcrRef>REF-2</AcctSvcrRef>
 <AddtlNtryInf>EFT masrafı</AddtlNtryInf></Ntry>
</Stmt></BkToCstmrStmt></Document>""".encode()
e = aktar('ekstre.xml', CAMT)
s = satirlar(e)
st = s.statement_id
ok(len(s) == 2 and s[0].amount == 500.5 and s[1].amount == -50 and s[0].atlas_referans == 'REF-1' and 'Mavi Tekstil' in s[0].payment_ref
   and 'ATL2025000000001' in s[0].payment_ref, f"CAMT.053: 2 hareket, tutar/işaret/referans/açıklama ({s.mapped('payment_ref')})")
ok(st.balance_start == 1000 and st.balance_end_real == 1450.5, f"CAMT.053: açılış {st.balance_start}, kapanış {st.balance_end_real}")
try:
    with env.cr.savepoint():
        aktar('ekstre.xml', CAMT); tekrar = True
except UserError:
    tekrar = False
ok(not tekrar, "aynı CAMT ikinci kez aktarılmaz (tekrar kontrolü)")

OFX = b"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>TRY<BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20251005120000<TRNAMT>250.00<FITID>OFX1<NAME>Sari Gida<MEMO>Tahsilat</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20251006<TRNAMT>-75.25<FITID>OFX2<NAME>Kira</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>2174.75<DTASOF>20251006</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""
s = satirlar(aktar('hesap.ofx', OFX))
ok(len(s) == 2 and s[0].amount == 250 and s[1].amount == -75.25 and s[0].payment_ref == 'Sari Gida Tahsilat' and s[0].date == date(2025, 10, 5),
   "OFX: 2 hareket, tarih/tutar/açıklama")
ok(s.statement_id.balance_end_real == 2174.75 and s.statement_id.balance_start == 2000, "OFX: kapanıştan açılış hesaplandı")

MT940 = b""":20:STARTUMS
:25:TR330006100519786457841326
:28C:00001/001
:60F:C251006TRY2174,75
:61:2510070107C1000,00NTRFNONREF//BANKREF1
:86:?20Havale Mavi Tekstil?21ATL2025000000002
:61:2510080108D200,50NCHGNONREF
:86:Hesap isletim ucreti
:62F:C251008TRY2974,25
-"""
s = satirlar(aktar('ekstre.sta', MT940))
ok(len(s) == 2 and s[0].amount == 1000 and s[1].amount == -200.5 and 'Mavi Tekstil' in s[0].payment_ref and s[0].date == date(2025, 10, 7),
   f"MT940: 2 hareket, C/D işareti, :86: açıklaması ({s[0].payment_ref})")
ok(s.statement_id.balance_start == 2174.75 and s.statement_id.balance_end_real == 2974.25, "MT940: :60F: / :62F: bakiyeleri")

CSV = "Tarih;Açıklama;Tutar;Bakiye\n09.10.2025;POS tahsilat;1.250,00;4.224,25\n10.10.2025;Fatura ödemesi;-224,25;4.000,00\n".encode('windows-1254')
s = satirlar(aktar('hareketler.csv', CSV))
ok(len(s) == 2 and s[0].amount == 1250 and s[1].amount == -224.25 and s[0].payment_ref == 'POS tahsilat' and s.statement_id.balance_end_real == 4000,
   "CSV (; ayraçlı, Türkçe sayı biçimi, windows-1254): başlıklardan otomatik algılandı")
try:
    with env.cr.savepoint():
        aktar('notlar.pdf', b'%PDF-1.4 bozuk'); taninmadi = False
except UserError as hata:
    taninmadi = 'tanınmadı' in str(hata)
ok(taninmadi, "tanınmayan biçimde anlaşılır hata")
env.cr.rollback(); print("(geri alındı)")
