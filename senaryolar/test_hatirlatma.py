from datetime import timedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']; M = env['account.move']; bugun = fields.Date.context_today(P)
s1, s2, s3 = (env.ref(f'atlas_hatirlatma.seviye_{i}') for i in (1, 2, 3))
def fatura(partner, gecikme, tutar):
    m = M.create({'move_type': 'out_invoice', 'partner_id': partner.id, 'invoice_date': bugun - timedelta(days=gecikme + 30),
                  'invoice_date_due': bugun - timedelta(days=gecikme),
                  'invoice_line_ids': [Command.create({'name': 'Mal', 'quantity': 1, 'price_unit': tutar, 'tax_ids': False})]})
    m.action_post(); return m
mus = P.create({'name': 'HTR Müşteri', 'is_company': True, 'atlas_cari_tipi': 'alici', 'email': 'htr@test.local'})
fa = fatura(mus, 40, 1000); fb = fatura(mus, 10, 500); fc = fatura(mus, -5, 300)
mus.invalidate_recordset()
ok(mus.atlas_gecikmis_tutar == 1500 and mus.atlas_en_eski_gecikme == 40 and mus.atlas_sonraki_seviye_id == s2,
   f"gecikmiş 1.500 (vadesi gelmeyen 300 hariç), en eski 40 gün, sıradaki: {mus.atlas_sonraki_seviye_id.name}")
ok(mus in P.search([('atlas_hatirlatma_gerekli', '=', True)]) and mus in P.search([('atlas_gecikmis_var', '=', True)]), "listede 'hatırlatma gerekli'")
mesaj_once = len(mus.message_ids)
mus.action_atlas_hatirlatma_gonder()
msg = mus.message_ids[:1]
la, lb = fa.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable'), fb.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
ok(msg.subject == s2.konu and msg.attachment_ids and 'HTR Müşteri' in msg.body and fa.name in msg.body, f"e-posta: '{msg.subject}', ekte mektup, gecikmiş kalem tablosu")
ok(la.atlas_hatirlatma_seviye_id == s2 and lb.atlas_hatirlatma_seviye_id == s1, "kalem bazında gönderilen seviye: A→İkinci, B→İlk")
g = mus.atlas_hatirlatma_gecmis_ids
ok(len(g) == 1 and g.seviye_id == s2 and g.tutar == 1500 and 'e-posta' in g.kanal, "geçmiş kaydı")
mus.invalidate_recordset()
try:
    mus.action_atlas_hatirlatma_gonder(); tekrar = True
except UserError: tekrar = False
ok(not tekrar and not mus.atlas_hatirlatma_gerekli, "aynı seviye tekrar gönderilmedi")
fd = fatura(mus, 70, 2000)
sorumlu = env['res.users'].search([('share', '=', False)], limit=1)
mus.atlas_tahsilat_sorumlusu_id = sorumlu
mus.invalidate_recordset()
ok(mus.atlas_sonraki_seviye_id == s3, "70 gün gecikmiş yeni fatura → Son uyarı")
mus.action_atlas_hatirlatma_gonder()
ok(mus.activity_ids.filtered(lambda a: a.user_id == sorumlu and 'Son uyarı' in a.summary), "son uyarıda tahsilat sorumlusuna görev açıldı")
pay = env['account.payment.register'].with_context(active_model='account.move', active_ids=fd.ids).create({})._create_payments()
mus.invalidate_recordset()
ok(mus.atlas_gecikmis_tutar == 1500, "ödenen fatura gecikmişten düştü")
mus2 = P.create({'name': 'HTR Durdurulan', 'is_company': True, 'atlas_cari_tipi': 'alici', 'email': 'x@test.local', 'atlas_hatirlatma_durdur': True})
fatura(mus2, 15, 100); mus2.invalidate_recordset()
ok(mus2.atlas_gecikmis_tutar == 100 and not mus2.atlas_hatirlatma_gerekli, "hatırlatması durdurulan cariye gönderilmez")
mus3 = P.create({'name': 'HTR Otomatik', 'is_company': True, 'atlas_cari_tipi': 'alici', 'email': 'y@test.local'})
f3 = fatura(mus3, 8, 250); s1.otomatik = True
P._cron_atlas_hatirlatma()
ok(mus3.atlas_hatirlatma_gecmis_ids.seviye_id == s1 and not mus2.atlas_hatirlatma_gecmis_ids, "otomatik görev ilk seviyeyi gönderdi, durdurulana göndermedi")
mus4 = P.create({'name': 'HTR Epostasız', 'is_company': True, 'atlas_cari_tipi': 'alici'})
fatura(mus4, 9, 50); mus4.action_atlas_hatirlatma_gonder()
ok('e-posta adresi yok' in mus4.message_ids[:1].body, "e-postası olmayan cari için not düşüldü")
html = env['ir.actions.report']._render_qweb_html('atlas_hatirlatma.report_hatirlatma', mus.ids)[0]
ok('Ödeme Hatırlatma Mektubu'.encode() in html and fa.name.encode() in html and fc.name.encode() not in html, "hatırlatma mektubu: gecikmiş faturalar var, vadesi gelmeyen yok")
env.cr.rollback(); print("(geri alındı)")
