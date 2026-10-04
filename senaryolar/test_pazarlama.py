from datetime import timedelta
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
etiket = env['res.partner.category'].create({'name': 'PZR Bülten'})
ilgili = env['res.partner.category'].create({'name': 'PZR İlgili'})
P = env['res.partner']
p1, p2, p3 = (P.create({'name': f'PZR Kişi {i}', 'email': f'kisi{i}@pzr.local', 'category_id': [Command.set(etiket.ids)]}) for i in (1, 2, 3))
P.create({'name': 'PZR Dışarıda', 'email': 'disari@pzr.local'})
eylem = env['ir.actions.server'].create({'name': 'PZR İlgili etiketi', 'model_id': env.ref('base.model_res_partner').id, 'state': 'code',
                                         'code': f"records.write({{'category_id': [(4, {ilgili.id})]}})"})
K = env['atlas.pazarlama.kampanya']
k = K.create({'name': 'PZR Karşılama', 'model_id': env.ref('base.model_res_partner').id, 'domain': f"[('category_id', 'in', [{etiket.id}])]",
              'benzersiz_alan_id': env['ir.model.fields']._get('res.partner', 'email').id})
A = env['atlas.pazarlama.aktivite']
a_hos = A.create({'kampanya_id': k.id, 'name': 'Hoş geldin', 'tur': 'eposta', 'konu': 'Hoş geldiniz', 'govde': '<p>Merhaba, <a href="https://atlas.local/katalog">kataloğumuz</a></p>'})
a_acti = A.create({'kampanya_id': k.id, 'name': 'Açanı işaretle', 'tur': 'eylem', 'eylem_id': eylem.id, 'parent_id': a_hos.id, 'tetik': 'acildi'})
a_hatir = A.create({'kampanya_id': k.id, 'name': 'Hatırlatma', 'tur': 'eposta', 'konu': 'Unutmayın', 'govde': '<p>Hatırlatma</p>',
                    'parent_id': a_hos.id, 'tetik': 'acilmadi', 'bekleme': 2, 'bekleme_birim': 'gun'})
try:
    with env.cr.savepoint(): A.create({'kampanya_id': k.id, 'name': 'x', 'tur': 'eylem', 'eylem_id': eylem.id, 'tetik': 'acildi'}); gecti = True
except ValidationError: gecti = False
ok(not gecti, "önceki adımı olmayan adım olay tetikleyicisi alamaz")
try:
    with env.cr.savepoint(): a_hos.parent_id = a_hatir; env.flush_all(); dongu = True
except (ValidationError, UserError): dongu = False
env.invalidate_all()
ok(not dongu, "adımlar döngü oluşturamaz")
try:
    with env.cr.savepoint(): k.action_simdi_calistir(); calisti = True
except UserError: calisti = False
ok(not calisti, "başlatılmadan çalıştırılamaz")
k.action_baslat()
ok(k.durum == 'calisiyor' and a_hos.mailing_id and a_hos.mailing_id.subject == 'Hoş geldiniz', "başlatıldı, e-posta adımı için toplu e-posta kaydı hazır")
onceki = env['mail.mail'].search([], order='id desc', limit=1).id or 0
k.action_simdi_calistir()
ok(k.katilimci_sayisi == 3 and set(k.katilimci_ids.mapped('res_id')) == {p1.id, p2.id, p3.id}, "kitleye uyan 3 kişi katıldı")
iz_hos = a_hos.iz_ids
ok(len(iz_hos) == 3 and all(i.durum == 'yapildi' and i.mailing_trace_id for i in iz_hos), "hoş geldin e-postası 3 kişiye: izlenebilir")
mailler = env['mail.mail'].search([('id', '>', onceki), ('mailing_id', '=', a_hos.mailing_id.id)])
ok(len(mailler) == 3 and 'Hoş geldiniz' in mailler[0].subject, "3 e-posta kuyruğa alındı")
ok(len(a_acti.iz_ids) == 3 and all(not i.planlanan for i in a_acti.iz_ids) and len(a_hatir.iz_ids) == 3 and all(i.planlanan for i in a_hatir.iz_ids),
   "dallar planlandı: 'açıldı' olay bekliyor, 'açılmadı' 2 gün sonra")
iz_hos.filtered(lambda i: i.katilimci_id.res_id == p1.id).mailing_trace_id.set_opened()
k.action_simdi_calistir()
ok(ilgili in p1.category_id and ilgili not in p2.category_id, "e-postayı açan kişi işaretlendi (sunucu eylemi)")
a_hatir.iz_ids.write({'planlanan': fields.Datetime.now() - timedelta(minutes=1)})
onceki = env['mail.mail'].search([], order='id desc', limit=1).id or 0
k.action_simdi_calistir()
hatir = {i.katilimci_id.res_id: i.durum for i in a_hatir.iz_ids}
ok(hatir[p1.id] == 'atlandi' and hatir[p2.id] == 'yapildi' and hatir[p3.id] == 'yapildi', "hatırlatma: açan atlandı, açmayan 2 kişiye gitti")
ok(env['mail.mail'].search_count([('id', '>', onceki), ('mailing_id', '=', a_hatir.mailing_id.id)]) == 2, "2 hatırlatma e-postası")
ok(a_hos.gonderilen == 3 and a_hos.acilan == 1 and k.acilan_orani > 0, "istatistikler: gönderilen 3, açılan 1")
p1_kat = k.katilimci_ids.filtered(lambda p: p.res_id == p1.id)
ok(p1_kat.durum == 'tamamlandi', "tüm adımları biten katılımcı tamamlandı")
P.create({'name': 'PZR Kopya', 'email': 'KISI1@pzr.local ', 'category_id': [Command.set(etiket.ids)]})
p5 = P.create({'name': 'PZR Yeni', 'email': 'yeni@pzr.local', 'category_id': [Command.set(etiket.ids)]})
k.action_simdi_calistir()
ok(k.katilimci_sayisi == 4 and p5.id in k.katilimci_ids.mapped('res_id'), "sonradan kitleye uyan yeni kişi katıldı, aynı e-postalı kopya alınmadı")
iz_eski = a_acti.iz_ids.filtered(lambda i: i.katilimci_id.res_id == p2.id)
iz_eski.parent_iz_id.yapilma = fields.Datetime.now() - timedelta(days=31)
k.action_simdi_calistir()
ok(iz_eski.durum == 'iptal', "30 günde gerçekleşmeyen olay adımı iptal edildi")
p5_kat = k.katilimci_ids.filtered(lambda p: p.res_id == p5.id)
p5_kat.action_cikar()
ok(p5_kat.durum == 'cikarildi' and not p5_kat.iz_ids.filtered(lambda i: i.durum == 'bekliyor'), "katılımcı çıkarıldı, bekleyen adımları iptal")
a_filtre = A.create({'kampanya_id': k.id, 'name': 'Yalnız ilgililere', 'tur': 'eylem', 'eylem_id': eylem.id, 'parent_id': a_acti.id, 'tetik': 'sonra',
                     'filtre': "[('email', 'ilike', 'kisi2')]"})
ok(a_filtre.parent_id == a_acti, "adım filtresi tanımlandı")
k.action_durdur()
ok(k.durum == 'durduruldu', "kampanya durduruldu")
env.cr.rollback(); print("(geri alındı)")
