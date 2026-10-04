import base64
from datetime import timedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
def hata(fn, *a, **k):
    try:
        with env.cr.savepoint(): fn(*a, **k)
        return None
    except UserError as e: return str(e)
Prod = env['product.product']; Bom = env['mrp.bom']; Eco = env['atlas.plm.eco']
cat = lambda x: env.ref(f'atlas_stok.categ_{x}')
hm = lambda ad, kod: Prod.create({'name': ad, 'default_code': kod, 'is_storable': True, 'categ_id': cat('ilk_madde').id})
vida, conta, pul = hm('PLM Vida', 'PV'), hm('PLM Conta', 'PC'), hm('PLM Pul', 'PP')
kombi = Prod.create({'name': 'PLM Kombi', 'default_code': 'PK', 'is_storable': True, 'tracking': False, 'categ_id': cat('mamul').id})
tmpl = kombi.product_tmpl_id
wc_a = env['mrp.workcenter'].create({'name': 'PLM Montaj', 'code': 'PMA'}); wc_b = env['mrp.workcenter'].create({'name': 'PLM Test', 'code': 'PMB'})
v1 = Bom.create({'product_tmpl_id': tmpl.id, 'product_qty': 1, 'code': 'KMB',
    'bom_line_ids': [Command.create({'product_id': vida.id, 'product_qty': 2}), Command.create({'product_id': conta.id, 'product_qty': 1})],
    'operation_ids': [Command.create({'name': 'Montaj', 'workcenter_id': wc_a.id, 'time_cycle_manual': 10})]})
nokta = env['atlas.kalite.nokta'].create({'name': 'Montaj kontrol', 'asama': 'ara', 'test_tipi': 'gecti_kaldi', 'operation_ids': [Command.set(v1.operation_ids.ids)]}) if 'atlas.kalite.nokta' in env else None
ok(v1.atlas_versiyon == 1 and tmpl.atlas_versiyon == 1, "başlangıç: reçete ve ürün sürüm 1")

ctx = v1.action_atlas_eco_baslat()['context']
eco = Eco.with_context(**ctx).create({'baslik': 'Conta kaldırılıyor, pul ekleniyor'})
ok(eco.name.startswith('ECO') and eco.bom_id == v1 and eco.tip_id == env.ref('atlas_plm.tip_revizyon') and eco.asama_id == env.ref('atlas_plm.asama_yeni'),
   f"reçeteden ECO açıldı: {eco.name} ({eco.asama_id.name})")
ok('revizyon' in (hata(eco.write, {'asama_id': env.ref('atlas_plm.asama_uygulandi').id}) or ''), "revizyon başlamadan uygulama aşamasına geçilemez")
eco.action_revizyon_baslat()
v2 = eco.yeni_bom_id
ok(not v2.active and v2.atlas_versiyon == 2 and v2.atlas_onceki_bom_id == v1 and eco.durum == 'islemde'
   and v2.with_context(active_test=False).operation_ids.atlas_onceki_operation_id == v1.operation_ids, "taslak revizyon: arşivli kopya, sürüm 2, operasyon eşleşmesi")
ok(Bom._bom_find(kombi)[kombi] == v1, "üretim hâlâ sürüm 1'i kullanıyor")
satir = {l.product_id: l for l in v2.bom_line_ids}
v2.write({'bom_line_ids': [Command.update(satir[vida].id, {'product_qty': 3}), Command.delete(satir[conta].id),
                           Command.create({'product_id': pul.id, 'product_qty': 4})],
          'operation_ids': [Command.update(v2.operation_ids.id, {'time_cycle_manual': 12}),
                            Command.create({'name': 'Test', 'workcenter_id': wc_b.id, 'time_cycle_manual': 5})]})
bd = {d.product_id: d for d in eco.bom_degisiklik_ids}; rd = {d.operasyon: d for d in eco.rota_degisiklik_ids}
ok(len(bd) == 3 and bd[vida].tip == 'guncelle' and bd[vida].fark == 1 and bd[conta].tip == 'sil' and bd[pul].tip == 'ekle' and bd[pul].yeni_miktar == 4,
   "bileşen farkı: vida 2→3, conta çıkarıldı, pul eklendi")
ok(rd['Montaj'].tip == 'guncelle' and rd['Montaj'].yeni_sure == 12 and rd['Test'].tip == 'ekle' and rd['Test'].yeni_workcenter_id == wc_b,
   "operasyon farkı: Montaj 10→12 dk, Test eklendi")

eco.action_sonraki_asama()
onay = eco.onay_ids
ok(eco.asama_id == env.ref('atlas_plm.asama_inceleme') and len(onay) == 1 and onay.durum == 'bekliyor' and eco.onay_durumu == 'bekliyor', "incelemede zorunlu onay açıldı")
ok(eco.activity_ids and eco.onayimi_bekliyor and eco in Eco.search([('onayimi_bekliyor', '=', True)]), "yöneticiye onay aktivitesi, 'onayımı bekleyen' filtresi")
ok('onay' in (hata(eco.action_sonraki_asama) or ''), "bekleyen zorunlu onayla ilerletilemez")
kullanici = env['res.users'].create({'name': 'PLM Mühendis', 'login': 'plm_muhendis_test', 'group_ids': [Command.link(env.ref('atlas_plm.group_plm_user').id)]})
ok(not eco.with_user(kullanici).onayimi_bekliyor and hata(eco.with_user(kullanici).action_onayla) is not None, "yetkisiz kullanıcı onaylayamaz")
eco.action_reddet()
ok(eco.onay_durumu == 'reddedildi' and 'reddedildi' in (hata(eco.action_sonraki_asama) or ''), "reddedilen ECO ilerletilemez")
onay.action_onayla()
ok(eco.onay_durumu == 'onaylandi' and not eco.activity_ids, f"onaylandı ({onay.user_id.name}), aktivite kapandı")
eco.action_sonraki_asama(); eco.action_sonraki_asama()
v1.invalidate_recordset(); tmpl.invalidate_recordset()
ok(eco.durum == 'bitti' and eco.asama_id.son_asama and v2.active and not v1.active and tmpl.atlas_versiyon == 2, "uygulandı: sürüm 2 aktif, sürüm 1 arşivlendi, ürün sürüm 2")
ok(Bom._bom_find(kombi)[kombi] == v2, "üretim artık sürüm 2'yi kullanıyor")
ok(not nokta or v2.operation_ids.filtered(lambda o: o.name == 'Montaj') in nokta.operation_ids, "kalite kontrol noktası yeni Montaj operasyonuna genişletildi")
mo = env['mrp.production'].create({'product_id': kombi.id, 'product_qty': 1}); mo.action_confirm()
ok(mo.bom_id == v2 and {m.product_id: m.product_uom_qty for m in mo.move_raw_ids} == {vida: 3, pul: 4} and len(mo.workorder_ids) == 2,
   "yeni üretim emri: 3 vida + 4 pul, 2 iş emri")
