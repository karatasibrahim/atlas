import base64
import io
import json
import zipfile
from datetime import date
from unittest.mock import patch
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.addons.atlas_mysoft.models import mysoft_api as ms
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
env = env(context=dict(env.context, atlas_mysoft_ayni_islem=True))
ms.TOKEN_ONBELLEK.clear()


class Yanit:
    def __init__(self, veri=None, kod=200, icerik=None, tur='application/json'):
        self.status_code = kod
        self._veri = veri
        self.content = icerik if icerik is not None else json.dumps(veri or {}).encode()
        self.text = self.content.decode('utf-8', 'ignore') if isinstance(self.content, bytes) else str(self.content)
        self.headers = {'Content-Type': tur}

    def json(self):
        if self._veri is None:
            raise ValueError('json değil')
        return self._veri


def zip_yap(ad, icerik):
    t = io.BytesIO()
    with zipfile.ZipFile(t, 'w') as z:
        z.writestr(ad, icerik)
    return t.getvalue()


UBL = '''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ProfileID>TICARIFATURA</cbc:ProfileID><cbc:ID>TED2026000000123</cbc:ID><cbc:UUID>AAAA1111-2222-3333-4444-555566667777</cbc:UUID>
 <cbc:IssueDate>2026-10-01</cbc:IssueDate><cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyIdentification><cbc:ID schemeID="VKN">9990001119</cbc:ID></cac:PartyIdentification>
 <cac:PartyName><cbc:Name>MYS Tedarikçi Ltd.</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>
 <cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="TRY">1080.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
 <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="C62">10</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="TRY">900.00</cbc:LineExtensionAmount>
  <cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator><cbc:Amount currencyID="TRY">100.00</cbc:Amount></cac:AllowanceCharge>
  <cac:TaxTotal><cbc:TaxAmount currencyID="TRY">180.00</cbc:TaxAmount><cac:TaxSubtotal><cbc:TaxableAmount currencyID="TRY">900</cbc:TaxableAmount>
   <cbc:TaxAmount currencyID="TRY">180</cbc:TaxAmount><cbc:Percent>20</cbc:Percent><cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name>
   <cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
  <cac:Item><cbc:Name>Rulman 6204</cbc:Name><cac:SellersItemIdentification><cbc:ID>RLM-6204</cbc:ID></cac:SellersItemIdentification></cac:Item>
  <cac:Price><cbc:PriceAmount currencyID="TRY">100.00</cbc:PriceAmount></cac:Price></cac:InvoiceLine>
</Invoice>'''

cagrilar = []
durumlar = {}
token_sayisi = [0]
gecersiz_token = set()


