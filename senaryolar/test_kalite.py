from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k)
        return None
    except UserError as e: return str(e)
B = env['atlas.barkod']; P = env['res.partner']; Prod = env['product.product']; N = env['atlas.kalite.nokta']; K = env['atlas.kalite.kontrol']
N.search([]).active = False  # kullanıcının mevcut noktaları testi etkilemesin
cat = lambda x: env.ref(f'atlas_stok.categ_{x}')
ted = P.create({'name': 'Kalite Tedarikçi', 'is_company': True}); ted2 = P.create({'name': 'Diğer Tedarikçi', 'is_company': True})
mus = P.create({'name': 'Kalite Müşteri', 'is_company': True})
vida = Prod.create({'name': 'Vida', 'default_code': 'KV-1', 'is_storable': True, 'categ_id': cat('ilk_madde').id})
klima = Prod.create({'name': 'Klima', 'default_code': 'KK-1', 'is_storable': True, 'categ_id': cat('ticari_mal').id})
kombi = Prod.create({'name': 'Kombi', 'default_code': 'KB-1', 'is_storable': True, 'categ_id': cat('mamul').id, 'tracking': False})
in_type = env.ref('stock.picking_type_in')

olcum = N.create({'name': 'Vida boy ölçümü', 'asama': 'giris', 'test_tipi': 'olcum', 'olcum_yeri': 'urun', 'category_ids': [Command.set(cat('ilk_madde').ids)],
                  'norm': 20, 'alt_sinir': 19.8, 'ust_sinir': 20.2, 'olcu_birimi': 'mm', 'partner_ids': [Command.set(ted.ids)]})
seri_k = N.create({'name': 'Klima görsel', 'asama': 'giris', 'test_tipi': 'gecti_kaldi', 'olcum_yeri': 'lot', 'product_ids': [Command.set(klima.ids)]})
hic = N.create({'name': 'Rastgele %0', 'asama': 'giris', 'test_tipi': 'gecti_kaldi', 'siklik': 'rastgele', 'yuzde': 0})
elle = N.create({'name': 'İsteğe bağlı', 'asama': 'giris', 'test_tipi': 'gecti_kaldi', 'siklik': 'istege_bagli'})

def satinal(partner, lines):
    po = env['purchase.order'].create({'partner_id': partner.id, 'order_line': [
        Command.create({'product_id': p.id, 'product_qty': q, 'price_unit': 10, 'tax_ids': False}) for p, q in lines]})
    po.button_confirm(); return po.picking_ids
rec = satinal(ted, [(vida, 100), (klima, 3)])
kk = rec.atlas_kalite_kontrol_ids
ok(kk.nokta_id == olcum and kk.product_id == vida and kk.durum == 'bekliyor' and kk.name.startswith('KK'), f"mal kabul onayında ölçüm kontrolü açıldı: {kk.name} (lot bazlı / %0 / elle olanlar açılmadı)")
ok(not satinal(ted2, [(vida, 5)]).atlas_kalite_kontrol_ids, "cari filtresi: başka tedarikçide kontrol açılmadı")

B.okut('mal_kabul', rec.id, 'KV-1', 100)
mv = rec.move_ids.filtered(lambda m: m.product_id == klima)
lots = env['stock.lot'].browse(B.seri_uret('mal_kabul', rec.id, mv.id)['seri_ids'])
e = hata(B.dogrula, 'mal_kabul', rec.id)
rec.invalidate_recordset()
kl = rec.atlas_kalite_kontrol_ids.filtered(lambda k: k.nokta_id == seri_k)
ok(e and 'kalite' in e and rec.state != 'done', "bekleyen kontrol varken mal kabul doğrulanamadı")
ok(len(kl) == 3 and set(kl.mapped('lot_name')) == set(lots.mapped('name')), f"doğrulamada her seri için kontrol açıldı: {kl.mapped('lot_name')}")
belge = B.belge_ac('mal_kabul', rec.id)
ok(len(belge['kalite']) == 4, "barkod belge ekranında 4 kalite kontrolü listelendi")
r = B.kalite_sonuc(kk.id, 'degerlendir', {'olcum': '20.5', 'notlar': 'Boy uzun'})
uyari = kk.uyari_ids
ok(kk.durum == 'kaldi' and kk.tolerans_disi and r['sonuc'] == 'uyari' and uyari.partner_id == ted and uyari.name.startswith('UYG'), f"tolerans dışı ölçüm → kaldı, uygunsuzluk {uyari.name}: {uyari.baslik}")
ok('20.5' in (uyari.aciklama or ''), "uygunsuzluk açıklamasında ölçüm değeri")
cz = B.cozumle(kl[0].atlas_qr)
ok(cz['tip'] == 'kalite' and cz['kalite']['id'] == kl[0].id, f"QR çözümlendi: {kl[0].atlas_qr}")
ok(B.cozumle(kl[1].name)['kalite']['id'] == kl[1].id, "kontrol no ile de bulunuyor")
ok(B.ana_ekran()['kalite'] >= 3 and any(x['id'] == kl[0].id for x in B.belge_listesi('kalite')), "ana ekran ve kalite listesi")
for k in kl: B.kalite_sonuc(k.id, 'gecti')
ok(hata(K.browse(kl[0].id).action_gecti) is not None, "sonuçlanan kontrol tekrar sonuçlandırılamaz")
r = B.dogrula('mal_kabul', rec.id)
ok(rec.state == 'done' and rec.atlas_kalite_durum == 'kaldi', f"kontroller bitti, mal kabul tamam (kalite durumu: {rec.atlas_kalite_durum}; başarısız ama durdurmuyor)")
ok(hata(kk.action_sifirla) is not None, "tamamlanmış belgenin kontrol sonucu geri alınamaz")

