import io
import zipfile

from lxml import etree
from odoo.exceptions import UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
S = env['atlas.studio']

# ---------------------------------------------------------------- yeni uygulama (özellik paketleri)
sonuc = S.uygulama_olustur('Filo Bakım', False, 'Bakım Kaydı', ['use_partner', 'use_responsible', 'use_date', 'use_double_dates', 'use_stages',
                                                                  'use_tags', 'use_image', 'lines', 'use_notes', 'use_value', 'use_sequence',
                                                                  'use_mail', 'use_active'])
X = sonuc['model']
M = env[X]
ok(X == 'x_bakim_kaydi' and all(a in env[X]._fields for a in ('x_studio_partner_id', 'x_studio_user_id', 'x_studio_date', 'x_studio_date_start',
   'x_studio_stage_id', 'x_studio_tag_ids', 'x_studio_image', 'x_studio_line_ids', 'x_studio_notes', 'x_studio_value', 'x_active', 'message_ids')),
   "yeni uygulama: 13 özellik paketinin alanları oluştu")
eylem = env['ir.actions.act_window'].browse(sonuc['action_id'])
ok(eylem.view_mode.split(',')[0] == 'kanban' and 'calendar' in eylem.view_mode and 'atlas_gantt' in eylem.view_mode,
   "eylem: kanban pipeline + takvim + gantt görünümleri")
kok = env['ir.ui.menu'].browse(sonuc['kok_menu_id'])
ok(kok.action and kok.child_id, "kök menü ve model menüsü")
ok(env[f'{X}_stage'].search_count([]) == 3 and env[X].create({'x_name': 'İlk'}).x_studio_stage_id.x_name == 'Yeni', "aşamalar ve varsayılan aşama")
b = S.baglam(eylem.id)
ok(b['model'] == X and b['menu']['kok_id'] == kok.id and any(g['tur'] == 'kanban' and g['varsayilan'] for g in b['gorunum_turleri']),
   "bağlam: model, menü yolu, varsayılan görünüm")
ok(any(u['id'] == kok.id and u['eylem_id'] == eylem.id for u in S.uygulamalar()), "uygulamalar listesi menüye bağlı eylemi verir")

# ---------------------------------------------------------------- form düzenleme
d = S.gorunum_getir(X, 'form', eylem.id)
vid = d['view_id']
kok_el = etree.fromstring(d['arch'])
sag = kok_el.xpath("//group[@name='studio_group_sag']")[0]
yol = S._yol(kok_el, sag)
yeni = S.alan_olustur(X, {'tur': 'selection', 'etiket': 'Bakım Türü', 'secenekler': [['periyodik', 'Periyodik'], ['ariza', 'Arıza']]})
ok(yeni['ad'] == 'x_studio_bakim_turu' and env[X]._fields['x_studio_bakim_turu'].type == 'selection', "alan oluştur: seçim")
d = S.islem_uygula(vid, {'islem': 'ekle', 'hedef_yol': yol, 'konum': 'inside', 'dugum': {'tag': 'field', 'attrs': {'name': yeni['ad']}}})
arch = etree.fromstring(env[X].get_view(vid, 'form')['arch'])
ok(arch.xpath("//group[@name='studio_group_sag']/field[@name='x_studio_bakim_turu']"), "sürükle-bırak: alan gruba eklendi")
studio = S._studio_gorunumu(env['ir.ui.view'].browse(vid), olustur=False)
ok(studio and studio.priority == 990 and studio.mode == 'extension', "tek Studio miras görünümü")

kok_el = etree.fromstring(d['arch'])
alan_el = kok_el.xpath("//field[@name='x_studio_bakim_turu']")[0]
d = S.islem_uygula(vid, {'islem': 'nitelik', 'hedef_yol': S._yol(kok_el, alan_el),
                         'nitelikler': {'string': 'Tür', 'required': 'True', 'invisible': "x_studio_stage_id == False", 'groups': ['%d' % env.ref('base.group_user').id]}})
arch = etree.fromstring(env[X].get_view(vid, 'form')['arch'])
f = arch.xpath("//field[@name='x_studio_bakim_turu']")[0]
ok(f.get('string') == 'Tür' and f.get('required') == 'True' and 'x_studio_stage_id' in f.get('invisible', ''), "özellikler: etiket, zorunlu, koşullu görünmez")
ok('base.group_user' in etree.fromstring(studio.arch).xpath("//attribute[@name='groups']")[0].text, "erişim grubu XML kimliğiyle yazıldı")

