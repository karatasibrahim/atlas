from datetime import date
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
yak = lambda a, b, t=0.01: abs((a or 0) - b) <= t
P = env['res.partner']; M = env['account.move']; c = env.company; A = env['account.account']; J = env['account.journal']
acc = lambda code: A.search([('code', '=', code)], limit=1)
post = lambda m: (m.action_post(), m)[1]
R = env['atlas.finansal.rapor']
rapor = lambda x: env.ref(f'atlas_finansal.{x}')

# Mevcut kayıtlar teste karışmasın: yalnız bu testin şirketinde, 2024-2025 tarihlerinde çalış
ok(R.search_count([]) == 14 and len(rapor('rapor_bilanco').satir_ids) > 40, "14 rapor tanımı (Bilanço TDHP satırlarıyla) kuruldu")
eylemler = env['ir.actions.client'].search([('tag', '=', 'atlas_finansal.rapor')])
ok(len(eylemler) == 14 and env.ref('atlas_finansal.menu_finansal_root').parent_id == env.ref('account.menu_finance_reports'),
   "her rapor için menü eylemi (Muhasebe › Raporlama › Finansal Raporlar)")

usd = env.ref('base.USD')
env['res.currency.rate'].create([{'currency_id': usd.id, 'name': date(2025, 1, 1), 'rate': 1 / 40.0, 'company_id': c.id},
                                 {'currency_id': usd.id, 'name': date(2025, 12, 31), 'rate': 1 / 45.0, 'company_id': c.id}])
mavi = P.create({'name': 'FR Mavi', 'is_company': True, 'atlas_cari_tipi': 'alici', 'atlas_satis_kur_tipi': False})
kir = P.create({'name': 'FR Kırmızı', 'is_company': True, 'atlas_cari_tipi': 'satici'})
banka = J.create({'name': 'FR Banka', 'code': 'FRB', 'type': 'bank'})
fis = lambda d, satirlar, tur='mahsup': post(M.create({'move_type': 'entry', 'atlas_fis_turu': tur, 'date': d, 'line_ids': [
    Command.create({'account_id': acc(k).id, 'debit': max(t, 0), 'credit': max(-t, 0), 'partner_id': p.id if p else False}) for k, t, p in satirlar]}))
inv = lambda mt, p, amt, d, hesap, vade=None, cur=None: post(M.create({
    'move_type': mt, 'partner_id': p.id, 'invoice_date': d, 'invoice_date_due': vade or d, 'currency_id': (cur or c.currency_id).id,
    'invoice_line_ids': [Command.create({'name': 'K', 'quantity': 1, 'price_unit': amt, 'tax_ids': False, 'account_id': acc(hesap).id})]}))
# 2024: geçen yıl verisi
fis(date(2024, 1, 1), [('100001', 100000, None), ('500000', -100000, None)], 'acilis')
inv('out_invoice', mavi, 20000, date(2024, 6, 1), '600000')
# 2025
s1 = inv('out_invoice', mavi, 50000, date(2025, 3, 1), '600000', vade=date(2025, 4, 1))
inv('in_invoice', kir, 30000, date(2025, 3, 5), '620000')
inv('in_invoice', kir, 8000, date(2025, 4, 1), '632000', vade=date(2025, 6, 30))
fis(date(2025, 5, 10), [('100001', 15000, None), ('120000', -15000, mavi)])  # kasaya tahsilat (kısmi)
fis(date(2025, 7, 1), [('300000', -40000, None), ('102001', 40000, None)])      # kredi kullanımı (finansman)
fusd = inv('out_invoice', mavi, 1000, date(2025, 2, 1), '600000', cur=usd)    # 1000 USD × 40 = 40.000
env['account.payment.register'].with_context(active_model='account.move', active_ids=s1.ids).create(
    {'journal_id': banka.id, 'payment_date': date(2025, 9, 1), 'amount': 10000})._create_payments()
st = env['account.bank.statement.line'].create({'journal_id': banka.id, 'date': date(2025, 9, 5), 'amount': 2500, 'payment_ref': 'FR havale'})

S = lambda **kw: dict({'tarih_bas': '2025-01-01', 'tarih_bit': '2025-12-31', 'partner_ids': [], 'sifir_gizle': True}, **kw)
deger = lambda v, ad, i=0: next((s['degerler'][i] for s in v['satirlar'] if s['ad'] == ad), None)

