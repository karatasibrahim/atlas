import base64, io
from reportlab.pdfgen import canvas
from odoo.exceptions import UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
B = env['atlas.belge']
b64 = lambda b: base64.b64encode(b).decode()


def pdf():
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    c.drawString(100, 750, 'Fatura No: ABC2025000000123')
    c.save()
    return tampon.getvalue()


kopruler = env['ir.module.module'].search([('name', 'like', 'atlas_belgeler_%'), ('state', '=', 'installed')])
ok(len(kopruler) == 11 and all(m.auto_install for m in kopruler), f"11 köprü modülü kurulu ve auto_install ({len(kopruler)})")
klasor = lambda x: env.ref(x)
ok(klasor('atlas_belgeler_muhasebe.klasor_banka').parent_id == klasor('atlas_belgeler.klasor_muhasebe')
   and klasor('atlas_belgeler_filo.klasor_arac').parent_id == klasor('atlas_belgeler_filo.klasor_filo'), "köprü klasörleri hiyerarşide")

# --- Otomatik dosyalama: çalışan, ürün, proje ekleri ilgili klasöre
calisan = env['hr.employee'].create({'name': 'BK Çalışan'})
ek = env['ir.attachment'].create({'name': 'kimlik.pdf', 'raw': pdf(), 'res_model': 'hr.employee', 'res_id': calisan.id})
belge = B.search([('kaynak_ek_id', '=', ek.id)])
ok(belge.klasor_id == klasor('atlas_belgeler_ik.klasor_calisan') and belge.ilgili_kayit == 'BK Çalışan', "çalışan eki → İK / Çalışanlar")
urun = env['product.template'].create({'name': 'BK Ürün'})
ek2 = env['ir.attachment'].create({'name': 'teknik.pdf', 'raw': pdf(), 'res_model': 'product.template', 'res_id': urun.id})
ok(B.search([('kaynak_ek_id', '=', ek2.id)]).klasor_id == klasor('atlas_belgeler_urun.klasor_urun'), "ürün eki → Ürünler")

# --- Belgeden tedarikçi faturası (Enterprise "Tedarikçi Faturası" eylemi)
tedarikci = env['res.partner'].create({'name': 'BK Tedarikçi', 'is_company': True})
gelen = B.create({'name': 'fatura.pdf', 'dosya_adi': 'fatura.pdf', 'dosya': b64(pdf()), 'partner_id': tedarikci.id,
                  'klasor_id': klasor('atlas_belgeler.klasor_gelen_fatura').id})
eylem = gelen.action_belge_tedarikci_faturasi()
fat = env['account.move'].browse(eylem['res_id'])
ok(fat.move_type == 'in_invoice' and fat.state == 'draft' and fat.partner_id == tedarikci, "belgeden taslak tedarikçi faturası")
ok(gelen.res_model == 'account.move' and gelen.res_id == fat.id and fat.message_main_attachment_id.name == 'fatura.pdf',
   "belge faturaya bağlandı, PDF faturanın ana eki")
ok(B.search_count([('res_model', '=', 'account.move'), ('res_id', '=', fat.id)]) == 1, "faturaya eklenen dosya ikinci kez belgeye çevrilmedi")
try:
    with env.cr.savepoint():
        gelen.action_belge_musteri_faturasi(); tekrar = True
except UserError:
    tekrar = False
ok(not tekrar, "kayda bağlı belgeden ikinci kayıt oluşturulmaz")
coklu = B.create([{'name': f'f{i}.pdf', 'dosya_adi': f'f{i}.pdf', 'dosya': b64(pdf()), 'klasor_id': klasor('atlas_belgeler.klasor_genel').id} for i in range(2)])
e2 = coklu.action_belge_mahsup()
ok(e2['res_model'] == 'account.move' and len(env['account.move'].search(e2['domain'])) == 2, "çoklu seçimde her belgeye bir mahsup fişi")

# --- Masraf, aday, imza
env.user.employee_id = calisan if not env.user.employee_id else env.user.employee_id
fis = B.create({'name': 'taksi.pdf', 'dosya_adi': 'taksi.pdf', 'dosya': b64(pdf()), 'klasor_id': klasor('atlas_belgeler.klasor_genel').id})
masraf = env['hr.expense'].browse(fis.action_belge_masraf()['res_id'])
ok(masraf.name == 'taksi.pdf' and fis.res_model == 'hr.expense', "belgeden masraf")
cv = B.create({'name': 'ahmet_yilmaz_cv.pdf', 'dosya_adi': 'ahmet_yilmaz_cv.pdf', 'dosya': b64(pdf()), 'klasor_id': klasor('atlas_belgeler_ise_alim.klasor_ise_alim').id})
aday = env['hr.applicant'].browse(cv.action_belge_aday()['res_id'])
ok(aday.partner_name == 'ahmet yilmaz cv' and cv.ilgili_kayit, f"belgeden aday: {aday.partner_name}")
sz = B.create({'name': 'sozlesme.pdf', 'dosya_adi': 'sozlesme.pdf', 'dosya': b64(pdf()), 'klasor_id': klasor('atlas_belgeler.klasor_genel').id})
talep = env['atlas.imza.talep'].browse(sz.action_belge_imza()['res_id'])
ok(talep.konu == 'sozlesme.pdf' and talep.dosya, "belgeden imza talebi")

# --- Kayda bağla sihirbazı (araç, çalışan …)
arac = env['fleet.vehicle'].create({'model_id': env['fleet.vehicle.model'].search([], limit=1).id or env['fleet.vehicle.model'].create(
    {'name': 'BK Model', 'brand_id': env['fleet.vehicle.model.brand'].create({'name': 'BK Marka'}).id}).id, 'license_plate': '34 BK 001'})
ruhsat = B.create({'name': 'ruhsat.pdf', 'dosya_adi': 'ruhsat.pdf', 'dosya': b64(pdf()), 'klasor_id': klasor('atlas_belgeler_filo.klasor_arac').id})
W = env['atlas.belge.bagla'].with_context(active_model='atlas.belge', active_ids=ruhsat.ids)
modeller = dict(W._modeller())
ok({'fleet.vehicle', 'hr.employee', 'project.task', 'account.move', 'res.partner'} <= set(modeller), "bağlanabilir modeller köprülerden geliyor")
W.create({'kayit': f'fleet.vehicle,{arac.id}'}).action_bagla()
ok(ruhsat.res_model == 'fleet.vehicle' and ruhsat.res_id == arac.id and env['ir.attachment'].search_count(
    [('res_model', '=', 'fleet.vehicle'), ('res_id', '=', arac.id)]) == 1, "belge araca bağlandı, dosya aracın eklerinde")

# --- Banka ekstresi eylemi yalnız Excel
try:
    with env.cr.savepoint():
        sz.action_belge_ekstre(); xlsx_degil = False
except UserError:
    xlsx_degil = True
ok(xlsx_degil, "ekstre biçiminde olmayan (PDF) belge ekstre olarak aktarılmaz")
x = B.create({'name': 'ekstre.xlsx', 'dosya_adi': 'ekstre.xlsx', 'dosya': b64(b'PK\x03\x04'), 'klasor_id': klasor('atlas_belgeler_muhasebe.klasor_banka').id})
ok(x.action_belge_ekstre()['res_model'] == 'atlas.banka.ekstre.import', "Excel ekstre: içe aktarma sihirbazı açılıyor")
env.cr.rollback(); print("(geri alındı)")
