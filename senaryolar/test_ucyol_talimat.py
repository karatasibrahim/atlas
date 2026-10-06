from datetime import date
from odoo import fields
from odoo.exceptions import UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)


def iban(bank, acc):
    bban = f"{bank}0{acc:016d}"; check = 98 - int(bban + '292700') % 97; return f"TR{check:02d}{bban}"


sirket = env.company
banka = env['account.journal'].create({'name': 'UCY Banka', 'code': 'UCB', 'type': 'bank', 'bank_account_number': iban('00062', 888001)})
ted = env['res.partner'].create({'name': 'UCY Tedarikçi', 'is_company': True, 'atlas_cari_tipi': 'satici', 'vat': '1234567890',
                                 'country_id': env.ref('base.tr').id})
env['res.partner.bank'].create({'partner_id': ted.id, 'account_number': iban('00064', 55), 'allow_out_payment': True})
mal = env['product.product'].create({'name': 'UCY Malı', 'type': 'consu', 'is_storable': True, 'purchase_method': 'purchase'})
po = env['purchase.order'].create({'partner_id': ted.id, 'order_line': [(0, 0, {'product_id': mal.id, 'product_qty': 5, 'price_unit': 200, 'tax_ids': [(5, 0, 0)]})]})
po.button_confirm()
po.action_create_invoice()
bekleyen = po.invoice_ids
bekleyen.invoice_date = date(2026, 9, 1)
bekleyen.action_post()
siparissiz = env['account.move'].create({'move_type': 'in_invoice', 'partner_id': ted.id, 'invoice_date': date(2026, 9, 1),
                                         'invoice_line_ids': [(0, 0, {'name': 'Kira', 'quantity': 1, 'price_unit': 300, 'tax_ids': [(5, 0, 0)]})]})
siparissiz.action_post()
ok(bekleyen.ucyol_durum == 'hayir' and siparissiz.ucyol_durum == 'evet', "teslim alınmamış sipariş faturası bekliyor, siparişsiz ödenebilir")

# engel kapalıyken her şey eklenir
w = env['atlas.odeme.talimat.ekle'].with_context(active_model='account.move', active_ids=(bekleyen | siparissiz).ids).create(
    {'journal_id': banka.id, 'tarih': date(2026, 10, 5)})
t1 = env['atlas.odeme.talimat'].browse(w.action_ekle()['res_id'])
ok(len(t1.satir_ids.move_ids) == 2 and t1.satir_ids.ucyol_durum == 'hayir', "engel kapalı: iki fatura eklendi, satırda eşleştirme durumu görünür")
t1.unlink()

# engel açık
sirket.ucyol_odeme_engeli = True
w = env['atlas.odeme.talimat.ekle'].with_context(active_model='account.move', active_ids=(bekleyen | siparissiz).ids).create(
    {'journal_id': banka.id, 'tarih': date(2026, 10, 5)})
t2 = env['atlas.odeme.talimat'].browse(w.action_ekle()['res_id'])
ok(t2.satir_ids.move_ids == siparissiz and 'eklenmeyen' in t2.message_ids[:1].body and bekleyen.name in t2.message_ids[:1].body,
   "engel açık: ödenebilir olmayan fatura eklenmez, talimata not düşülür")
try:
    env['atlas.odeme.talimat.ekle'].with_context(active_model='account.move', active_ids=bekleyen.ids).create(
        {'journal_id': banka.id}).action_ekle(); hic = False
except UserError:
    hic = True
ok(hic, "yalnız ödenemeyen faturalar seçilirse uyarı")
alan = env['atlas.odeme.talimat.satir']._fields['move_ids'].domain
ok("ucyol_durum" in alan, "satırda fatura seçimi ödenebilir faturalarla sınırlı")

# talimata sonradan elle eklenen ödenemeyen fatura onayda yakalanır
t2.satir_ids.write({'move_ids': [(4, bekleyen.id)], 'tutar': 1300})
try:
    with env.cr.savepoint():
        t2.action_onayla(); onaylandi = True
except UserError as e:
    onaylandi = False
    mesaj = str(e)
ok(not onaylandi and bekleyen.name in mesaj and 'Teslimat bekleniyor' in mesaj, "onayda ödenemeyen fatura adıyla birlikte reddedilir")
bekleyen.action_ucyol_serbest()
t2.action_onayla()
ok(t2.durum == 'onaylandi' and bekleyen.payment_state in ('paid', 'in_payment'), "elle serbest bırakılınca talimat onaylanır, fatura ödenir")
env.cr.rollback(); print("(geri alındı)")