kok_el = etree.fromstring(d['arch'])
kaynak = kok_el.xpath("//field[@name='x_studio_bakim_turu']")[0]
hedef = kok_el.xpath("//field[@name='x_studio_partner_id']")[0]
d = S.islem_uygula(vid, {'islem': 'tasi', 'kaynak_yol': S._yol(kok_el, kaynak), 'hedef_yol': S._yol(kok_el, hedef), 'konum': 'before'})
arch = etree.fromstring(env[X].get_view(vid, 'form')['arch'])
ok(arch.xpath("//group[@name='studio_group_sol']/field[1]")[0].get('name') == 'x_studio_bakim_turu', "taşı: alan diğer sütunun başına taşındı")

d = S.geri_al(vid)
arch = etree.fromstring(env[X].get_view(vid, 'form')['arch'])
ok(arch.xpath("//group[@name='studio_group_sag']/field[@name='x_studio_bakim_turu']") and d['ileri'], "geri al: taşıma geri alındı")
d = S.yinele(vid)
arch = etree.fromstring(env[X].get_view(vid, 'form')['arch'])
ok(arch.xpath("//group[@name='studio_group_sol']/field[@name='x_studio_bakim_turu']") and not d['ileri'], "yinele")

kok_el = etree.fromstring(d['arch'])
try:
    S.islem_uygula(vid, {'islem': 'ekle', 'hedef_yol': S._yol(kok_el, kok_el.xpath('//sheet')[0]), 'konum': 'inside',
                         'dugum': {'tag': 'field', 'attrs': {'name': 'yok_boyle_alan'}}})
    gecersiz = True
except UserError:
    gecersiz = False
ok(not gecersiz and not S._durum(env['ir.ui.view'].browse(vid))['ileri'], "geçersiz değişiklik reddedilir, hiçbir şey kaydedilmez")

kok_el = etree.fromstring(S.gorunum_getir(X, 'form', eylem.id)['arch'])
not_defteri = kok_el.xpath('//notebook')[0]
d = S.islem_uygula(vid, {'islem': 'ekle', 'hedef_yol': S._yol(kok_el, not_defteri), 'konum': 'inside',
                         'dugum': {'tag': 'page', 'attrs': {'string': 'Ek', 'name': 'studio_sayfa_1'}}})
ok(etree.fromstring(env[X].get_view(vid, 'form')['arch']).xpath("//notebook/page[@name='studio_sayfa_1']"), "bileşen: yeni sekme")

# alan türleri
etiket = S.alan_olustur(X, {'tur': 'tags', 'etiket': 'Kategoriler'})
satir = S.alan_olustur(X, {'tur': 'lines', 'etiket': 'Parçalar'})
para = S.alan_olustur(X, {'tur': 'monetary', 'etiket': 'Maliyet'})
iliskili = S.alan_olustur(X, {'tur': 'related', 'etiket': 'Kontak Şehri', 'yol': 'x_studio_partner_id.city'})
dosya = S.alan_olustur(X, {'tur': 'binary', 'etiket': 'Rapor Dosyası'})
imza = S.alan_olustur(X, {'tur': 'signature', 'etiket': 'İmza'})
oncelik = S.alan_olustur(X, {'tur': 'priority', 'etiket': 'Öncelik'})
M = env[X]
ok(env[X]._fields[etiket['ad']].type == 'many2many' and etiket['nitelikler'].get('widget') == 'many2many_tags', "alan: etiketler (etiket modeli + renk)")
ok(env[X]._fields[satir['ad']].type == 'one2many', "alan: satırlar (satır modeli + ters alan)")
ok(env[X]._fields[para['ad']].currency_field == 'x_studio_currency_id', "alan: parasal değer mevcut para birimine bağlandı")
ok(env[X]._fields[iliskili['ad']].related == 'x_studio_partner_id.city', "alan: ilişkili alan")
ok(dosya['nitelikler'].get('filename') in env[X]._fields and imza['nitelikler'].get('widget') == 'signature' and oncelik['nitelikler'].get('widget') == 'priority',
   "alan: dosya (dosya adı alanı), imza, öncelik bileşenleri")
S.alan_ozellik(X, yeni['ad'], {'takip': True, 'varsayilan': 'ariza'})
ok(env[X].create({'x_name': 'B'}).x_studio_bakim_turu == 'ariza' and S.alan_bilgisi(X, yeni['ad'])['takip'], "alan: varsayılan değer ve değişiklik takibi")