olcum.kaldi_engeller = True
rec2 = satinal(ted, [(vida, 10)])
k2 = rec2.atlas_kalite_kontrol_ids
k2.write({'olcum': 21, 'olcum_girildi': True}); k2.action_degerlendir()
rec2.move_ids.quantity = 10
ok('kalite' in (hata(rec2.button_validate) or ''), "'başarısızlıkta durdur': kaldı sonrası doğrulama engellendi")
k2.action_sifirla(); k2.action_olcum_kaydet(20.1)
rec2.button_validate()
ok(k2.durum == 'gecti' and rec2.state == 'done', "sonuç geri alınıp yeniden ölçüldü (20.1 geçti), doğrulandı")
rec3 = satinal(ted, [(vida, 1)]); kid = rec3.atlas_kalite_kontrol_ids.id
rec3.action_cancel()
ok(kid and not K.browse(kid).exists(), "iptal edilen belgenin bekleyen kontrolü silindi")

sevk = N.create({'name': 'Ambalaj talimatı', 'asama': 'sevkiyat', 'test_tipi': 'talimat', 'olcum_yeri': 'islem', 'talimat': '<p>Koliyi bantla</p>'})
foto = N.create({'name': 'Yükleme fotoğrafı', 'asama': 'sevkiyat', 'test_tipi': 'foto', 'olcum_yeri': 'islem', 'engelleyici': False})
so = env['sale.order'].create({'partner_id': mus.id, 'order_line': [Command.create({'product_id': vida.id, 'product_uom_qty': 5, 'price_unit': 1, 'tax_ids': False})]})
so.action_confirm(); out = so.picking_ids
ks = out.atlas_kalite_kontrol_ids
ok(set(ks.mapped('nokta_id').ids) == {sevk.id, foto.id} and len(ks) == 2, "sevkiyatta talimat + fotoğraf kontrolleri")
kf = ks.filtered(lambda k: k.nokta_id == foto)
ok('fotoğraf' in (hata(kf.action_gecti) or ''), "fotoğrafsız 'geçti' reddedildi")
ok(hata(ks.filtered(lambda k: k.nokta_id == sevk).action_kaldi) is not None, "talimat 'kaldı' olamaz")
ks.filtered(lambda k: k.nokta_id == sevk).action_gecti()
out.move_ids.quantity = 5; out.button_validate()
ok(out.state == 'done' and kf.durum == 'bekliyor', "engelleyici olmayan fotoğraf kontrolü beklerken sevkiyat yapıldı")

periyot = N.create({'name': 'Haftalık', 'asama': 'giris', 'test_tipi': 'gecti_kaldi', 'siklik': 'periyodik', 'periyot_sayi': 1, 'periyot_birim': 'hafta', 'product_ids': [Command.set(kombi.ids)]})
p1 = satinal(ted2, [(kombi, 1)]); p2 = satinal(ted2, [(kombi, 1)])
ok(len(p1.atlas_kalite_kontrol_ids) == 1 and not p2.atlas_kalite_kontrol_ids, "periyodik: haftada bir kontrol")
yuzde = N.create({'name': '%50', 'asama': 'giris', 'test_tipi': 'gecti_kaldi', 'siklik': 'rastgele', 'yuzde': 50, 'product_ids': [Command.set(klima.ids)]})
secim = [bool(satinal(ted2, [(klima, 1)]).atlas_kalite_kontrol_ids.filtered(lambda k: k.nokta_id == yuzde)) for _ in range(20)]
ok(0 < sum(secim) < 20, f"rastgele %50: 20 belgenin {sum(secim)} tanesinde kontrol")

