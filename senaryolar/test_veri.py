from odoo.addons.atlas_veri.models import metin
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
P = env['res.partner']
Grup = env['atlas.veri.grup']

# --- Türkçe metin yardımcıları
ok(metin.tr_buyuk('istanbul ılgaz') == 'İSTANBUL ILGAZ' and metin.tr_kucuk('İSTANBUL IRMAK') == 'istanbul ırmak'
   and metin.tr_baslik('KADIKÖY VE ÜSKÜDAR') == 'Kadıköy ve Üsküdar', "Türkçe büyük/küçük harf (İ/ı) ve başlık biçimi")
ok(metin.normal('  MAVİ  Tekstil A.Ş. ') == metin.normal('mavi tekstil a.s.') == metin.normal('Mavi Tekstil A.Ş.'),
   "eşleştirme anahtarı: harf, aksan, boşluk duyarsız")

# --- Mükerrer bulma (kontak): ad aksan duyarsız, VKN birebir
a = P.create({'name': 'VT Mavi Tekstil A.Ş.', 'email': 'info@vtmavi.com'})
b = P.create({'name': 'vt MAVİ  tekstil a.s.'})
c = P.create({'name': 'VT Başka Firma', 'vat': '1234567890'})
d = P.create({'name': 'VT Başka Firma Ltd', 'vat': '1234567890'})
e = P.create({'name': 'VT Tek Kayıt'})
m = env.ref('atlas_veri.vmodel_cari')
m.action_tara()
gruplar = Grup.search([('vmodel_id', '=', m.id)])
idler = [set(g.kayit_ids.mapped('res_id')) for g in gruplar]
ok({a.id, b.id} in idler and {c.id, d.id} in idler and not any(e.id in s for s in idler),
   "aynı ad (yazım farklı) ve aynı VKN grupları bulundu; tekil kayıt gruplanmadı")
g_ab = gruplar.filtered(lambda g: set(g.kayit_ids.mapped('res_id')) == {a.id, b.id})
ok(g_ab.benzerlik >= 90 and 'E-posta' in (g_ab.farkli_alanlar or '') or g_ab.farkli_alanlar, f"benzerlik %{g_ab.benzerlik}, farklı alanlar: {g_ab.farkli_alanlar}")
m.action_tara()
ok(len(Grup.search([('vmodel_id', '=', m.id)])) == len(gruplar), "tekrar taramada aynı gruplar yeniden açılmaz")

# --- Yoksay
g_cd = gruplar.filtered(lambda g: set(g.kayit_ids.mapped('res_id')) == {c.id, d.id})
g_cd.action_yoksay()
g_cd.unlink()
m.action_tara()
ok(not Grup.search([('vmodel_id', '=', m.id)]).filtered(lambda g: set(g.kayit_ids.mapped('res_id')) == {c.id, d.id}),
   "'mükerrer değil' denen grup tekrar önerilmez")

# --- Birleştirme (cari): bağlı kayıtlar ana kayda taşınır
siparis = env['sale.order'].create({'partner_id': b.id})
g_ab.kayit_ids.filtered(lambda k: k.res_id == a.id).ana = True
g_ab.action_birlestir()
ok(siparis.partner_id == a and not b.exists().active and not g_ab.active, "cari birleştirme: sipariş ana kayda taşındı, kopya arşivlendi")

# --- Birleştirme (genel model: ürün) — bağlantılar ve boş alan doldurma
U = env['product.template']
u1 = U.create({'name': 'VT Kablo 3x2,5', 'default_code': 'VT-KBL-25'})
u2 = U.create({'name': 'vt kablo 3x2,5', 'description_sale': 'NYY kablo'})
satir = env['sale.order'].create({'partner_id': a.id, 'order_line': [(0, 0, {'product_id': u2.product_variant_id.id, 'product_uom_qty': 3})]})
mu = env.ref('atlas_veri.vmodel_urun')
mu.action_tara()
gu = Grup.search([('vmodel_id', '=', mu.id)]).filtered(lambda g: set(g.kayit_ids.mapped('res_id')) == {u1.id, u2.id})
ok(gu, "ürün mükerrer grubu (ad)")
gu.kayit_ids.filtered(lambda k: k.res_id == u1.id).ana = True
ok(gu.kayit_ids.filtered(lambda k: k.res_id == u2.id).kullanim >= 1, "kullanım sayısı (bağlı kayıt) hesaplandı")
gu.action_birlestir()
ok((not u2.exists() or not u2.active) and u1.description_sale == 'NYY kablo' and satir.order_line.product_id == u1.product_variant_id,
   "ürün birleştirme: sipariş satırı ana varyanta taşındı, kopya kaldırıldı, boş alan dolduruldu")

# --- Listeden "Birleştir" eylemi (her model)
etiket1 = env['res.partner.category'].create({'name': 'VT Bayi'})
etiket2 = env['res.partner.category'].create({'name': 'VT BAYİ'})
k1 = P.create({'name': 'VT Etiketli', 'category_id': [(6, 0, etiket2.ids)]})
me = env.ref('atlas_veri.vmodel_etiket')
me.action_eylem_ekle()
ok(me.eylem_id.binding_model_id.model == 'res.partner.category', "'Birleştir' eylemi listeye eklendi")
eylem = env['atlas.veri.birlestir'].eylem_ac('res.partner.category', [etiket1.id, etiket2.id])
w = env['atlas.veri.birlestir'].with_context(**eylem['context']).create({})
ok(w.ana_secim == str(etiket1.id) and len(w._secenekler()) == 2, "birleştirme sihirbazı: ana kayıt seçenekleri")
w.action_birlestir()
ok(k1.category_id == etiket1 and not etiket2.exists().active, "etiket birleştirme: many2many bağlantı ana etikete taşındı")

# --- Biçim temizliği
k = P.create({'name': '  VT   Fazla   Boşluk  ', 'email': ' Info@VT-Ornek.COM ', 'phone': '0532 123 45 67', 'country_id': env.ref('base.tr').id})
t = env.ref('atlas_veri.temizlik_cari')
t.action_tara()
oneriler = env['atlas.veri.temizlik.kayit'].search([('res_id', '=', k.id)])
o = {x.field_id.name: x.onerilen for x in oneriler}
ok(o.get('name') == 'VT Fazla Boşluk' and o.get('email') == 'info@vt-ornek.com' and o.get('phone') == '+90 532 123 45 67',
   f"öneriler: ad boşluk, e-posta boşluk+küçük harf, telefon uluslararası ({o})")
oneriler.action_uygula()
ok(k.name == 'VT Fazla Boşluk' and k.email == 'info@vt-ornek.com' and k.phone == '+90 532 123 45 67', "öneriler uygulandı")
t.mod = 'otomatik'
k2 = P.create({'name': 'VT  Oto  Temizlik'})
t.action_tara()
ok(k2.name == 'VT Oto Temizlik', "otomatik modda doğrudan uygulandı")
env.cr.rollback(); print("(geri alındı)")