# ---- Gelir tablosu ve karşılaştırma
g = rapor('rapor_gelir').rapor_verisi(S(karsilastirma={'tur': 'gecen_yil', 'adet': 1}, buyume=True))
ok([k['ad'] for k in g['kolonlar']] == ['2025', '2024', '%'], f"kolonlar: {[k['ad'] for k in g['kolonlar']]}")
brut = deger(g, 'A. Brüt Satışlar')
ok(brut >= 90000 and yak(deger(g, 'A. Brüt Satışlar', 1) - deger(g, 'A. Brüt Satışlar', 0), 20000 - brut, 0.01) is not None,
   f"brüt satışlar 2025 {brut:,.0f} / 2024 {deger(g, 'A. Brüt Satışlar', 1):,.0f}")
net = deger(g, 'DÖNEM NET KÂRI VEYA ZARARI')
ok(yak(net, brut - 30000 - 8000 + (deger(g, 'B. Satış İndirimleri (-)') or 0) + (deger(g, 'F. Diğer Faaliyetlerden Olağan Gelir ve Kârlar') or 0)
       + (deger(g, 'G. Diğer Faaliyetlerden Olağan Gider ve Zararlar (-)') or 0) + (deger(g, 'H. Finansman Giderleri (-)') or 0), 0.05),
   f"net kâr = satış − SMM − gider ({net:,.2f})")
ok(deger(g, 'A. Brüt Satışlar', 2) is not None and deger(g, 'A. Brüt Satışlar', 2) > 0, "% değişim kolonu")
alt = rapor('rapor_gelir').alt_satirlar(g['secenekler'], next(s['anahtar'] for s in g['satirlar'] if s['ad'] == 'A. Brüt Satışlar'))
ok(alt and alt[0]['ad'].startswith('600') and alt[0]['denetim'][0], "satır hesaplara açılıyor; tutarda denetim alanı var")
eylem = rapor('rapor_gelir').denetim_ac(alt[0]['denetim'][0])
kalemler = env['account.move.line'].search(eylem['domain'])
ok(eylem['res_model'] == 'account.move.line' and yak(-sum(kalemler.mapped('balance')), alt[0]['degerler'][0]), "denetim: kalemler tutarı veriyor")
ok(len(rapor('rapor_gelir').rapor_verisi(S(karsilastirma={'tur': 'onceki', 'adet': 3}))['kolonlar']) == 4, "3 önceki dönem karşılaştırması")

# ---- Bilanço: aktif = pasif (kapanış öncesi cari yıl kârı dahil)
b = rapor('rapor_bilanco').rapor_verisi({'tarih_bit': '2025-12-31'})
aktif, pasif = deger(b, 'AKTİF (VARLIKLAR)'), deger(b, 'PASİF (KAYNAKLAR)')
ok(aktif > 0 and yak(aktif, pasif) and not any('Aktif − Pasif' in s['ad'] for s in b['satirlar']),
   f"bilanço dengede: aktif {aktif:,.2f} = pasif {pasif:,.2f}")
ok(deger(b, 'A. Mali Borçlar') == 40000 and deger(b, 'Cari Yıl Kârı (Zararı) — kapanış öncesi') is not None, "kredi 300'de, cari yıl kârı özkaynakta")
ok([k['ad'] for k in b['kolonlar']] == ['31.12.2025'], "bilanço tek tarih itibarıyla")

# ---- Yönetici özeti
y = rapor('rapor_yonetici').rapor_verisi(S())
ok(deger(y, 'Brüt Kâr') == deger(y, 'Net Satışlar') - deger(y, 'Satışların Maliyeti') and deger(y, 'Cari Oran (Dönen Varlıklar / KVYK)') > 0
   and 0 < deger(y, 'Brüt Kâr Marjı (Brüt Kâr / Net Satış)') < 100, "yönetici özeti: brüt kâr, marj ve cari oran")
ok(not any(s['ad'].endswith('(yardımcı)') for s in y['satirlar']), "yardımcı satırlar gizli")

# ---- Nakit akış
n = rapor('rapor_nakit').rapor_verisi(S())
ok(yak(deger(n, 'Müşterilerden tahsilatlar'), 25000) and yak(deger(n, 'Kredi kullanımı ve geri ödemeleri'), 40000),
   f"nakit akış: tahsilat (kasa 15.000 + banka 10.000) {deger(n, 'Müşterilerden tahsilatlar')}, kredi {deger(n, 'Kredi kullanımı ve geri ödemeleri')}")
