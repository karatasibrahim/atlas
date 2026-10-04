from datetime import date
from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
SO = env['sale.order']; Plan = env['atlas.abonelik.plan']
aylik = env.ref('atlas_abonelik.plan_aylik'); uc = env.ref('atlas_abonelik.plan_3aylik')
taahhutlu = Plan.create({'name': 'Aylık 2 ay taahhüt', 'aralik': 1, 'birim': 'ay', 'taahhut_aralik': 2, 'taahhut_birim': 'ay'})
mus = env['res.partner'].create({'name': 'ABO Müşteri', 'is_company': True, 'atlas_cari_tipi': 'alici'})
hizmet = env['product.product'].create({'name': 'ABO Bakım Hizmeti', 'type': 'service', 'list_price': 1000})
def abonelik(plan, bas, adet=2, fiyat=1000):
    so = SO.create({'partner_id': mus.id, 'atlas_plan_id': plan.id, 'atlas_baslangic': bas,
                    'order_line': [Command.create({'product_id': hizmet.id, 'product_uom_qty': adet, 'price_unit': fiyat, 'tax_ids': False})]})
    so.action_confirm(); return so
bugun = fields.Date.context_today(SO)
s1 = abonelik(aylik, date(2026, 7, 1))
ok(s1.atlas_abonelik_durum == 'devam' and s1.atlas_sonraki_fatura == date(2026, 7, 1) and s1.atlas_mrr == 2000, f"abonelik onaylandı, MRR {s1.atlas_mrr:,.0f}")
try:
    with env.cr.savepoint(): s1._create_invoices(); hata = False
except UserError: hata = True
ok(hata, "standart 'Fatura Oluştur' abonelikte kullanılmıyor")
SO._cron_atlas_abonelik()
f = s1.atlas_abonelik_fatura_ids.sorted('invoice_date')
beklenen = len([m for m in range(7, 13) if date(2026, m, 1) <= bugun])
ok(len(f) == beklenen and all(x.state == 'posted' and x.amount_untaxed == 2000 for x in f), f"geride kalan {beklenen} dönem faturalandı (onaylı, 2.000)")
ok(f[0].invoice_date == date(2026, 7, 1) and '01.07.2026 - 31.07.2026' in f[0].invoice_line_ids[0].name, "fatura satırında dönem açıklaması")
ok(s1.atlas_sonraki_fatura > bugun, f"sonraki fatura {s1.atlas_sonraki_fatura}")
SO._cron_atlas_abonelik()
ok(len(s1.atlas_abonelik_fatura_ids) == beklenen, "aynı dönem ikinci kez faturalanmadı")
s2 = abonelik(uc, bugun, 1, 3000)
ok(s2.atlas_mrr == 1000 and s2.atlas_arr == 12000, "3 aylık 3.000 → MRR 1.000, ARR 12.000")
s3 = abonelik(taahhutlu, date(2026, 8, 1))
ok(s3.atlas_bitis == date(2026, 9, 30), f"taahhüt bitişi {s3.atlas_bitis}")
SO._cron_atlas_abonelik()
ok(len(s3.atlas_abonelik_fatura_ids) == 2 and s3.atlas_abonelik_durum == 'kapandi' and s3.atlas_mrr == 0, "taahhüt sonunda 2 fatura, abonelik kapandı, MRR 0")
y = SO.browse(s3.action_atlas_yenile()['res_id'])
ok(s3.atlas_abonelik_durum == 'yenilendi' and y.atlas_baslangic == date(2026, 10, 1) and y.atlas_onceki_id == s3 and y.state == 'draft', "yenileme: yeni dönem siparişi 01.10.2026")
y.action_confirm()
ok(y.atlas_abonelik_durum == 'devam' and y.atlas_bitis == date(2026, 11, 30), "yenilenen abonelik onaylandı (yeni taahhüt)")
s2.action_atlas_durdur()
ok(s2.atlas_abonelik_durum == 'durduruldu' and s2.atlas_mrr == 0, "durdurulan abonelik MRR'a katılmıyor")
once = len(s2.atlas_abonelik_fatura_ids)
s2.atlas_sonraki_fatura = date(2026, 1, 1); SO._cron_atlas_abonelik()
ok(len(s2.atlas_abonelik_fatura_ids) == once, "durdurulan abonelik faturalanmadı")
s2.action_atlas_devam()
ok(s2.atlas_abonelik_durum == 'devam' and s2.atlas_sonraki_fatura == bugun, "devam: durdurulan dönemler atlandı")
try:
    with env.cr.savepoint(): s1.action_atlas_kapat(); hata = False
except UserError: hata = True
s1.atlas_kapanis_id = env.ref('atlas_abonelik.kapanis_rakip'); s1.action_atlas_kapat()
ok(hata and s1.atlas_abonelik_durum == 'kapandi', "kapanış nedeni zorunlu, abonelik kapandı")
manuel = s2.action_atlas_faturala()
ok(len(s2.atlas_abonelik_fatura_ids) == once + 1, "'Dönemi Faturala' ile elle fatura")
env.cr.rollback(); print("(geri alındı)")
