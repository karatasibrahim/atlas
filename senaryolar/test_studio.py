from lxml import etree
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.addons.atlas_studio.models.atlas_studio import teknik_ad
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
ok(teknik_ad('Teslim Şekli') == 'x_atlas_teslim_sekli' and teknik_ad('İç Ölçü (mm)') == 'x_atlas_ic_olcu_mm', "Türkçe etiketten teknik ad")
M = 'atlas.onay.kategori'
mid = env['ir.model']._get_id(M)
A = env['atlas.studio.alan']
w = A.create({'model_id': mid, 'etiket': 'Bütçe Grubu', 'tur': 'selection', 'secenekler': 'Yatırım\nGider\nop:Operasyonel',
              'hedef_alan_id': env['ir.model.fields']._get(M, 'min_onay').id, 'aramaya_ekle': True})
ok(w.teknik == 'x_atlas_butce_grubu' and w.form_view_id, "sihirbaz: teknik ad ve form görünümü otomatik")
w.action_ekle()
alan = env[M]._fields.get('x_atlas_butce_grubu')
ok(alan and alan.type == 'selection' and [k for k, _ in alan.selection] == ['yatirim', 'gider', 'op'], "seçim alanı oluştu, seçenekler doğru")
form = etree.fromstring(env[M].get_view(w.form_view_id.id, 'form')['arch'])
f = form.xpath("//field[@name='min_onay']")[0]
ok(f.getnext() is not None and f.getnext().get('name') == 'x_atlas_butce_grubu', "formda min_onay alanının hemen sonrasına eklendi")
liste = etree.fromstring(env[M].get_view(env['ir.model']._atlas_studio_view(M, 'list').id, 'list')['arch'])
ok(liste.xpath("//field[@name='x_atlas_butce_grubu'][@optional='show']") and not env['ir.model']._atlas_studio_view(M, 'search'),
   "listeye eklendi (arama görünümü olmayan modelde arama adımı atlanır)")
kat = env.ref('atlas_onay.kategori_odeme'); kat.x_atlas_butce_grubu = 'op'
ok(kat.x_atlas_butce_grubu == 'op' and env[M].search_count([('x_atlas_butce_grubu', '=', 'op')]) == 1, "değer yazılıp aranabiliyor")
deg = env['atlas.studio.degisiklik'].search([('alan_id.name', '=', 'x_atlas_butce_grubu')])
ok(len(deg) == 1 and len(deg.view_ids) == 2, "özelleştirme kaydı: 1 alan, 2 miras görünüm (form + liste)")
w2 = A.create({'model_id': mid, 'etiket': 'İlgili Cari', 'tur': 'many2one', 'iliski_model_id': env['ir.model']._get_id('res.partner'), 'listeye_ekle': False})
w2.action_ekle()
form = etree.fromstring(env[M].get_view(w2.form_view_id.id, 'form')['arch'])
ok(env[M]._fields['x_atlas_ilgili_cari'].comodel_name == 'res.partner' and form.xpath("//sheet/group[@name='x_atlas_ilgili_cari_grup']/field[@name='x_atlas_ilgili_cari']"),
   "konum seçilmeyince formun sonuna 'Ek Bilgiler' bölümü")
try:
    with env.cr.savepoint(): A.create({'model_id': mid, 'etiket': 'Bütçe Grubu', 'tur': 'char'}).action_ekle(); cift = True
except ValidationError: cift = False
ok(not cift, "aynı teknik ad ikinci kez eklenemez")
try:
    with env.cr.savepoint(): A.create({'model_id': mid, 'etiket': 'Tutar', 'tur': 'monetary'}).action_ekle(); para = True
except ValidationError: para = False
ok(not para, "para birimi olmayan modele para alanı eklenemez")
try:
    with env.cr.savepoint(): A.create({'model_id': mid, 'etiket': 'Deneme', 'tur': 'char', 'hedef_alan_id': env['ir.model.fields']._get(M, 'bekleyen_sayisi').id}).action_ekle(); yer = True
except UserError: yer = False
ok(not yer, "formda olmayan alanın yanına eklenemez")
deg.action_geri_al()
ok('x_atlas_butce_grubu' not in env[M]._fields and not env['ir.ui.view'].search_count([('name', 'like', 'x_atlas_butce_grubu')]), "geri al: alan ve görünümler silindi")

