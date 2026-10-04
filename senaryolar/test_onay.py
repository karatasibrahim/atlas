from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
grp = [Command.set([env.ref('base.group_user').id, env.ref('purchase.group_purchase_user').id])]
U = env['res.users'].with_context(no_reset_password=True)
talep_eden, yonetici, a1, a2, yabanci = (U.create({'name': f'ONY {ad}', 'login': f'ony_{ad}', 'email': f'{ad}@ornek.com', 'group_ids': grp})
                                         for ad in ('talep', 'yonetici', 'a1', 'a2', 'yabanci'))
e_yon = env['hr.employee'].create({'name': 'ONY Yönetici', 'user_id': yonetici.id})
env['hr.employee'].create({'name': 'ONY Talep', 'user_id': talep_eden.id, 'parent_id': e_yon.id})
K = env['atlas.onay.kategori']; T = env['atlas.onay.talep']
kat = K.create({'name': 'ONY Avans', 'yonetici_onayi': 'zorunlu', 'min_onay': 2, 'alan_tutar': 'zorunlu',
                'onaylayici_ids': [Command.create({'user_id': a1.id, 'zorunlu': True, 'sira': 1}), Command.create({'user_id': a2.id, 'sira': 2})]})
ok(talep_eden.has_group('atlas_onay.group_onay_user'), "iç kullanıcılar onay kullanıcısı")
t = T.with_user(talep_eden).create({'konu': 'Fuar avansı', 'kategori_id': kat.id})
try:
    with env.cr.savepoint(): t.action_gonder(); gitti = True
except UserError: gitti = False
ok(not gitti and t.durum == 'taslak', "zorunlu tutar alanı boşken gönderilemez")
t.tutar = 15000
t.with_user(talep_eden).action_gonder()
ok(t.durum == 'beklemede' and set(t.onay_ids.user_id.ids) == {yonetici.id, a1.id, a2.id}, "gönderildi: yönetici + 2 onaylayıcı")
ok(t.onay_ids.filtered(lambda s: s.user_id == yonetici).zorunlu and all(s.durum == 'bekliyor' for s in t.onay_ids), "yönetici zorunlu, paralel: hepsi bekliyor")
tur = env.ref('atlas_onay.mail_activity_onay')
ok(set(t.activity_ids.filtered(lambda a: a.activity_type_id == tur).user_id.ids) == {yonetici.id, a1.id, a2.id}, "her onaylayıcıya aktivite")
ok(t.with_user(a1).benim_durumum == 'bekliyor' and t in T.with_user(a1).search([]), "onaylayıcı talebi görüyor, onayı bekleniyor")
ok(t not in T.with_user(yabanci).search([]), "ilgisiz kullanıcı talebi görmez")
try:
    with env.cr.savepoint(): t.with_user(yabanci).action_onayla(); yetkisiz = True
except AccessError: yetkisiz = False
ok(not yetkisiz, "onaylayıcı olmayan onaylayamaz")
t.with_user(a2).action_onayla()
t.with_user(yonetici).action_onayla(aciklama='Uygun')
ok(t.durum == 'beklemede' and t.onaylayan_sayisi == 2, "2 onay var ama zorunlu a1 eksik: beklemede")
ok(a2 not in t.activity_ids.user_id and a1 in t.activity_ids.user_id, "onaylayanın aktivitesi kapandı")
t.with_user(a1).action_onayla()
ok(t.durum == 'onaylandi' and t.onay_tarihi and not t.activity_ids.filtered(lambda a: a.activity_type_id == tur), "zorunlular tamam: onaylandı")
ok(any('onaylandı' in (m.body or '') and talep_eden.partner_id in m.partner_ids for m in t.message_ids), "talep edene bildirim")

# Sıralı + red
kat2 = K.create({'name': 'ONY Sıralı', 'sirali': True, 'min_onay': 2,
                 'onaylayici_ids': [Command.create({'user_id': a1.id, 'sira': 1}), Command.create({'user_id': a2.id, 'sira': 2})]})
t2 = T.with_user(talep_eden).create({'konu': 'Yazılım lisansı', 'kategori_id': kat2.id})
t2.action_gonder()
s1, s2 = t2.onay_ids.sorted('sira')
ok(s1.durum == 'bekliyor' and s2.durum == 'yeni' and t2.with_user(a2).benim_durumum == 'yeni', "sıralı: yalnızca ilk onaylayıcı aktif")
t2.with_user(a1).action_onayla()
ok(s2.durum == 'bekliyor' and t2.durum == 'beklemede' and a2 in t2.activity_ids.user_id, "ilk onaydan sonra sıradaki aktif")
w = env['atlas.onay.red'].with_user(a2).create({'talep_id': t2.id, 'neden': 'Bütçe yok'})
w.action_reddet()
ok(t2.durum == 'reddedildi' and s2.durum == 'reddetti' and s2.aciklama == 'Bütçe yok', "red nedeniyle reddedildi")
t2.with_user(talep_eden).action_geri_cek()
ok(t2.durum == 'taslak' and not t2.onay_ids, "talep eden taslağa geri çekti")
try:
    with env.cr.savepoint(): K.create({'name': 'x', 'min_onay': 3, 'onaylayici_ids': [Command.create({'user_id': a1.id})]}); gecti = True