def sunucu(yontem, url, headers=None, json=None, params=None, timeout=None, data=None):
    yol = url.split('.tr', 1)[1]
    cagrilar.append({'yontem': yontem, 'yol': yol, 'json': json, 'params': params or {}, 'data': data, 'headers': headers or {}})
    if yol == '/oauth/token':
        if data.get('client_secret') != 'GIZLI':
            return Yanit({'error': 'Authentication Error', 'error_description': 'Client bilgisi hatalı'}, 500)
        token_sayisi[0] += 1
        return Yanit({'access_token': f'TOKEN{token_sayisi[0]}', 'token_type': 'bearer', 'expires_in': 300})
    if headers.get('Authorization', '').split(' ')[-1] in gecersiz_token:
        gecersiz_token.clear()
        return Yanit({'Message': 'Authorization has been denied for this request.'}, 401)
    if yol == '/api/GeneralCard/getUserCompanyInfo':
        return Yanit({'success': True, 'data': {'companyTitle': 'ATLAS TEST A.Ş.', 'vknTckn': '1234567890'}})
    if yol == '/api/GeneralCard/getGibAccountModel':
        if params['vknTckn'] == '1112223339':
            return Yanit({'success': True, 'data': {'vknTckn': '1112223339', 'title': 'MYS MÜŞTERİ',
                                                    'aliases': [{'alias': 'urn:mail:defaultgb@musteri.com', 'type': 'GB'},
                                                                {'alias': 'urn:mail:defaultpk@musteri.com', 'type': 'PK'}]}})
        return Yanit({'success': True, 'data': None})
    if yol == '/api/InvoiceOutbox/invoiceOutbox':
        if json['invoiceAccount']['accountName'] == 'MYS Hatalı':
            return Yanit({'success': False, 'message': 'Alıcı VKN geçersiz'})
        durumlar[json['ettn']] = 'GİB\'E GÖNDERİLDİ'
        return Yanit({'success': True, 'message': 'Kaydedildi', 'data': {'invoiceETTN': json['ettn'], 'docNo': json.get('docNo') or 'MYF2026000000001'}})
    if yol == '/api/InvoiceOutbox/getInvoiceOutboxStatusChanged':
        return Yanit({'success': True, 'data': [{'id': i + 1, 'invoiceETTN': e, 'statusName': d, 'statusDescription': 'Alıcı sistem yanıtı: Hatalı adres'
                      if 'HATA' in d else ''} for i, (e, d) in enumerate(durumlar.items())]})
    if yol == '/api/InvoiceOutbox/getInvoiceOutboxStatus':
        return Yanit({'success': True, 'data': {'invoiceETTN': params['invoiceETTN'], 'status': durumlar.get(params['invoiceETTN'].upper(), 'BAŞARILI')}})
    if yol == '/api/InvoiceOutbox/getInvoiceOutboxPdfAsZip':
        return Yanit(icerik=zip_yap('fatura.pdf', b'%PDF-1.4 mysoft'), tur='application/zip')
    if yol == '/api/InvoiceOutbox/cancelEArchiveInvoice':
        return Yanit({'success': True, 'message': 'İptal edildi'})
    if yol == '/api/InvoiceInbox/getNewInvoiceInboxWithHeaderInfoList':
        if json['afterValue'] >= 501:
            return Yanit({'success': True, 'data': []})
        return Yanit({'success': True, 'data': [{'id': 501, 'invoiceETTN': 'aaaa1111-2222-3333-4444-555566667777', 'docNo': 'TED2026000000123',
                                                 'docDate': '2026-10-01T00:00:00', 'senderVknTckn': '9990001119', 'senderName': 'MYS Tedarikçi Ltd.',
                                                 'profile': 'TICARIFATURA', 'invoiceType': 'SATIS', 'taxAmount': 180, 'payableAmount': 1080,
                                                 'currencyCode': 'TRY'}]})
    if yol == '/api/InvoiceInbox/getInvoiceInboxUBLXMLAsZip':
        return Yanit(icerik=zip_yap('fatura.xml', UBL.encode()), tur='application/octet-stream')
    if yol in ('/api/InvoiceInbox/invoiceInboxSavedByCustomer', '/api/InvoiceInbox/acceptInvoice', '/api/InvoiceInbox/denyInvoice'):
        return Yanit({'success': True})
    if yol == '/api/DespatchOutbox/despatchOutbox':
        return Yanit({'success': True, 'data': {'despatchETTN': json['ettn'], 'docNo': json.get('docNo')}})
    return Yanit({'success': False, 'message': f'Bilinmeyen uç: {yol}'}, 404)


def son(yol):
    return next(c for c in reversed(cagrilar) if c['yol'] == yol)


sirket = env.company
sirket.write({'atlas_ebelge_aktif': True, 'atlas_mysoft_aktif': True, 'atlas_mysoft_ortam': 'test', 'atlas_mysoft_client_id': 'CID-GECERSIZ',
              'atlas_mysoft_client_secret': 'YANLIS', 'atlas_mysoft_gb_etiket': 'urn:mail:defaultgb@atlas.com.tr', 'vat': '1234567890',
              'atlas_mysoft_otomatik': True, 'atlas_eirsaliye': True})