# akıllı düğme
iliski = env['ir.model.fields']._get(f'{X}_line', [n for n in env[f'{X}_line']._fields if n.endswith('_id') and env[f'{X}_line']._fields[n].comodel_name == X][0])
d = S.akilli_dugme_ekle(vid, iliski.id, 'Satırlar', 'list_alt')
arch = etree.fromstring(env[X].get_view(vid, 'form')['arch'])
ok(arch.xpath("//div[@name='button_box']/button[@type='action']/field[@widget='statinfo']"), "akıllı düğme: sayaç + eylem")
kayit = env[X].create({'x_name': 'Sayaçlı', 'x_studio_line_ids': [(0, 0, {'x_name': 'a'}), (0, 0, {'x_name': 'b'})]})
sayac = arch.xpath("//field[@widget='statinfo']")[0].get('name')
ok(kayit[sayac] == 2, "akıllı düğme sayacı doğru")

# ---------------------------------------------------------------- liste / arama
dl = S.gorunum_getir(X, 'list', eylem.id)
kok_el = etree.fromstring(dl['arch'])
S.islem_uygula(dl['view_id'], [{'islem': 'nitelik', 'hedef_yol': [], 'nitelikler': {'editable': 'bottom', 'default_order': 'x_name desc'}},
                               {'islem': 'ekle', 'hedef_yol': [], 'konum': 'inside', 'dugum': {'tag': 'field', 'attrs': {'name': yeni['ad'], 'optional': 'show'}}}])
la = etree.fromstring(env[X].get_view(dl['view_id'], 'list')['arch'])
ok(la.get('editable') == 'bottom' and la.xpath(f"//field[@name='{yeni['ad']}'][@optional='show']"), "liste: satır içi düzenleme, isteğe bağlı sütun")
ds = S.gorunum_getir(X, 'search', eylem.id)
S.islem_uygula(ds['view_id'], {'islem': 'ekle', 'hedef_yol': [], 'konum': 'inside',
                               'dugum': {'tag': 'filter', 'attrs': {'name': 'studio_grupla_tur', 'string': 'Tür', 'context': f"{{'group_by': '{yeni['ad']}'}}"}}})
ok(etree.fromstring(env[X].get_view(ds['view_id'], 'search')['arch']).xpath("//filter[@name='studio_grupla_tur']"), "arama: gruplama eklendi")

# ---------------------------------------------------------------- görünüm türleri
for tur in ('pivot', 'graph', 'activity', 'atlas_kohort'):
    S.gorunum_turu_ayarla(eylem.id, tur, 'etkinlestir')
eylem.invalidate_recordset()
ok(all(t in eylem.view_mode for t in ('pivot', 'graph', 'activity', 'atlas_kohort')), "görünüm türleri etkinleştirildi (pivot, grafik, aktivite, kohort)")
for tur in ('pivot', 'graph', 'activity', 'atlas_kohort'):
    env[X].get_views([(False, tur)])
ok(True, "etkinleştirilen görünümler yüklenebiliyor")
S.gorunum_turu_ayarla(eylem.id, 'list', 'varsayilan')
S.gorunum_turu_ayarla(eylem.id, 'graph', 'devre_disi')
eylem.invalidate_recordset()
ok(eylem.view_mode.startswith('list') and 'graph' not in eylem.view_mode, "varsayılan yap / devre dışı bırak")
try:
    tek = env['ir.actions.act_window'].create({'name': 't', 'res_model': X, 'view_mode': 'list'})
    S.gorunum_turu_ayarla(tek.id, 'list', 'devre_disi'); son = True
except UserError:
    son = False
ok(not son, "son görünüm devre dışı bırakılamaz")

# kanban kartı (görsel kanban editörünün kullandığı işlemler; arayüz her seferinde tek işlem gönderir)
dk = S.gorunum_getir(X, 'kanban', eylem.id)


def kart_ve_kok():
    kk = etree.fromstring(S.gorunum_getir(X, 'kanban', eylem.id)['arch'])
    return kk, kk.xpath("//t[@t-name='card']")[0]


kk, kart = kart_ve_kok()
S.islem_uygula(dk['view_id'], {'islem': 'ekle', 'hedef_yol': S._yol(kk, kart.xpath('footer')[0]), 'konum': 'inside',
                               'dugum': {'tag': 'field', 'attrs': {'name': 'x_studio_value', 'class': 'ms-auto'}}})
S.islem_uygula(dk['view_id'], {'islem': 'nitelik', 'hedef_yol': [], 'nitelikler': {'default_group_by': 'x_studio_stage_id', 'highlight_color': 'x_studio_sequence'}})
kk, kart = kart_ve_kok()
S.islem_uygula(dk['view_id'], {'islem': 'ekle', 'hedef_yol': S._yol(kk, kart[0]), 'konum': 'before',
                               'dugum': {'tag': 'widget', 'attrs': {'name': 'web_ribbon', 'title': 'Arşiv', 'invisible': 'x_active'}}})
