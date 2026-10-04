import base64
from datetime import date
from lxml import etree
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; P = env['res.partner']; M = env['account.move']; B = env['atlas.beyanname']
ref = lambda x: env['account.chart.template'].with_company(c).ref(x)
tax = lambda name: env['account.tax'].search([('company_id', '=', c.id), ('name', '=', name)], limit=1)
s20, p20 = ref('tr_s_20'), ref('tr_p_20')
s_tev5 = tax('Satış KDV %20 Tevkifatlı 5/10'); p_tev9 = tax('Alış KDV %20 Tevkifatlı 9/10')
s_tev5.atlas_gib_kod_id = env.ref('atlas_muhasebe_base.gib_602'); p_tev9.atlas_gib_kod_id = env.ref('atlas_muhasebe_base.gib_601')
ihr = tax('KDV %0 - İhracat (301)')
fp_ihr = env['account.fiscal.position'].search([('company_id', '=', c.id), ('atlas_gib_kod_id.tip', '=', 'ihracat')], limit=1)
tr = env.ref('base.tr')
def cari(ad, vkn, tip): return P.create({'name': ad, 'is_company': True, 'atlas_cari_tipi': tip, 'vat': vkn, 'country_id': tr.id})
mus = cari('BYN Müşteri', '1234567890', 'alici'); kamu = cari('BYN Belediye', '1234567890', 'alici')
ted = cari('BYN Tedarikçi', '1234567890', 'satici'); mtd = cari('BYN Müteahhit', '1234567890', 'satici'); kucuk = cari('BYN Küçük', '1234567890', 'satici')
yab = P.create({'name': 'BYN Foreign', 'is_company': True, 'atlas_cari_tipi': 'alici', 'country_id': env.ref('base.de').id})
def fatura(mt, partner, tarih, tutar, vergi, fp=None):
    m = M.create({'move_type': mt, 'partner_id': partner.id, 'invoice_date': tarih, 'date': tarih, 'fiscal_position_id': fp.id if fp else False,
                  'invoice_line_ids': [Command.create({'name': 'K', 'quantity': 1, 'price_unit': tutar, 'tax_ids': [Command.set(vergi.ids)] if vergi else False})]})
    m.action_post(); return m
fatura('in_invoice', ted, date(2031, 2, 10), 100000, p20); fatura('out_invoice', mus, date(2031, 2, 12), 50000, s20)
subat = B.create({'tip': 'kdv1', 'yil': 2031, 'ay': '2'}); subat.action_hesapla()
ok(subat.beyan_edilen_kdv == 10000 and subat.indirilecek_kdv == 20000 and subat.sonraki_devreden == 10000 and subat.odenecek_kdv == 0,
   f"Şubat: hesaplanan 10.000, indirilecek 20.000 → devreden {subat.sonraki_devreden:,.2f}")
