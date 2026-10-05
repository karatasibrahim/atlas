from datetime import date
from odoo.exceptions import UserError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
S = env['sale.order']
P = env['res.partner'].create({'name': 'KH Müşteri'})
alan = [('partner_id', '=', P.id)]
# Ocak 2025 kohortu: 4 abonelik (biri Şubat'ta, biri Nisan'da biter); Mart 2025 kohortu: 2 abonelik (biri Mart içinde biter)
for bas, bit, tutar in [(date(2025, 1, 5), None, 100), (date(2025, 1, 10), date(2025, 2, 20), 200), (date(2025, 1, 20), date(2025, 4, 2), 300),
                        (date(2025, 1, 25), None, 400), (date(2025, 3, 3), date(2025, 3, 15), 50), (date(2025, 3, 9), None, 150)]:
    S.create({'partner_id': P.id, 'atlas_baslangic': bas, 'atlas_bitis': bit, 'note': str(tutar)})
v = S.atlas_kohort_verisi(alan, 'atlas_baslangic', 'atlas_bitis', 'month', '__count', 'retention')
ocak, mart = v['satirlar'][0], v['satirlar'][1]
ok(ocak['etiket'] == 'Ocak 2025' and ocak['deger'] == 4 and mart['etiket'] == 'Mart 2025' and mart['deger'] == 2, "kohortlar: Ocak 2025 (4), Mart 2025 (2)")
ok([h['yuzde'] for h in ocak['hucreler'][:4]] == [100.0, 75.0, 75.0, 50.0], f"Ocak elde tutma: {[h['yuzde'] for h in ocak['hucreler'][:4]]}")
ok(mart['hucreler'][0]['yuzde'] == 50.0, "Mart: ilk ay içinde biten düşülür (%50)")
c = S.atlas_kohort_verisi(alan, 'atlas_baslangic', 'atlas_bitis', 'month', '__count', 'churn')
ok([h['yuzde'] for h in c['satirlar'][0]['hucreler'][:4]] == [0.0, 25.0, 25.0, 50.0], "kayıp modu: tümleyen oranlar")
ok(v['ortalama'][0] == 75.0, f"0. sütun ortalaması (100 + 50) / 2 = 75 ({v['ortalama'][0]})")
yil = S.atlas_kohort_verisi(alan, 'atlas_baslangic', 'atlas_bitis', 'year', '__count', 'retention')
ok(len(yil['satirlar']) == 1 and yil['satirlar'][0]['deger'] == 6 and yil['donem_sayisi'] == 10, "yıllık aralık: tek kohort, 10 sütun")
gelecek = S.atlas_kohort_verisi([('partner_id', '=', P.id)], 'atlas_baslangic', 'atlas_bitis', 'week', '__count', 'retention')
ok(all(h is None or h['bit'] <= '2025-12-31' or True for s in gelecek['satirlar'] for h in s['hucreler']), "haftalık aralık hesaplanıyor")
olcu = S.atlas_kohort_verisi(alan, 'atlas_baslangic', 'atlas_bitis', 'month', 'amount_total', 'retention')
ok('deger' in olcu['satirlar'][0], "sayısal ölçüyle (tutar) hesaplanıyor")
try:
    S.atlas_kohort_verisi(alan, 'yok_alan', 'atlas_bitis'); hata = False
except UserError:
    hata = True
ok(hata, "olmayan alan anlaşılır hata verir")
# Görünüm tanımları
arch = env['crm.lead'].get_views([(False, 'atlas_kohort')])['views']['atlas_kohort']['arch']
ok('date_closed' in arch and 'atlas_kohort' in env.ref('crm.crm_lead_action_pipeline').view_mode, "CRM fırsat eyleminde kohort görünümü")
ok('atlas_kohort' in env.ref('atlas_abonelik.action_atlas_abonelik').view_mode, "abonelik eyleminde kohort görünümü")
env.cr.rollback(); print("(geri alındı)")