kk, kart = kart_ve_kok()
S.islem_uygula(dk['view_id'], {'islem': 'nitelik', 'hedef_yol': S._yol(kk, kart.xpath("field[@name='x_name']")[0]), 'nitelikler': {'class': 'fw-bold fs-5'}})
ka = etree.fromstring(env[X].get_view(dk['view_id'], 'kanban')['arch'])
ok(ka.get('default_group_by') == 'x_studio_stage_id' and ka.get('highlight_color') == 'x_studio_sequence'
   and ka.xpath("//t[@t-name='card']/footer/field[@name='x_studio_value']")
   and ka.xpath("//t[@t-name='card']/*[1][@name='web_ribbon']") and ka.xpath("//t[@t-name='card']/field[@name='x_name'][@class='fw-bold fs-5']"),
   "kanban kartı: alt bilgiye alan, şerit, alan biçimi, gruplama ve renk alanı")
env[X].get_views([(dk['view_id'], 'kanban')])
S.sifirla(dk['view_id'])

# XML düzenleyici / sıfırla
dk = S.gorunum_getir(X, 'kanban', eylem.id)
S.xml_kaydet(dk['view_id'], "<data><xpath expr=\"//field[@name='x_name']\" position=\"after\"><field name=\"x_studio_date\"/></xpath></data>")
ok(etree.fromstring(env[X].get_view(dk['view_id'], 'kanban')['arch']).xpath("//field[@name='x_studio_date']"), "XML düzenleyici: kanban özelleştirildi")
try:
    S.xml_kaydet(dk['view_id'], "<data><xpath expr=\"//yok\" position=\"after\"><field name=\"x_name\"/></xpath></data>"); kotu = True
except UserError:
    kotu = False
ok(not kotu and etree.fromstring(env[X].get_view(dk['view_id'], 'kanban')['arch']).xpath("//field[@name='x_studio_date']"), "hatalı XML reddedilir, önceki hal korunur")
S.sifirla(dk['view_id'])
ok(not etree.fromstring(env[X].get_view(dk['view_id'], 'kanban')['arch']).xpath("//templates//field[@name='x_studio_date']"), "görünümü sıfırla")

# mevcut (standart) modelde düzenleme
dp = S.gorunum_getir('res.partner', 'form')
pk = etree.fromstring(dp['arch'])
hedef = pk.xpath("//field[@name='vat']")[0]
S.islem_uygula(dp['view_id'], {'islem': 'nitelik', 'hedef_yol': S._yol(pk, hedef), 'nitelikler': {'string': 'VKN / TCKN'}})
ok(etree.fromstring(env['res.partner'].get_view(dp['view_id'], 'form')['arch']).xpath("//field[@name='vat'][@string='VKN / TCKN']"), "standart model formunda etiket değişti")

# ---------------------------------------------------------------- menü
agac = S.menu_agaci(kok.id)
S.menu_olustur(kok.id, 'Ayarlar', 'ust')
S.menu_olustur(kok.id, 'Kontaklar', 'mevcut_model', 'res.partner')
agac = S.menu_agaci(kok.id)
adlar = [c['ad'] for c in agac['cocuklar']]
ust = next(c for c in agac['cocuklar'] if c['ad'] == 'Ayarlar')
kontak = next(c for c in agac['cocuklar'] if c['ad'] == 'Kontaklar')
yeni_agac = [{'id': ust['id'], 'ad': 'Yapılandırma', 'cocuklar': [{'id': kontak['id'], 'ad': 'Kontaklar', 'cocuklar': []}]}] + \
            [{'id': c['id'], 'ad': c['ad'], 'cocuklar': []} for c in agac['cocuklar'] if c['id'] not in (ust['id'], kontak['id'])]
agac = S.menu_kaydet(kok.id, yeni_agac)
ok(agac['cocuklar'][0]['ad'] == 'Yapılandırma' and agac['cocuklar'][0]['cocuklar'][0]['ad'] == 'Kontaklar', "menü düzenle: yeniden adlandır, sırala, alt menüye taşı")
yeni_model = S.menu_olustur(kok.id, 'Araçlar', 'yeni_model', False, ['use_mail'])
ok('x_araclar' in env and env['ir.ui.menu'].browse(yeni_model['id']).action, "menüden yeni model")