wc = env['mrp.workcenter'].create({'name': 'Montaj', 'code': 'MNT'})
bom = env['mrp.bom'].create({'product_tmpl_id': kombi.product_tmpl_id.id, 'product_qty': 1,
    'bom_line_ids': [Command.create({'product_id': vida.id, 'product_qty': 2})],
    'operation_ids': [Command.create({'name': 'Montaj', 'workcenter_id': wc.id, 'time_cycle_manual': 10})]})
ara = N.create({'name': 'Montaj numune', 'asama': 'ara', 'test_tipi': 'sayim', 'olcum_yeri': 'islem', 'operation_ids': [Command.set(bom.operation_ids.ids)],
                'numune_miktar': 10, 'kabul_orani': 5})
final = N.create({'name': 'Final kontrol', 'asama': 'final', 'test_tipi': 'kontrol_listesi', 'olcum_yeri': 'urun', 'product_ids': [Command.set(kombi.ids)],
                  'madde_ids': [Command.create({'name': 'Etiket'}), Command.create({'name': 'Sızdırmazlık'})]})
mo = env['mrp.production'].create({'product_id': kombi.id, 'product_qty': 2, 'bom_id': bom.id}); mo.action_confirm()
ka = mo.atlas_kalite_kontrol_ids.filtered(lambda k: k.nokta_id == ara); kfi = mo.atlas_kalite_kontrol_ids.filtered(lambda k: k.nokta_id == final)
ok(ka.workorder_id == mo.workorder_ids and ka.test_edilen == 10 and len(kfi.madde_ids) == 2, f"üretim onayında ara (iş emri) ve final kontrolleri: {ka.name}, {kfi.name}")
wo = mo.workorder_ids; wo.button_start()
ok('kalite' in (hata(wo.button_finish) or ''), "bekleyen ara kontrol iş emrini bitirtmedi")
B.kalite_sonuc(ka.id, 'degerlendir', {'test_edilen': 10, 'hatali': 1})
ok(ka.durum == 'kaldi' and round(ka.hata_orani) == 10 and ka.uyari_ids.workcenter_id == wc, f"numune %10 hatalı > %5 → kaldı, uygunsuzluk iş merkezi {ka.uyari_ids.workcenter_id.name}")
wo.button_finish()
ok(wo.state == 'done', "ara kontrol sonuçlandı, iş emri bitti")
mo.qty_producing = 2; mo.set_qty_producing()
ok('kalite' in (hata(mo.button_mark_done) or ''), "final kontrolü beklerken üretim tamamlanmadı")
ok('maddeleri' in (hata(B.kalite_sonuc, kfi.id, 'degerlendir', {'maddeler': {str(kfi.madde_ids[0].id): 'uygun'}}) or ''), "eksik madde ile değerlendirme reddedildi")
B.kalite_sonuc(kfi.id, 'degerlendir', {'maddeler': {str(m.id): 'uygun' for m in kfi.madde_ids}})
B.okut('uretim', mo.id, 'KV-1', 4)
B.uretim_tamamla(mo.id)
ok(kfi.durum == 'gecti' and mo.state == 'done', f"final kontrolü geçti, üretim tamam ({mo.name})")
ok(mo.atlas_kalite_sayisi == 2 and mo.atlas_uyari_sayisi == 1, "üretim emrinde 2 kontrol, 1 uygunsuzluk")

u = ka.uyari_ids
cozuldu = env.ref('atlas_kalite.asama_cozuldu')
u.write({'neden_id': env.ref('atlas_kalite.neden_makine').id, 'duzeltici_faaliyet': '<p>Fikstür ayarlandı</p>', 'asama_id': cozuldu.id})
ok(u.kapali and u.kapanis_tarihi, "uygunsuzluk DÖF ile çözüldü")
html = env['ir.actions.report']._render_qweb_html('atlas_kalite.report_kalite_kontrol', (kk | kfi | ka).ids)[0]
ok(html.count(b'barcode_type=QR') == 3 and b'ATL%3AQC%3A' in html and 'Sızdırmazlık'.encode() in html, "kontrol fişi çıktısı (QR, maddeler)")
olcum.invalidate_recordset()
ok(olcum.kontrol_sayisi == 2 and round(olcum.basari_orani) == 50, f"kontrol noktası istatistiği: {olcum.kontrol_sayisi} kontrol, %{olcum.basari_orani:.0f} başarı")
env.cr.rollback(); print("(geri alındı)")