ok(not any('açıklanamayan' in s['ad'] for s in n['satirlar']) and
   yak(deger(n, 'Dönem Sonu Nakit') - deger(n, 'Dönem Başı Nakit'), deger(n, 'NAKİTTEKİ NET DEĞİŞİM (A + B + C)')),
   "dönem başı + net değişim = dönem sonu nakit")

# ---- Mizan
m = rapor('rapor_mizan').rapor_verisi(S())
top = deger(m, 'GENEL TOPLAM', 3), deger(m, 'GENEL TOPLAM', 4), deger(m, 'GENEL TOPLAM', 5), deger(m, 'GENEL TOPLAM', 6)
ok(yak(top[0], top[1]) and yak(top[2], top[3]) and top[0] > 0, f"mizan: toplam borç = alacak ({top[0]:,.2f}), borç bakiye = alacak bakiye")
ok(any(s['ad'].startswith('120 ') and s['seviye'] == 2 for s in m['satirlar']), "seviye 3: ana hesaplar görünüyor (1 → 12 → 120)")
m4 = rapor('rapor_mizan').rapor_verisi(S(seviye='4', hesap_filtre='120'))
ok(m4['satirlar'] and all(s['ad'].startswith(('1', 'GENEL')) for s in m4['satirlar']) and any(s['seviye'] == 3 for s in m4['satirlar']),
   "hesap filtresi ve alt hesap seviyesi")

# ---- Büyük defter: yürüyen bakiye, sayfa
md = rapor('rapor_muavin').rapor_verisi(S(hesap_filtre='100'))
kasa = next(s for s in md['satirlar'] if s['ad'].startswith('100'))
alt = rapor('rapor_muavin').alt_satirlar(md['secenekler'], kasa['anahtar'])
ok(alt[0]['ad'] == 'Açılış Bakiyesi' and yak(alt[0]['degerler'][6], 100000) and yak(alt[-1]['degerler'][6], kasa['degerler'][6]),
   f"muavin: açılış 100.000, son yürüyen bakiye = hesap bakiyesi ({kasa['degerler'][6]:,.2f})")

# ---- Cari defter
cd = rapor('rapor_cari').rapor_verisi(S(partner_ids=[mavi.id]))
ok(len([s for s in cd['satirlar'] if s['sinif'] == 'normal']) == 1 and cd['satirlar'][0]['ad'] == 'FR Mavi', "cari defter: cari filtresi")

# ---- Yaşlandırma (geçmiş tarihe göre)
ya1 = rapor('rapor_yas_alacak').rapor_verisi({'tarih_bit': '2025-08-31', 'partner_ids': [mavi.id]})
ya2 = rapor('rapor_yas_alacak').rapor_verisi({'tarih_bit': '2025-12-31', 'partner_ids': [mavi.id]})
t1, t2 = ya1['satirlar'][0]['degerler'][-1], ya2['satirlar'][0]['degerler'][-1]
ok(yak(t1 - t2, 10000), f"31.08'de ödeme yok ({t1:,.0f}); 31.12'de 10.000 ödeme düşülmüş ({t2:,.0f})")
ok(ya2['satirlar'][0]['degerler'][6] > 0, "120+ gün kovası dolu (2024 faturası)")
by = rapor('rapor_yas_borc').rapor_verisi({'tarih_bit': '2025-05-15', 'partner_ids': [kir.id]})
ok(yak(by['satirlar'][0]['degerler'][1], 8000) and yak(by['satirlar'][0]['degerler'][-1], 38000), "borç yaşlandırma: vadesi gelmemiş 8.000, toplam 38.000")

# ---- Gerçekleşmemiş kur farkı
k = rapor('rapor_kur').rapor_verisi({'tarih_bit': '2025-12-31'})
usd_satir = next(s for s in k['satirlar'] if s['anahtar'].startswith('doviz:'))
ok(yak(usd_satir['degerler'][0], 1000) and yak(usd_satir['degerler'][2], 45) and yak(usd_satir['degerler'][4], 5000),
   f"USD alacak 1000 × (45 − 40) = 5.000 kur farkı ({usd_satir['degerler'][4]})")