ok(hata(eco.write, {'asama_id': env.ref('atlas_plm.asama_yeni').id}) is not None and hata(eco.action_iptal) is not None, "uygulanan ECO geri alınamaz / iptal edilemez")

eco2 = Eco.with_context(**v2.action_atlas_eco_baslat()['context']).create({'baslik': 'Vida 4 adet', 'yururluk': 'tarih', 'yururluk_tarihi': fields.Datetime.now() + timedelta(days=3)})
eco3 = Eco.with_context(**v2.action_atlas_eco_baslat()['context']).create({'baslik': 'Paralel değişiklik'})
eco2.action_revizyon_baslat(); eco3.action_revizyon_baslat()
v3 = eco2.yeni_bom_id
v3.bom_line_ids.filtered(lambda l: l.product_id == vida).product_qty = 4
ok(len(eco2.bom_degisiklik_ids) == 1, "bileşen satırı doğrudan düzenlenince fark güncellendi")
eco2.action_sonraki_asama(); eco2.action_onayla(); eco2.action_sonraki_asama(); eco2.action_sonraki_asama()
ok(eco2.zamanlandi and eco2.durum == 'islemde' and not v3.active and v2.active, "ileri yürürlük tarihi: onaylandı ama uygulanmadı")
eco2.yururluk_tarihi = fields.Datetime.now() - timedelta(minutes=1)
Eco._cron_yururluk()
ok(eco2.durum == 'bitti' and v3.active and not v2.active and tmpl.atlas_versiyon == 3, "zamanlanmış görev yürürlük tarihinde uyguladı (sürüm 3)")
eco3.action_sonraki_asama(); eco3.action_onayla(); eco3.action_sonraki_asama()
ok('başka bir değişiklik' in (hata(eco3.action_sonraki_asama) or ''), "aynı sürümden açılan paralel ECO çakışma uyarısı verdi")
taslak = eco3.yeni_bom_id; eco3.action_iptal()
ok(eco3.durum == 'iptal' and not taslak.exists(), "iptal: taslak revizyon silindi")
ok(v3.atlas_surum_sayisi == 3 and set(v3._atlas_surumler().mapped('atlas_versiyon')) == {1, 2, 3}, "sürüm geçmişi: 1, 2, 3")

ek = env['ir.attachment'].create({'name': 'montaj_talimati.txt', 'raw': b'Montaj talimati', 'res_model': 'atlas.plm.eco'})
eco4 = Eco.create({'baslik': 'Montaj talimatı güncellendi', 'uygulama': 'urun', 'product_tmpl_id': tmpl.id, 'dokuman_ids': [Command.set(ek.ids)]})
eco4.action_revizyon_baslat(); eco4.action_sonraki_asama(); eco4.action_onayla(); eco4.action_sonraki_asama(); eco4.action_sonraki_asama()
doc = env['product.document'].search([('res_model', '=', 'product.template'), ('res_id', '=', tmpl.id)])
ok(eco4.durum == 'bitti' and tmpl.atlas_versiyon == 4 and doc.name == 'montaj_talimati.txt' and ek.res_model == 'atlas.plm.eco', "doküman ECO'su: ürün sürüm 4, doküman ürüne kopyalandı")

yeni_urun = Prod.create({'name': 'PLM Yeni Ürün', 'is_storable': True, 'tracking': False, 'categ_id': cat('mamul').id})
eco5 = Eco.create({'baslik': 'Yeni ürün', 'tip_id': env.ref('atlas_plm.tip_yeni_urun').id, 'product_tmpl_id': yeni_urun.product_tmpl_id.id})
eco5.action_revizyon_baslat()
eco5.yeni_bom_id.bom_line_ids = [Command.create({'product_id': vida.id, 'product_qty': 1})]
eco5.action_sonraki_asama(); eco5.action_onayla(); eco5.action_sonraki_asama(); eco5.action_sonraki_asama()
ok(eco5.yeni_bom_id.active and eco5.yeni_bom_id.atlas_versiyon == 1 and Bom._bom_find(yeni_urun)[yeni_urun] == eco5.yeni_bom_id, "yeni ürün girişi: boş reçete hazırlandı, uygulanınca devreye girdi")
html = env['ir.actions.report']._render_qweb_html('atlas_plm.report_eco', eco.ids)[0]
ok('Değişiklik'.encode() in html and b'PLM Pul' in html and b'Montaj' in html, "ECO değişiklik özeti çıktısı")
env.cr.rollback(); print("(geri alındı)")
