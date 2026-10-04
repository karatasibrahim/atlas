import base64
from datetime import date
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
B = env['atlas.belge']; K = env['atlas.belge.klasor']
genel = env.ref('atlas_belgeler.klasor_genel'); ik = env.ref('atlas_belgeler.klasor_ik'); satis = env.ref('atlas_belgeler.klasor_satis')
u1 = env['res.users'].create({'name': 'BLG Satışçı', 'login': 'blg_satis', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
u2 = env['res.users'].create({'name': 'BLG Satış Müdürü', 'login': 'blg_mudur', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
satis.write({'yazma_user_ids': [Command.set(u2.ids)]})
alt = K.create({'name': 'Teklifler', 'parent_id': satis.id})
ok(u1.has_group('atlas_belgeler.group_belge_user'), "her iç kullanıcı belge kullanıcısı")
gorunen = K.with_user(u1).search([])
ok(genel in gorunen and satis in gorunen and alt in gorunen and ik not in gorunen, "İK klasörü yalnızca yöneticilere açık")
b64 = lambda b: base64.b64encode(b).decode()
d1 = B.create({'dosya_adi': 'prosedur.txt', 'dosya': b64(b'Kalite proseduru v1'), 'klasor_id': genel.id})
ok(d1.name == 'prosedur.txt' and d1.mimetype == 'text/plain' and d1.boyut == 19, "belge: ad dosyadan, tür ve boyut")
ok(B.with_user(u1).browse(d1.id).dosya.content == b'Kalite proseduru v1' and d1 in B.with_user(u1).search([]), "kullanıcı belgeyi görüyor ve içeriğini okuyabiliyor")
d_ik = B.create({'dosya_adi': 'bordro.txt', 'dosya': b64(b'gizli'), 'klasor_id': ik.id})
ok(d_ik not in B.with_user(u1).search([]), "İK belgesi diğer kullanıcıya görünmez")
try:
    with env.cr.savepoint():
        B.with_user(u1).create({'dosya_adi': 'u1.txt', 'dosya': b64(b'x'), 'klasor_id': alt.id}); env.flush_all(); yazdi = True
except AccessError:
    yazdi = False
    env.invalidate_all()
ok(not yazdi, "alt klasör üstün yazma kısıtını devraldı: satışçı yazamaz")
d2 = B.with_user(u2).create({'dosya_adi': 'teklif.txt', 'dosya': b64(b'teklif'), 'klasor_id': alt.id})
ok(d2.exists() and B.with_user(u1).search_count([('id', '=', d2.id)]) == 1, "müdür yazdı, satışçı okuyabiliyor")
d1.yeni_surum(b'Kalite proseduru v2')
ok(d1.surum == 2 and len(d1.surum_ids) == 1 and d1.dosya.content == b'Kalite proseduru v2' and d1.surum_ids.dosya.content == b'Kalite proseduru v1',
   "yeni sürüm: v2, önceki sürüm saklandı")
d1.action_kilitle()
try:
    with env.cr.savepoint(): B.with_user(u1).browse(d1.id).write({'name': 'degisti.txt'}); kilit = False
except UserError: kilit = True
ok(kilit and d1.kilitleyen_id == env.user, "kilitli belgeyi başkası değiştiremez")
ted = env['res.partner'].create({'name': 'BLG Tedarikçi', 'is_company': True, 'atlas_cari_tipi': 'satici'})
fatura = env['account.move'].create({'move_type': 'in_invoice', 'partner_id': ted.id, 'invoice_date': date(2026, 9, 1),
                                      'invoice_line_ids': [Command.create({'name': 'K', 'quantity': 1, 'price_unit': 10, 'tax_ids': False})]})
ek = env['ir.attachment'].create({'name': 'fatura.pdf', 'raw': b'%PDF-1.4 sahte', 'res_model': 'account.move', 'res_id': fatura.id})
bd = B.search([('kaynak_ek_id', '=', ek.id)])
ok(bd.klasor_id == env.ref('atlas_belgeler.klasor_gelen_fatura') and bd.partner_id == ted and env.ref('atlas_belgeler.etiket_fatura') in bd.etiket_ids
   and bd.ilgili_kayit, f"fatura eki otomatik belgeye düştü (ilgili kayıt: {bd.ilgili_kayit})")
e1 = env['ir.attachment'].create({'name': 'a.txt', 'raw': b'a', 'res_model': 'atlas.belge.yukle'})
e2 = env['ir.attachment'].create({'name': 'b.txt', 'raw': b'b', 'res_model': 'atlas.belge.yukle'})
w = env['atlas.belge.yukle'].create({'klasor_id': genel.id, 'ek_ids': [Command.set((e1 | e2).ids)], 'etiket_ids': [Command.set(env.ref('atlas_belgeler.etiket_sozlesme').ids)]})
yeni = B.search(w.action_yukle()['domain'])
ok(len(yeni) == 2 and all(yeni.mapped('dosya_adi')) and not (e1 | e2).exists(), "toplu yükleme: 2 belge, geçici ekler silindi")
p = env['atlas.belge.paylasim'].browse(d2.action_paylas()['res_id'])
ok(p.token and p.url.endswith(p.token) and p._gecerli() and p.belge_ids == d2, "paylaşım bağlantısı oluşturuldu")
env.cr.rollback(); print("(geri alındı)")
