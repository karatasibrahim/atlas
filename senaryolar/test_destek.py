from datetime import timedelta
from odoo import fields
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
T = env['atlas.destek.talep']
ekip = env.ref('atlas_destek.ekip_musteri')
u1 = env['res.users'].create({'name': 'DST Ayşe', 'login': 'dst_ayse', 'group_ids': [Command.link(env.ref('atlas_destek.group_destek_user').id)]})
u2 = env['res.users'].create({'name': 'DST Mehmet', 'login': 'dst_mehmet', 'group_ids': [Command.link(env.ref('atlas_destek.group_destek_user').id)]})
ekip.write({'user_ids': [Command.set((u1 | u2).ids)], 'atama': 'yuk'})
T.search([('ekip_id', '=', ekip.id), ('kapali', '=', False)]).write({'asama_id': env.ref('atlas_destek.asama_iptal').id})
mus = env['res.partner'].create({'name': 'DST Müşteri A.Ş.', 'is_company': True, 'email': 'musteri@dst.local'})
t1 = T.create({'baslik': 'Yazıcı çalışmıyor', 'partner_id': mus.id, 'oncelik': '2', 'tip_id': env.ref('atlas_destek.tip_ariza').id})
t2 = T.create({'baslik': 'Fatura sorusu', 'partner_id': mus.id, 'oncelik': '1'})
ok(t1.name.startswith('DST') and t1.asama_id == env.ref('atlas_destek.asama_yeni') and {t1.user_id, t2.user_id} == {u1, u2},
   f"talepler {t1.name}, {t2.name}: en az yüklü üyeye dağıtıldı")
ok(len(t1.sla_durum_ids) == 2 and len(t2.sla_durum_ids) == 1, "yüksek öncelik 2 SLA, normal 1 SLA")
s4 = t1.sla_durum_ids.filtered(lambda d: d.sla_id == env.ref('atlas_destek.sla_acil_yanit'))
ok(s4.deadline and s4.deadline > t1.create_date and s4.durum == 'devam', f"4 iş saati SLA son tarihi: {s4.deadline}")
t1.asama_id = env.ref('atlas_destek.asama_islemde')
ok(s4.ulasildi and s4.durum == 'basarili', "işleme alındı: yanıt SLA'sı zamanında")
cozum = t1.sla_durum_ids - s4
cozum.deadline = fields.Datetime.now() - timedelta(hours=1)
T._cron_sla()
ok(cozum.durum == 'ihlal' and t1.sla_ihlal, "süresi geçen çözüm SLA'sı ihlal")
ok(t1 in T.search([('sla_ihlal', '=', True)]), "SLA ihlali filtresi")
t1.with_user(u1).message_post(body='Sürücüyü güncelleyin lütfen.', message_type='comment', subtype_xmlid='mail.mt_comment')
ok(t1.ilk_yanit, "personel yanıtı ilk yanıt olarak kaydedildi")
t1.asama_id = env.ref('atlas_destek.asama_cozuldu')
anket = t1.message_ids.filtered(lambda m: '/rate/' in (m.body or ''))
ok(t1.kapali and t1.kapanis_tarihi and t1.cozum_saat >= 0 and anket and cozum.ulasildi, "çözüldü: kapandı, memnuniyet anketi gönderildi")
yeni = T.message_new({'subject': 'Sipariş durumu?', 'email_from': 'Ali Veli <ali@dst-yeni.local>', 'body': '<p>Siparişim nerede?</p>',
                      'to': 'destek@local'}, {'ekip_id': ekip.id})
ok(yeni.kanal == 'eposta' and yeni.partner_id.email == 'ali@dst-yeni.local' and yeni.baslik == 'Sipariş durumu?' and yeni.user_id,
   "e-postadan talep: müşteri oluşturuldu ve atandı")
portal = env['res.users'].create({'name': 'DST Portal', 'login': 'dst_portal', 'partner_id': mus.id,
                                  'group_ids': [Command.set([env.ref('base.group_portal').id])]})
gorunen = T.with_user(portal).search([])
ok(set(gorunen.ids) == {t1.id, t2.id}, "portal kullanıcısı yalnızca kendi şirketinin taleplerini görür")
ok(t1.access_url == f'/my/destek/{t1.id}' and ekip.alias_name == 'destek', "portal adresi ve e-posta takma adı")
env.cr.rollback(); print("(geri alındı)")