except Exception: gecti = False
ok(not gecti, "gereken onay onaylayıcı sayısını aşamaz")

# Belge eki zorunlu
bk = env.ref('atlas_onay.kategori_belge'); bk.onaylayici_ids = [Command.create({'user_id': a1.id})]
t3 = T.with_user(talep_eden).create({'konu': 'Kira sözleşmesi', 'kategori_id': bk.id})
try:
    with env.cr.savepoint(): t3.action_gonder(); gitti = True
except UserError: gitti = False
ok(not gitti, "belge eki zorunlu: eksikken gönderilemez")
t3.message_post(body='Sözleşme', attachments=[('sozlesme.pdf', b'%PDF-1.4 test')])
t3.action_gonder()
ok(t3.durum == 'beklemede', "ek eklenince gönderildi")

# Kayıt onayı: satın alma
satin = K.create({'name': 'ONY Satın Alma', 'onaylayici_ids': [Command.create({'user_id': a1.id})]})
kural = env['atlas.onay.kural'].create({'name': '1000 üzeri satın alma', 'model': 'purchase.order', 'kategori_id': satin.id,
                                        'domain': "[('amount_total', '>', 1000)]"})
ted = env['res.partner'].create({'name': 'ONY Tedarikçi'})
urun = env['product.product'].create({'name': 'ONY Malzeme', 'purchase_ok': True, 'standard_price': 10})
def po(fiyat):
    return env['purchase.order'].with_user(talep_eden).create({'partner_id': ted.id, 'order_line': [Command.create({'product_id': urun.id, 'product_qty': 1, 'price_unit': fiyat, 'tax_ids': False})]})
kucuk = po(500); buyuk = po(2000)
ok(kucuk.atlas_onay_durumu == 'gerekmez' and buyuk.atlas_onay_durumu == 'gerekli', "kural yalnızca 1000 üzerine uygulanıyor")
kucuk.button_confirm()
ok(kucuk.state == 'purchase', "küçük sipariş onaysız onaylandı")
try:
    with env.cr.savepoint(): buyuk.with_user(talep_eden).button_confirm(); onaylandi = True
except UserError: onaylandi = False
ok(not onaylandi, "büyük sipariş onaysız onaylanamaz")
buyuk.with_user(talep_eden).action_atlas_onaya_gonder()
kt = T.search([('res_model', '=', 'purchase.order'), ('res_id', '=', buyuk.id)])
ok(len(kt) == 1 and kt.durum == 'beklemede' and kt.tutar == 2000 and kt.kural_id == kural and buyuk.atlas_onay_durumu == 'beklemede',
   "onaya gönderildi: talep oluştu")
buyuk.with_user(talep_eden).action_atlas_onaya_gonder()
ok(T.search_count([('res_model', '=', 'purchase.order'), ('res_id', '=', buyuk.id)]) == 1, "bekleyen varken ikinci talep açılmaz")
kt.with_user(a1).action_onayla()
buyuk.invalidate_recordset()
ok(kt.durum == 'onaylandi' and buyuk.atlas_onay_durumu == 'onaylandi' and buyuk.atlas_onay_talep_sayisi == 1, "onaylandı")
buyuk.order_line.price_unit = 2500
buyuk.invalidate_recordset()
ok(buyuk.atlas_onay_durumu == 'gerekli', "onaydan sonra tutar artınca yeniden onay gerekli")
buyuk.order_line.price_unit = 1800
buyuk.with_user(talep_eden).button_confirm()
ok(buyuk.state == 'purchase', "onaylanan tutarın altında: sipariş onaylandı")

# Fatura kuralı
fk = env['atlas.onay.kural'].create({'name': 'Tedarikçi faturası', 'model': 'account.move', 'kategori_id': satin.id,
                                     'domain': "[('move_type', '=', 'in_invoice')]"})
from datetime import date
ft = env['account.move'].create({'move_type': 'in_invoice', 'partner_id': ted.id, 'invoice_date': date.today(),
                                 'invoice_line_ids': [Command.create({'name': 'K', 'quantity': 1, 'price_unit': 10, 'tax_ids': False})]})
try:
    with env.cr.savepoint(): ft.action_post(); islendi = True
except UserError: islendi = False
ok(not islendi and ft.atlas_onay_durumu == 'gerekli', "tedarikçi faturası onaysız işlenemez")
try:
    with env.cr.savepoint(): env['atlas.onay.kural'].create({'name': 'bozuk', 'model': 'sale.order', 'kategori_id': satin.id, 'domain': "[('yok_alan', '=', 1)]"}); gecti = True
except Exception: gecti = False
ok(not gecti, "geçersiz koşul reddedildi")
ok(kat.with_user(a1).bekleyen_sayisi == 0 and bk.with_user(a1).bekleyen_sayisi == 1, "kategori panelinde onayımı bekleyen sayısı")
env.cr.rollback(); print("(geri alındı)")