subat.action_onayla()
fatura('out_invoice', mus, date(2031, 3, 5), 200000, s20)
fatura('out_invoice', kamu, date(2031, 3, 6), 10000, s_tev5)
fatura('out_invoice', yab, date(2031, 3, 7), 30000, ihr, fp_ihr)
fatura('in_invoice', ted, date(2031, 3, 8), 50000, p20)
fatura('in_invoice', mtd, date(2031, 3, 9), 10000, p_tev9)
fatura('in_invoice', kucuk, date(2031, 3, 10), 3000, p20)
mart = B.create({'tip': 'kdv1', 'yil': 2031, 'ay': '3'}); mart.action_hesapla()
bolum = lambda b, k: mart.satir_ids.filtered(lambda s: s.bolum == k)
m20 = bolum(mart, 'matrah').filtered(lambda s: s.oran == 20)
ok(m20.matrah == 210000 and m20.vergi == 42000, f"matrah %20: 210.000 (tevkifatlı dahil), vergi 42.000")
tv = bolum(mart, 'tevkifat')
ok(tv.kod == '602' and tv.tevkifat_orani == '5/10' and tv.matrah == 10000 and tv.vergi == 2000 and tv.tevkifat == 1000, "kısmi tevkifat 602, 5/10: vergi 2.000, tevkif 1.000")
ist = bolum(mart, 'istisna')
ok(ist.kod == '301' and ist.matrah == 30000, "istisna 301 ihracat 30.000")
ok(mart.hesaplanan_kdv == 42000 and mart.beyan_edilen_kdv == 41000 and mart.devreden_kdv == 10000, "beyan edilen 41.000, devreden Şubat'tan otomatik 10.000")
ok(mart.indirilecek_kdv == 12600 and mart.odenecek_kdv == 18400 and mart.matrah_toplam == 240000, f"indirilecek 12.600 → ödenecek {mart.odenecek_kdv:,.2f}")
kontrol = {s.kod: s for s in bolum(mart, 'kontrol')}
ok(kontrol['391'].tevkifat == 0 and kontrol['191'].tevkifat == 0, f"hesap kontrolü: 391 farkı {kontrol['391'].tevkifat}, 191 farkı {kontrol['191'].tevkifat}")
kdv2 = B.create({'tip': 'kdv2', 'yil': 2031, 'ay': '3'}); kdv2.action_hesapla()
k = kdv2.satir_ids.filtered(lambda s: s.bolum == 'kdv2')
ok(len(k) == 1 and k.kod == '601' and k.matrah == 10000 and k.tevkifat == 1800 and kdv2.kdv2_toplam == 1800, "KDV2: 601, matrah 10.000, sorumlu sıfatıyla 1.800")
ok(kdv2.satir_ids.filtered(lambda s: s.bolum == 'kontrol').tevkifat == 0, "KDV2 360001 kontrolü tutuyor")
ba = B.create({'tip': 'ba', 'yil': 2031, 'ay': '3'}); ba.action_hesapla()
bs = B.create({'tip': 'bs', 'yil': 2031, 'ay': '3'}); bs.action_hesapla()
ba_c = {s.partner_id: s for s in ba.satir_ids}
ok(set(ba_c) == {ted, mtd} and ba_c[ted].matrah == 50000 and ba_c[ted].belge_sayisi == 1 and ba_c[ted].kod == '1234567890', "Form Ba: 3.000 TL'lik alış sınır altında, 2 cari")
ok({s.partner_id for s in bs.satir_ids} == {mus, kamu, yab} and bs.bildirim_sayisi == 3, "Form Bs: 3 cari (yurt dışı dahil)")
c.write({'vat': '1234567890', 'l10n_tr_tax_office_id': env['l10n_tr.tax.office'].search([], limit=1).id, 'atlas_duzenleyen_tip': 'mukellef'})
mart.action_xml()
x = etree.fromstring(mart.xml_dosya.content)
ok(x.get('kodVer') == c.atlas_kdv1_kodver and x.findtext('.//vergiNo') == '1234567890' and x.findtext('.//odenmesiGerekenKDV') == '18400.00'
   and x.findtext('.//kismiTevkifat/islemTuru') == '602' and mart.xml_adi == 'KDV1_203103.xml', "KDV1 XML: sürüm, VKN, tevkifat, ödenecek")
bs.action_xml(); xb = etree.fromstring(bs.xml_dosya.content)
ok(len(xb.findall('.//bildirim')) == 3 and xb.findtext('.//bildirim/belgeSayisi') == '1', "Form Bs XML: 3 bildirim")
ok(mart._xlsx()[:2] == b'PK', "Excel çıktısı")
html = env['ir.actions.report']._render_qweb_html('atlas_beyanname.report_beyanname', mart.ids)[0]
import re as _re
ok('Kısmi Tevkifat'.encode() in html and _re.search(rb'18[.,]400', html), "PDF çalışma kâğıdı")
try:
    with env.cr.savepoint(): B.create({'tip': 'kdv1', 'yil': 2031, 'ay': '3'}); env.flush_all(); cift = False
except Exception: cift = True
ok(cift, "aynı dönem için ikinci KDV1 açılamaz")
env.cr.rollback(); print("(geri alındı)")