# ---------------------------------------------------------------- rapor
r = S.rapor_olustur(X, 'Bakım Formu', 'dis')
rapor = env['ir.actions.report'].browse(r['id'])
ok(rapor.binding_model_id.model == X and rapor.report_name.startswith('atlas_studio_ozel.'), "rapor: yazdır menüsünde, Studio anahtarıyla")
html = S.rapor_onizle(r['id'])
ok('Sayaçlı' in html or 'İlk' in html or 'B' in html, "rapor önizleme HTML")
g = S.rapor_getir(r['id'])
yeni_arch = g['arch'].replace('<div class="page">', '<div class="page"><p class="studio_test">Teknik Servis</p>')
S.rapor_kaydet(r['id'], yeni_arch, 'Bakım Fişi', False, "'Bakım - %s' % object.x_name")
rapor.invalidate_recordset()
ok(rapor.name == 'Bakım Fişi' and not rapor.binding_model_id and 'Teknik Servis' in S.rapor_onizle(r['id']), "rapor kaydet: şablon, ad, menüden kaldırma")
try:
    S.rapor_kaydet(r['id'], '<t t-name="x"><span t-field="doc.yok_alan"/></t>'); kotu_rapor = True
except UserError:
    kotu_rapor = False
ok(not kotu_rapor and 'Teknik Servis' in S.rapor_onizle(r['id']), "hatalı rapor şablonu reddedilir")

# ---------------------------------------------------------------- onay adımları
grup = env['res.groups'].create({'name': 'Bakım Müdürü'})
mudur = env['res.users'].create({'name': 'Müdür', 'login': 'studio_mudur', 'group_ids': [(6, 0, [env.ref('base.group_user').id, grup.id])]})
calisan = env['res.users'].create({'name': 'Çalışan', 'login': 'studio_calisan', 'group_ids': [(6, 0, [env.ref('base.group_user').id])]})
S.onay_kurallari_kaydet(X, 'metot:action_archive', [{'grup_id': grup.id, 'aciklama': 'Müdür onayı'}])
ok(len(S.onay_kurallari(X, 'metot:action_archive')) == 1, "onay kuralı kaydedildi")
is_kaydi = env[X].create({'x_name': 'Onaylı İş'})
baglam = {'atlas_studio_onay': f'{X}:metot:action_archive'}
try:
    is_kaydi.with_user(calisan).with_context(**baglam).atlas_studio_onayli_calistir(); gecti = True
except UserError:
    gecti = False
talep = env['atlas.studio.onay.talep'].search([('res_id', '=', is_kaydi.id)])
ok(not gecti and talep.durum == 'bekliyor' and is_kaydi.x_active, "onaysız kullanıcı: işlem durdu, onay talebi açıldı")
ok(is_kaydi.activity_ids.filtered(lambda a: a.user_id == mudur), "onaylayıcıya aktivite")
try:
    talep.with_user(calisan).action_onayla(); yetkisiz = True
except UserError:
    yetkisiz = False
ok(not yetkisiz, "yetkisiz kullanıcı onaylayamaz")
talep.with_user(mudur).action_onayla()
is_kaydi.with_user(calisan).with_context(**baglam).atlas_studio_onayli_calistir()
ok(not is_kaydi.x_active, "onaydan sonra hedef metot çalıştı")
is2 = env[X].create({'x_name': 'Müdür İşi'})
is2.with_user(mudur).with_context(**baglam).atlas_studio_onayli_calistir()
ok(not is2.x_active, "onaylayıcının tıklaması onay sayılır")

# ---------------------------------------------------------------- dışa aktar
icerik = S.disa_aktar()
z = zipfile.ZipFile(io.BytesIO(icerik))
veri = z.read('atlas_studio_ozel/data/ozellestirmeler.xml')
xml = etree.fromstring(veri)
modeller = {r.get('model') for r in xml.iter('record')}
ok({'ir.model', 'ir.model.fields', 'ir.ui.view', 'ir.actions.act_window', 'ir.ui.menu', 'ir.access', 'ir.actions.report', 'atlas.studio.onay.kural'} <= modeller,
   "dışa aktar: model, alan, görünüm, eylem, menü, erişim, rapor, onay kuralı")
manifest = z.read('atlas_studio_ozel/__manifest__.py').decode()
ok("'base'" in manifest and 'ozellestirmeler.xml' in manifest, "dışa aktar: manifest")
dugme = [r for r in xml.iter('record') if r.get('model') == 'ir.ui.view' and b'statinfo' in etree.tostring(r)]
ok(dugme and '%(' in etree.tostring(dugme[0], encoding='unicode'), "akıllı düğme eylemi XML kimliğiyle (%(xmlid)d) dışa aktarıldı")

# ---------------------------------------------------------------- yetki
try:
    S.with_user(calisan).baglam(eylem.id); acik = True
except Exception:
    acik = False
ok(not acik, "Studio yalnız sistem yöneticisine açık")

env.cr.rollback(); print("(geri alındı)")