with patch.object(ms.requests, 'request', side_effect=sunucu), \
        patch.object(ms.requests, 'post', side_effect=lambda url, **kw: sunucu('POST', url, **kw)):
    try:
        with env.cr.savepoint(): sirket.action_atlas_mysoft_test(); guid = True
    except UserError as e: guid = 'GUID' not in str(e)
    ok(not guid and not cagrilar, "GUID olmayan Client Id istek gönderilmeden reddedildi")
    sirket.atlas_mysoft_client_id = '56d8a57f-1691-47da-850a-79b860a7011f'
    try:
        with env.cr.savepoint(): sirket.action_atlas_mysoft_test(); baglandi = True
    except UserError as e: baglandi = False; hata_metni = str(e)
    ok(not baglandi and 'Client bilgisi hatalı' in hata_metni, "yanlış client secret: token hatası anlaşılır mesajla")
    sirket.atlas_mysoft_client_secret = 'GIZLI'
    sonuc = sirket.action_atlas_mysoft_test()
    tok = son('/oauth/token')
    ok('ATLAS TEST' in sonuc['params']['message'] and tok['data']['grant_type'] == 'client_credentials' and tok['data']['client_id'] == '56d8a57f-1691-47da-850a-79b860a7011f',
       "bağlantı testi: client_credentials ile token alındı")
    ok(son('/api/GeneralCard/getUserCompanyInfo')['headers']['Authorization'] == 'Bearer TOKEN1', "istekte Bearer token")
    sirket.action_atlas_mysoft_test()
    ok(token_sayisi[0] == 1, "token 5 dakika önbellekte tutuldu")
    gecersiz_token.add('TOKEN1')
    sirket.action_atlas_mysoft_test()
    ok(token_sayisi[0] == 2, "401 yanıtında token yenilendi ve istek tekrarlandı")
    log = env['atlas.mysoft.log'].search([('islem', '=', 'Token')], limit=1)
    ok(log and 'GIZLI' not in (log.istek or '') and 'TOKEN' not in (log.yanit or ''), "günlükte gizli anahtar ve token maskeli")

    # Mükellef sorgusu ve e-Fatura gönderimi
    mus = env['res.partner'].create({'name': 'MYS Müşteri A.Ş.', 'is_company': True, 'vat': '1112223339', 'street': 'Atatürk Cd. 5',
                                     'city': 'Kadıköy', 'state_id': env['res.country.state'].search([('country_id.code', '=', 'TR'), ('name', 'ilike', 'İstanbul')], limit=1).id,
                                     'country_id': env.ref('base.tr').id, 'email': 'muhasebe@musteri.com', 'atlas_cari_tipi': 'alici'})
    kdv20 = env['account.tax'].search([('type_tax_use', '=', 'sale'), ('amount', '=', 20), ('amount_type', '=', 'percent'),
                                       ('company_id', '=', sirket.id)], limit=1)
    urun = env['product.product'].create({'name': 'MYS Pompa', 'default_code': 'PMP-01', 'list_price': 1000})
    f = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 10, 5), 'narration': '<p>Teşekkürler</p>',
                                    'invoice_line_ids': [Command.create({'product_id': urun.id, 'quantity': 3, 'price_unit': 1000, 'discount': 10,
                                                                         'tax_ids': [Command.set(kdv20.ids)]})]})
    ok(f.atlas_ebelge_tipi == 'earsiv', "sorgu öncesi: mükellef işaretli değil → e-Arşiv")
    f.action_post()
    ok(mus.atlas_efatura_mukellef and mus.atlas_efatura_etiket == 'urn:mail:defaultpk@musteri.com' and mus.atlas_efatura_kontrol,
       "onayda GİB mükellef sorgusu: PK etiketi bulundu")
    ok(f.atlas_ebelge_tipi == 'efatura' and f.atlas_ebelge_senaryo == 'TICARIFATURA' and f.name.startswith('ATL'), f"e-Fatura'ya döndü, seri ATL: {f.name}")
    ok(f.atlas_mysoft_durum == 'kuyrukta' and f.atlas_ettn, "onaylanan fatura gönderim kuyruğunda, ETTN var")
    env['account.move']._cron_atlas_mysoft()
    g = son('/api/InvoiceOutbox/invoiceOutbox')['json']
    satir = g['invoiceDetail'][0]
    ok(g['eDocumentType'] == 'EFATURA' and g['profile'] == 'TICARIFATURA' and g['invoiceType'] == 'SATIS' and g['ettn'] == f.atlas_ettn
       and g['docNo'] == f.name, "gövde: e-Fatura, ticari, satış, ETTN ve Atlas numarası")
    ok(g['pkAlias'] == 'urn:mail:defaultpk@musteri.com' and g['gbAlias'] == 'urn:mail:defaultgb@atlas.com.tr' and g['invoiceAccount']['vknTckn'] == '1112223339',
       "gövde: alıcı PK, gönderici GB ve VKN")
    ok(satir['qty'] == 3 and satir['unitPriceTra'] == 1000 and satir['amtTra'] == 3000 and satir['discAmtTra'] == 300 and satir['taxableAmtTra'] == 2700
       and satir['vatRate'] == 20 and satir['amtVatTra'] == 540 and satir['unitCode'] == 'C62' and satir['productCode'] == 'PMP-01',
       "satır: miktar, birim fiyat, iskonto, matrah, KDV, birim kodu")
    hes = g['invoiceCalculation']
    ok(hes['taxExclusiveAmount'] == 2700 and hes['taxInclusiveAmount'] == 3240 and hes['payableAmount'] == 3240 and g['isManuelCalculation'],
       "toplamlar: matrah 2.700, KDV dahil 3.240")
    ok(g['tax'][0]['taxSubTotal'][0]['percent'] == 20 and g['tax'][0]['taxAmount'] == 540 and g['notes'][0]['note'] == 'Teşekkürler', "vergi özeti ve not")
    ok(f.atlas_mysoft_durum == 'gonderildi' and f.atlas_mysoft_belge_no == f.name, "gönderildi")
    ok(not son('/api/InvoiceOutbox/invoiceOutbox')['json'].get('tenantIdentifierNumber'), "firma anahtarında tenant VKN gönderilmez")
    try:
        with env.cr.savepoint(): f.button_draft(); taslak = True
    except UserError: taslak = False
    ok(not taslak, "GİB'e gönderilmiş fatura taslağa alınamaz")

    # e-Arşiv, hata ve durum takibi
    bireysel = env['res.partner'].create({'name': 'Ahmet Bireysel', 'vat': '12345678950', 'city': 'Ankara', 'country_id': env.ref('base.tr').id})
    a = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': bireysel.id, 'invoice_date': date(2026, 10, 5),
                                    'invoice_line_ids': [Command.create({'name': 'Hizmet', 'quantity': 1, 'price_unit': 500, 'tax_ids': [Command.set(kdv20.ids)]})]})
    a.action_post()
    hatali_p = env['res.partner'].create({'name': 'MYS Hatalı', 'vat': '98765432150'})
    h = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': hatali_p.id, 'invoice_date': date(2026, 10, 5),
                                    'invoice_line_ids': [Command.create({'name': 'X', 'quantity': 1, 'price_unit': 10, 'tax_ids': [Command.set(kdv20.ids)]})]})
    h.action_post()
    env['account.move']._cron_atlas_mysoft()
    ga = next(c['json'] for c in reversed(cagrilar) if c['yol'] == '/api/InvoiceOutbox/invoiceOutbox' and c['json']['ettn'] == a.atlas_ettn)
    ok(a.atlas_ebelge_tipi == 'earsiv' and ga['eDocumentType'] == 'EARSIVFATURA' and ga['profile'] == 'EARSIVFATURA' and ga['senderType'] == 'ELEKTRONIK'
       and a.name.startswith('ARS') and ga['pkAlias'] is None, "e-Arşiv gövdesi ve ARS serisi")
    ok(h.atlas_mysoft_durum == 'hata' and 'Alıcı VKN geçersiz' in h.atlas_mysoft_mesaj, "MySoft success=false: fatura hata durumunda, mesaj kayıtlı")
    durumlar[f.atlas_ettn] = 'BAŞARILI'
    durumlar[a.atlas_ettn] = 'HATA - ALICI SİSTEM YANITI'
    env['account.move']._atlas_durum_toplu(sirket)
    ok(f.atlas_mysoft_durum == 'basarili' and f.atlas_mysoft_durum_metin == 'BAŞARILI', "durum değişikliği: başarılı")
    ok(a.atlas_mysoft_durum == 'hata' and 'Hatalı adres' in (a.atlas_mysoft_mesaj or '') and a.activity_ids, "durum değişikliği: hata + sorumluya aktivite")
    durumlar[a.atlas_ettn] = 'BAŞARILI'
    a.action_atlas_mysoft_durum()
    ok(a.atlas_mysoft_durum == 'basarili', "tek fatura durum sorgusu")
    sonuc = f.action_atlas_mysoft_pdf()
    ek = env['ir.attachment'].search([('res_model', '=', 'account.move'), ('res_id', '=', f.id), ('mimetype', '=', 'application/pdf')], limit=1)
    ok(ek and ek.raw.content.startswith(b'%PDF') and sonuc['url'].startswith('/web/content/'), "PDF zip'ten çıkarılıp eklendi")
    a.action_atlas_mysoft_iptal()
    ip = son('/api/InvoiceOutbox/cancelEArchiveInvoice')['params']
    ok(a.atlas_mysoft_durum == 'iptal' and ip['invoiceETTN'] == a.atlas_ettn and ip['cancelType'] == 'PORTAL' and a.payment_state == 'reversed',
       "e-Arşiv iptali: GİB'de iptal, muhasebe ters kayıtla kapandı")
    try:
        with env.cr.savepoint(): f.action_atlas_mysoft_iptal(); efat_iptal = True
    except UserError: efat_iptal = False
    ok(not efat_iptal, "e-Fatura iptal edilemez (yalnız e-Arşiv)")

    # Tevkifat ve iade
    tevk = env['account.tax'].search([('amount_type', '=', 'group'), ('type_tax_use', '=', 'sale'), ('name', 'ilike', 'Tevkifatlı 5/10'),
                                      ('company_id', '=', sirket.id)], limit=1)
    tevk.atlas_gib_kod_id = env['atlas.gib.kod'].search([('kod', '=', '601')])
    t = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 10, 5),
                                    'invoice_line_ids': [Command.create({'name': 'Proje hizmeti', 'quantity': 1, 'price_unit': 1000, 'tax_ids': [Command.set(tevk.ids)]})]})
    t.action_post(); t.action_atlas_mysoft_gonder()
    gt = son('/api/InvoiceOutbox/invoiceOutbox')['json']
    st = gt['invoiceDetail'][0]
    ok(gt['invoiceType'] == 'TEVKIFAT' and st['withholdingTaxTypeCode'] == '601' and st['withholdingTaxPercentage'] == 50
       and st['withholdingTaxAmount'] == 100 and st['amtVatTra'] == 200, "tevkifat: kod 601, %50, tevkif 100")
    ok(gt['invoiceCalculation']['taxInclusiveAmount'] == 1200 and gt['invoiceCalculation']['payableAmount'] == 1100, "tevkifatta ödenecek 1.100")
    tevk.atlas_gib_kod_id = False
    t2 = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 10, 5),
                                     'invoice_line_ids': [Command.create({'name': 'Y', 'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.set(tevk.ids)]})]})
    t2.action_post()
    try:
        with env.cr.savepoint(): t2._atlas_mysoft_json(); kodsuz = True
    except UserError: kodsuz = False
    ok(not kodsuz, "tevkifat kodu atanmamış vergi gönderilmez")
    sifir = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': mus.id, 'invoice_date': date(2026, 10, 5),
                                        'invoice_line_ids': [Command.create({'name': 'Z', 'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.clear()]})]})
    sifir.action_post()
    ok(sifir._atlas_mysoft_json()['invoiceDetail'][0]['taxExemptionReasonCode'] == '351', "KDV'siz satış satırına 351 kodu")

    # İş ortağı anahtarı: tenant VKN
    sirket.atlas_mysoft_anahtar_tipi = 'is_ortagi'
    mus._atlas_mukellef_sorgula(sirket)
    ok(son('/api/GeneralCard/getGibAccountModel')['params'].get('tenantIdentifierNumber') == '1234567890', "iş ortağı anahtarında tenantIdentifierNumber gönderildi")
    sirket.atlas_mysoft_anahtar_tipi = 'firma'

    # Gelen e-faturalar
    G = env['atlas.mysoft.gelen']
    yeniler = G._gelenleri_al(sirket)
    G._gelenleri_al(sirket)
    gelen = G.search([('ettn', '=', 'AAAA1111-2222-3333-4444-555566667777')])
    ok(len(yeniler) == 1 and len(gelen) == 1 and gelen.belge_no == 'TED2026000000123' and gelen.tutar == 1080 and gelen.gonderen_vkn == '9990001119'
       and sirket.atlas_mysoft_gelen_imlec == 501, "gelen fatura başlığı alındı, imleç ilerledi, tekrar alınmadı")
    gelen.action_fatura_olustur()
    alis = gelen.fatura_id
    satir = alis.invoice_line_ids
    ok(alis.move_type == 'in_invoice' and alis.ref == 'TED2026000000123' and alis.partner_id.vat == '9990001119' and alis.atlas_ettn == gelen.ettn,
       "UBL'den taslak alış faturası: tedarikçi oluşturuldu, ETTN")
    ok(satir.quantity == 10 and satir.price_unit == 100 and satir.discount == 10 and satir.tax_ids.amount == 20 and abs(alis.amount_total - 1080) < 0.01,
       f"alış satırı: 10 × 100, %10 iskonto, KDV %20 → {alis.amount_total}")
    ok(gelen.durum == 'aktarildi' and son('/api/InvoiceInbox/invoiceInboxSavedByCustomer')['params']['invoiceETTN'] == gelen.ettn, "MySoft'a 'işlendi' bildirildi")
    gelen.action_kabul()
    ok(son('/api/InvoiceInbox/acceptInvoice')['params']['invoiceETTN'] == gelen.ettn, "ticari fatura kabul edildi")

    # e-İrsaliye
    depo = env['stock.warehouse'].search([('company_id', '=', sirket.id)], limit=1)
    stok_urun = env['product.product'].create({'name': 'MYS Kutu', 'is_storable': True, 'default_code': 'KT-1'})
    env['stock.quant']._update_available_quantity(stok_urun, depo.lot_stock_id, 10)
    arac = env['atlas.irsaliye.plaka'].create({'name': '34ABC123', 'tip': 'arac'})
    sofor = env['atlas.irsaliye.sofor'].create({'ad': 'Mehmet', 'soyad': 'Yılmaz', 'tckn': '98765432150'})
    p = env['stock.picking'].create({'picking_type_id': depo.out_type_id.id, 'partner_id': mus.id, 'atlas_arac_id': arac.id,
                                     'atlas_sofor_ids': [Command.set(sofor.ids)],
                                     'move_ids': [Command.create({'product_id': stok_urun.id, 'product_uom_qty': 4, 'location_id': depo.lot_stock_id.id,
                                                                  'location_dest_id': env.ref('stock.stock_location_customers').id})]})
    p.action_confirm(); p.move_ids.quantity = 4; p.button_validate()
    ok(p.state == 'done' and p.atlas_mysoft_durum == 'kuyrukta' and p.atlas_ettn, "tamamlanan sevkiyat e-İrsaliye kuyruğunda")
    env['stock.picking']._cron_atlas_mysoft()
    gi = son('/api/DespatchOutbox/despatchOutbox')['json']
    ok(gi['eDespatchType'] == 'SEVK' and gi['lisancePlate'] == '34ABC123' and gi['driverIdentifierNumber'] == '98765432150' and gi['driverSurname'] == 'Yılmaz'
       and gi['deliveryAccount']['identifierNumber'] == '1112223339' and gi['despatchDetail'][0]['qty'] == 4 and gi['docNo'] == p.atlas_irsaliye_no,
       "e-İrsaliye gövdesi: plaka, şoför, alıcı VKN, miktar, irsaliye no")
    ok(p.atlas_mysoft_durum == 'gonderildi', "e-İrsaliye gönderildi")
ok(env['atlas.mysoft.log'].search_count([('company_id', '=', sirket.id)]) > 10, "tüm istekler günlüğe yazıldı")
env.cr.rollback(); print("(geri alındı)")
