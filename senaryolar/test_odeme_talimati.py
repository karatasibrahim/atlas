from datetime import date
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def iban(bank, acc):
    bban = f"{bank}0{acc:016d}"; check = 98 - int(bban + '292700') % 97; return f"TR{check:02d}{bban}"
P = env['res.partner']; M = env['account.move']; T = env['atlas.odeme.talimat']
banka = env['account.journal'].create({'name': 'OTL Garanti', 'code': 'OTG', 'type': 'bank', 'bank_account_number': iban('00062', 777001)})
def ted(ad, ib=None):
    p = P.create({'name': ad, 'is_company': True, 'atlas_cari_tipi': 'satici', 'vat': '1234567890', 'country_id': env.ref('base.tr').id})
    if ib:
        env['res.partner.bank'].create({'partner_id': p.id, 'account_number': ib, 'allow_out_payment': True})
    return p
a, b, c, d = ted('OTL Alfa', iban('00064', 11)), ted('OTL Beta', iban('00046', 22)), ted('OTL Gama'), ted('OTL Delta', iban('00010', 33))
def fatura(p, tutar, ref):
    m = M.create({'move_type': 'in_invoice', 'partner_id': p.id, 'invoice_date': date(2026, 9, 1), 'ref': ref,
                  'invoice_line_ids': [Command.create({'name': 'K', 'quantity': 1, 'price_unit': tutar, 'tax_ids': False})]})
    m.action_post(); return m
fa1, fa2, fb, fc = fatura(a, 1000, 'A-1'), fatura(a, 500, 'A-2'), fatura(b, 2000, 'B-1'), fatura(c, 300, 'C-1')
w = env['atlas.odeme.talimat.ekle'].with_context(active_model='account.move', active_ids=(fa1 | fa2 | fb).ids).create({'journal_id': banka.id, 'tarih': date(2026, 10, 5)})
t = T.browse(w.action_ekle()['res_id'])
sa = t.satir_ids.filtered(lambda s: s.partner_id == a); sb = t.satir_ids.filtered(lambda s: s.partner_id == b)
ok(t.name.startswith('OTL') and len(t.satir_ids) == 2 and sa.tutar == 1500 and len(sa.move_ids) == 2 and sa.partner_bank_id.partner_id == a and 'A-1' in sa.aciklama,
   f"talimat {t.name}: Alfa 1.500 (2 fatura, IBAN otomatik), Beta 2.000")
env['atlas.odeme.talimat.ekle'].with_context(active_model='account.move', active_ids=(fa1 | fc).ids).create({'talimat_id': t.id}).action_ekle()
ok(len(t.satir_ids) == 3 and sa.tutar == 1500, "aynı fatura ikinci kez eklenmedi, Gama eklendi")
env['atlas.odeme.talimat.satir'].create({'talimat_id': t.id, 'partner_id': d.id, 'tutar': 700, 'aciklama': 'Ekim avansı'})
try:
    with env.cr.savepoint(): t.action_onayla(); hata = None
except UserError as e: hata = str(e)
ok(hata and 'OTL Gama' in hata and 'IBAN' in hata, "IBAN'ı olmayan cari onayı engelledi")
t.satir_ids.filtered(lambda s: s.partner_id == c).unlink()
sb.tutar = 2500
try:
    with env.cr.savepoint(): t.action_onayla(); hata = None
except UserError as e: hata = str(e)
ok(hata and 'aşıyor' in hata, "fatura bakiyesini aşan tutar reddedildi")
sb.tutar = 1500
ok(t.toplam == 3700, "talimat toplamı 3.700")
t.action_onayla()
ok(t.durum == 'onaylandi' and len(t.payment_ids) == 3 and fa1.payment_state in ('paid', 'in_payment') and fa2.payment_state in ('paid', 'in_payment')
   and fb.payment_state == 'partial' and fb.amount_residual == 500, f"onay: 3 ödeme, Alfa faturaları kapandı, Beta kısmi ({fb.amount_residual:,.0f} kaldı)")
pd = t.satir_ids.filtered(lambda s: s.partner_id == d).payment_id
ok(pd.amount == 700 and pd.partner_type == 'supplier' and pd.state != 'draft', "faturasız avans ödemesi")
csv = t._csv().decode('utf-8-sig')
ok(t._xlsx()[:2] == b'PK' and iban('00064', 11) in csv and '1500,00' in csv and 'Ekim avansı' in csv, "banka dosyası: Excel ve CSV (IBAN, tutar, açıklama)")
t.action_csv()
ok(t.durum == 'gonderildi', "dosya alınınca 'bankaya gönderildi'")
for s in t.satir_ids:
    st = env['account.bank.statement.line'].create({'journal_id': banka.id, 'date': date(2026, 10, 5), 'amount': -s.tutar, 'payment_ref': f'EFT {s.partner_id.name}'})
    st.atlas_bekleyen_line_id = st._atlas_find_pending_line()
    st.action_atlas_eslestir()
t.invalidate_recordset()
ok(t.eslesen_sayisi == 3 and t.durum == 'tamamlandi', "ekstre eşleşince talimat tamamlandı")
fa3 = fatura(a, 800, 'A-3')
t2 = T.browse(env['atlas.odeme.talimat.ekle'].with_context(active_model='account.move', active_ids=fa3.ids).create({'journal_id': banka.id}).action_ekle()['res_id'])
t2.action_onayla(); t2.action_iptal()
ok(t2.durum == 'iptal' and fa3.payment_state == 'not_paid' and t2.payment_ids.state == 'canceled', "iptal: ödeme iptal, fatura yeniden açık")
env.cr.rollback(); print("(geri alındı)")
