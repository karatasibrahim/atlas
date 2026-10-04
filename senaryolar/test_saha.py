import base64
import io
from PIL import Image, ImageDraw
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
proje = env.ref('atlas_saha.proje_saha')
U = env['res.users'].with_context(no_reset_password=True)
tek = U.create({'name': 'SHA Teknisyen', 'login': 'sha_tek', 'group_ids': [Command.set([env.ref('base.group_user').id, env.ref('project.group_project_user').id,
                                                                                         env.ref('hr_timesheet.group_hr_timesheet_user').id])]})
e = env['hr.employee'].create({'name': 'SHA Teknisyen', 'user_id': tek.id})
mus = env['res.partner'].create({'name': 'SHA Müşteri A.Ş.', 'is_company': True, 'street': 'Atatürk Cd. 10', 'city': 'İzmir',
                                 'country_id': env.ref('base.tr').id, 'email': 'sha@musteri.local'})
urun = env['product.product'].create({'name': 'SHA Filtre', 'is_storable': True, 'list_price': 120, 'sale_ok': True})
stok = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1).lot_stock_id
env['stock.quant']._update_available_quantity(urun, stok, 5)
t = env['project.task'].with_user(tek).create({'name': 'Kombi bakımı', 'project_id': proje.id, 'partner_id': mus.id, 'user_ids': [Command.set(tek.ids)]})
ok(t.atlas_saha and len(t.atlas_kontrol_ids) == 3 and t.atlas_kontrol_ids.filtered('zorunlu').mapped('name')[0].startswith('İş güvenliği'),
   "saha görevi: şablondan 3 kontrol maddesi geldi")
ok('İzmir' in t.atlas_adres and 'google.com/maps/dir' in t.action_atlas_yol_tarifi()['url'], "adres ve yol tarifi bağlantısı")
try:
    with env.cr.savepoint(): t.with_user(tek).action_atlas_tamamla(); bitti = True
except UserError: bitti = False
ok(not bitti, "zorunlu kontroller yapılmadan tamamlanamaz")
t.atlas_kontrol_ids.filtered('zorunlu').write({'yapildi': True})
try:
    with env.cr.savepoint(): t.with_user(tek).action_atlas_tamamla(); bitti = True
except UserError: bitti = False
ok(not bitti, "imzasız tamamlanamaz (imza zorunlu)")
env['account.analytic.line'].with_user(tek).create({'employee_id': e.id, 'project_id': proje.id, 'task_id': t.id, 'unit_amount': 2, 'name': 'Bakım'})
t.with_user(tek).write({'atlas_malzeme_ids': [Command.create({'product_id': urun.id, 'miktar': 2})], 'atlas_is_raporu': '<p>Filtre değişti.</p>'})
ok(t.atlas_malzeme_ids.fiyat == 120 and t.atlas_malzeme_ids.tutar == 240 and t.atlas_kontrol_ozet == '2/3', "malzeme fiyatı ve kontrol özeti")
r = Image.new('RGBA', (300, 100), (0, 0, 0, 0)); ImageDraw.Draw(r).line([(10, 80), (150, 20), (290, 70)], fill=(0, 0, 0, 255), width=3)
tampon = io.BytesIO(); r.save(tampon, 'PNG')
t.with_user(tek).write({'atlas_imza': base64.b64encode(tampon.getvalue()).decode(), 'atlas_imzalayan': 'Ayşe Müşteri'})
ok(t.atlas_imza_tarihi, "imza tarihi kaydedildi")
t.with_user(tek).action_atlas_tamamla()
t = t.sudo(); so = t.atlas_siparis_id
cevir = lambda tutar: env.company.currency_id._convert(tutar, so.currency_id, env.company, so.date_order.date())
ok(t.state == '1_done' and t.atlas_tamamlanma and so.state == 'sale', "tamamlandı: görev bitti, sipariş onaylandı")
iscilik = so.order_line.filtered(lambda l: l.product_id == proje.atlas_hizmet_urun_id)
ok(iscilik.product_uom_qty == 2 and so.currency_id.is_zero(iscilik.price_unit - cevir(750)) and so.order_line.filtered(lambda l: l.product_id == urun).product_uom_qty == 2,
   f"siparişte 2 saat işçilik ve 2 filtre ({so.currency_id.name})")
ok(all(p.state == 'done' for p in so.picking_ids) and urun.qty_available == 3, "malzeme çıkışı yapıldı, stok 5 → 3")
fatura = so.invoice_ids
ok(len(fatura) == 1 and fatura.state == 'draft' and abs(fatura.amount_untaxed - cevir(2 * 750 + 240)) < 0.05, f"fatura taslağı: {fatura.amount_untaxed} {fatura.currency_id.name}")
ek = t.message_ids.attachment_ids.filtered(lambda a: a.name.startswith('Servis Raporu'))
ok(ek and ek.mimetype == 'application/pdf', "imzalı servis raporu PDF olarak eklendi")
ok(t.with_user(tek).action_atlas_rapor_gonder()['res_model'] == 'mail.compose.message', "rapor gönderme sihirbazı")
try:
    with env.cr.savepoint(): t.with_user(tek).action_atlas_tamamla(); iki = True
except UserError: iki = False
ok(not iki, "ikinci kez tamamlanamaz")
p2 = env['project.project'].create({'name': 'SHA Garanti', 'atlas_saha': True, 'allow_timesheets': True, 'atlas_faturala': False, 'atlas_imza_zorunlu': False})
t2 = env['project.task'].create({'name': 'Garanti değişimi', 'project_id': p2.id, 'partner_id': mus.id})
t2.action_atlas_tamamla()
ok(t2.state == '1_done' and not t2.atlas_siparis_id, "faturasız/imzasız proje: sipariş oluşmadan tamamlandı")
ok(not env['project.task'].create({'name': 'Normal görev', 'project_id': env['project.project'].create({'name': 'SHA Normal'}).id}).atlas_saha, "normal proje görevi saha değil")
env.cr.rollback(); print("(geri alındı)")