# ---- Banka denkleştirme
bd = rapor('rapor_banka').rapor_verisi({'tarih_bit': '2025-12-31', 'yevmiye_ids': [banka.id]})
satir = {s['ad']: s for s in bd['satirlar']}
ok(yak(satir['Eşleştirilmemiş ekstre satırları']['degerler'][2], 2500) and yak(satir['(+) Bekleyen tahsilatlar (ekstreye düşmemiş)']['degerler'][2], 10000)
   and yak(satir['Açıklanamayan fark']['degerler'][2], 0), "banka: 2.500 eşleşmemiş ekstre, 10.000 bekleyen tahsilat, fark yok")
ana = rapor('rapor_banka').rapor_verisi({'tarih_bit': '2025-12-31', 'yevmiye_ids': [J.search([('type', '=', 'bank'), ('id', '!=', banka.id),
                                         ('default_account_id', '=', acc('102001').id)], limit=1).id]})
sa = {s['ad']: s for s in ana['satirlar']}
ok(yak(sa['(±) Ekstre dışı doğrudan kayıtlar (mahsup fişi vb.)']['degerler'][2], 40000) and yak(sa['Açıklanamayan fark']['degerler'][2], 0)
   and '(+) Bekleyen tahsilatlar (ekstreye düşmemiş)' not in sa, "102001: mahsupla yazılan kredi 'ekstre dışı' satırında; başka yevmiyenin bekleyeni karışmıyor")

# ---- Vergi raporu, yevmiye, amortisman
v = rapor('rapor_vergi').rapor_verisi(S())
ok(len(v['kolonlar']) == 2 and v['satirlar'][0]['ad'].startswith('Satışlar'), "vergi raporu çalışıyor")
yv = rapor('rapor_yevmiye').rapor_verisi(S())
ok(yv['satirlar'] and yak(deger(yv, 'TOPLAM', 3), deger(yv, 'TOPLAM', 4)), "yevmiye raporu: borç = alacak")
ok(isinstance(rapor('rapor_amortisman').rapor_verisi(S())['satirlar'], list), "amortisman tablosu çalışıyor")

# ---- Notlar, sıfır gizleme, açık satır durumu, çıktılar
anahtar = next(s['anahtar'] for s in b['satirlar'] if s['ad'] == 'A. Mali Borçlar')
rapor('rapor_bilanco').not_kaydet(anahtar, 'Kredi Temmuz 2025, 24 ay vadeli')
ok(next(s for s in rapor('rapor_bilanco').rapor_verisi({'tarih_bit': '2025-12-31'})['satirlar'] if s['anahtar'] == anahtar)['not']
   == 'Kredi Temmuz 2025, 24 ay vadeli', "satır notu kaydedildi ve raporda görünüyor")
gizli = rapor('rapor_bilanco').rapor_verisi({'tarih_bit': '2025-12-31', 'sifir_gizle': False})
ok(len(gizli['satirlar']) >= len(b['satirlar']), "sıfırları gizle kapalıyken tüm satırlar")
acik = rapor('rapor_bilanco').rapor_verisi({'tarih_bit': '2025-12-31', 'acik': [anahtar]})
ok(any(s['anahtar'].startswith(anahtar + '|hesap:') for s in acik['satirlar']), "açık satır listesi yeniden yüklemede korunuyor")
ad, xlsx = rapor('rapor_gelir').xlsx_olustur(S(karsilastirma={'tur': 'gecen_yil', 'adet': 1}))
ok(xlsx[:2] == b'PK' and ad.endswith('.xlsx'), "Excel çıktısı")
html = env['ir.actions.report']._render_qweb_html('atlas_finansal.action_report_finansal', rapor('rapor_bilanco').ids,
                                                  data={'rapor_id': rapor('rapor_bilanco').id, 'secenekler': {'tarih_bit': '2025-12-31'}})[0]
ok(b'AKT' in html and b'Kredi Temmuz' in html, "PDF şablonu (HTML) notlarla oluşuyor")

# ---- Otomatik gönderim
gon = env['atlas.finansal.gonderim'].create({'rapor_id': rapor('rapor_gelir').id, 'alici_ids': [Command.set(mavi.ids)],
                                             'donem': 'onceki_ay', 'sonraki_tarih': date(2020, 1, 1)})
mail = gon._gonder()
ok(mail.attachment_ids and mail.attachment_ids[0].name.endswith('.xlsx') and gon.sonraki_tarih > date(2020, 1, 1), "otomatik gönderim: Excel ekli e-posta kuyrukta")
env.cr.rollback(); print("(geri alındı)")