# Yeni model
Mw = env['atlas.studio.model'].create({
    'ad': 'Araç Bakım Kaydı', 'cogul_ad': 'Bakım Kayıtları', 'uygulama_adi': 'Filo Bakım',
    'alan_ids': [Command.create({'etiket': 'Plaka', 'tur': 'char', 'zorunlu': True, 'sira': 1}),
                 Command.create({'etiket': 'Bakım Tarihi', 'tur': 'date', 'sira': 2}),
                 Command.create({'etiket': 'Bakım Türü', 'tur': 'selection', 'secenekler': 'Periyodik\nArıza', 'sira': 3}),
                 Command.create({'etiket': 'Servis', 'tur': 'many2one', 'iliski_model_id': env['ir.model']._get_id('res.partner'), 'sira': 4}),
                 Command.create({'etiket': 'Yapılan İşlemler', 'tur': 'html', 'sira': 5}),
                 Command.create({'etiket': 'Etiketler', 'tur': 'many2many', 'iliski_model_id': env['ir.model']._get_id('res.partner.category'), 'sira': 6})]})
ok(Mw.teknik == 'x_atlas_arac_bakim_kaydi', "model teknik adı")
wp = A.create({'model_id': env['ir.model']._get_id('atlas.destek.talep'), 'etiket': 'Cihaz Seri No', 'tur': 'char', 'aramaya_ekle': True})
wp.action_ekle()
arama = etree.fromstring(env['atlas.destek.talep'].get_view(env['ir.model']._atlas_studio_view('atlas.destek.talep', 'search').id, 'search')['arch'])
ok(arama.xpath("//field[@name='x_atlas_cihaz_seri_no']"), "arama görünümüne eklendi")
Mw.action_olustur()
X = 'x_atlas_arac_bakim_kaydi'
ok(X in env and {'x_name', 'x_active', 'x_user_id', 'x_atlas_plaka', 'x_atlas_bakim_turu', 'x_atlas_etiketler'} <= set(env[X]._fields), "model ve alanlar oluştu")
ok('message_ids' in env[X]._fields and 'activity_ids' in env[X]._fields, "mesajlaşma ve aktiviteler etkin")
deg = env['atlas.studio.degisiklik'].search([('model_id.model', '=', X)])
ok(len(deg.view_ids) == 3 and deg.action_id and len(deg.menu_ids) == 2 and deg.access_ids, "form/liste/arama, eylem, uygulama menüsü, erişim")
form = etree.fromstring(env[X].get_view(False, 'form')['arch'])
ok(form.xpath("//chatter") and form.xpath("//notebook/page/field[@name='x_atlas_yapilan_islemler']") and form.xpath("//field[@name='x_atlas_etiketler'][@widget='many2many_tags']"),
   "form: chatter, html sayfası, etiket widget'ı")
u = env['res.users'].with_context(no_reset_password=True).create({'name': 'STD Kullanıcı', 'login': 'std_k', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
kayit = env[X].with_user(u).create({'x_name': 'Yağ değişimi', 'x_atlas_plaka': '34 ABC 123', 'x_atlas_bakim_turu': 'periyodik', 'x_user_id': u.id})
ok(kayit.x_active and kayit.with_user(u).search_count([]) == 1, "iç kullanıcı kayıt oluşturup görebiliyor, varsayılan etkin")
kayit.message_post(body='Servise bırakıldı')
kayit.x_active = False
ok(not env[X].search_count([]) and env[X].with_context(active_test=False).search_count([]) == 1, "arşivleme x_active ile çalışıyor")
kok = deg.menu_ids.filtered(lambda m: not m.parent_id)
ok(kok.name == 'Filo Bakım' and kok in env['ir.ui.menu'].with_user(u).search([('id', '=', kok.id)]), "uygulama menüsü kullanıcıya görünür")
try:
    with env.cr.savepoint(): env['atlas.studio.model'].create({'ad': 'Araç Bakım Kaydı'}).action_olustur(); iki = True
except ValidationError: iki = False
ok(not iki, "aynı model ikinci kez oluşturulamaz")
deg.action_geri_al()
ok(X not in env['ir.model'].search([]).mapped('model') and not env['ir.ui.menu'].search_count([('name', '=', 'Filo Bakım')]), "geri al: model, menü ve görünümler silindi")
env.cr.rollback(); print("(geri alındı)")
