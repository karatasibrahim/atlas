import base64
import json
import logging

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .mysoft_api import anahtar_bul, liste_bul, sadece_rakam, zipten_dosya

_logger = logging.getLogger(__name__)

NS = {'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
      'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'}


def _sayi(deger):
    try:
        return float(str(deger).replace(',', '.'))
    except (TypeError, ValueError):
        return 0.0


class AtlasMysoftGelen(models.Model):
    _name = 'atlas.mysoft.gelen'
    _description = 'Gelen e-Fatura'
    _inherit = ['mail.thread']
    _order = 'tarih desc, id desc'
    _rec_name = 'belge_no'

    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company, index=True)
    ettn = fields.Char(string='ETTN', required=True, index=True)
    belge_no = fields.Char(string='Fatura No')
    tarih = fields.Date(string='Fatura Tarihi')
    gonderen_vkn = fields.Char(string='Gönderen VKN/TCKN', index=True)
    gonderen_ad = fields.Char(string='Gönderen')
    partner_id = fields.Many2one('res.partner', string='Tedarikçi', compute='_compute_partner_id', store=True, readonly=False)
    senaryo = fields.Char(string='Senaryo')
    fatura_tipi = fields.Char(string='Fatura Tipi')
    tutar = fields.Float(string='Ödenecek Tutar', digits=(16, 2))
    para_birimi = fields.Char(string='Para Birimi')
    durum = fields.Selection([('yeni', 'Yeni'), ('aktarildi', 'Faturaya Aktarıldı'), ('kabul', 'Kabul Edildi'), ('red', 'Reddedildi')],
                             string='Durum', default='yeni', required=True, tracking=True, index=True)
    xml_dosya = fields.Binary(string='UBL XML', attachment=True)
    xml_adi = fields.Char()
    pdf_dosya = fields.Binary(string='PDF', attachment=True)
    pdf_adi = fields.Char()
    fatura_id = fields.Many2one('account.move', string='Alış Faturası', readonly=True)
    ham = fields.Text(string='MySoft Kaydı', readonly=True)
    red_nedeni = fields.Char(string='Red Nedeni', readonly=True)

    _ettn_uniq = models.Constraint('UNIQUE(company_id, ettn)', 'Bu fatura zaten alınmış.')

    @api.depends('gonderen_vkn')
    def _compute_partner_id(self):
        for g in self:
            if g.gonderen_vkn and not g.partner_id:
                g.partner_id = self.env['res.partner'].search([('vat', 'ilike', g.gonderen_vkn), ('parent_id', '=', False)], limit=1)

    # -------------------------------------------------------------------------
    # MySoft'tan alma
    # -------------------------------------------------------------------------

    @api.model
    def _kaydet(self, company, oge):
        ettn = anahtar_bul(oge, [r'(invoice)?ettn', r'uuid'])
        if not ettn:
            return self.browse()
        ettn = str(ettn).upper()
        mevcut = self.search([('company_id', '=', company.id), ('ettn', '=', ettn)], limit=1)
        if mevcut:
            return mevcut
        tarih = anahtar_bul(oge, [r'docDate', r'issueDate', r'invoiceDate', r'.*Date'])
        return self.create({
            'company_id': company.id, 'ettn': ettn,
            'belge_no': anahtar_bul(oge, [r'docNo', r'invoiceNo', r'invoiceNumber', r'documentNo']),
            'tarih': str(tarih)[:10] if tarih else False,
            'gonderen_vkn': sadece_rakam(str(anahtar_bul(oge, [r'(sender|supplier|account)?(Vkn|Tckn|VknTckn|IdentifierNumber)', r'vknTckn']) or '')),
            'gonderen_ad': anahtar_bul(oge, [r'(sender|supplier|account)(Name|Title|PartyName)', r'.*Name']),
            'senaryo': anahtar_bul(oge, [r'profile', r'profileId', r'scenario']),
            'fatura_tipi': anahtar_bul(oge, [r'invoiceType', r'invoiceTypeCode', r'type']),
            'tutar': _sayi(anahtar_bul(oge, [r'payableAmount(Tra)?', r'.*TotalAmount.*', r'.*Amount'])),
            'para_birimi': anahtar_bul(oge, [r'currencyCode', r'currency']),
            'ham': json.dumps(oge, ensure_ascii=False, indent=1, default=str)[:20000],
        })

    @api.model
    def _cron_gelen(self):
        for company in self.env['res.company'].search([('atlas_mysoft_aktif', '=', True)]):
            try:
                with self.env.cr.savepoint():
                    self._gelenleri_al(company)
            except UserError as hata:
                _logger.warning('MySoft gelen fatura alınamadı (%s): %s', company.name, hata)

    @api.model
    def _gelenleri_al(self, company):
        """Yeni gelen e-faturaları (başlık bilgisiyle) alır; imleç şirkette saklanır."""
        Api = self.env['atlas.mysoft.api']
        imlec = company.atlas_mysoft_gelen_imlec or 0
        yeniler = self.browse()
        for _sayfa in range(20):
            yanit = Api._istek(company, 'POST', '/api/InvoiceInbox/getNewInvoiceInboxWithHeaderInfoList',
                               {'afterValue': imlec, 'limit': 100}, islem='Gelen faturalar')
            liste = liste_bul(yanit) or []
            for oge in liste:
                if isinstance(oge, dict):
                    yeniler |= self._kaydet(company, oge)
            ids = [int(anahtar_bul(o, [r'id', r'rowId', r'.*Id']) or 0) for o in liste if isinstance(o, dict)]
            yeni_imlec = max(ids or [imlec])
            if not liste or yeni_imlec <= imlec:
                break
            imlec = yeni_imlec
            if len(liste) < 100:
                break
        company.sudo().write({'atlas_mysoft_gelen_imlec': imlec, 'atlas_mysoft_gelen_kontrol': fields.Datetime.now()})
        return yeniler

    def action_gelenleri_al(self):
        yeniler = self._gelenleri_al(self.env.company)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('%s yeni gelen fatura alındı.', len(yeniler)),
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def _dosya_al(self, yol, uzantilar):
        self.ensure_one()
        icerik = self.env['atlas.mysoft.api']._istek(self.company_id, 'GET', yol, params={'invoiceETTN': self.ettn}, ikili=True,
                                                     islem='Gelen fatura dosyası', kayit=self)
        return zipten_dosya(icerik, uzantilar)

    def action_xml_al(self):
        for g in self:
            ad, xml = g._dosya_al('/api/InvoiceInbox/getInvoiceInboxUBLXMLAsZip', ('.xml',))
            g.write({'xml_dosya': base64.b64encode(xml).decode(), 'xml_adi': ad or f'{g.ettn}.xml'})
            g._xml_ozet_doldur(xml)
        return True

    def action_pdf_al(self):
        self.ensure_one()
        if not self.pdf_dosya:
            ad, pdf = self._dosya_al('/api/InvoiceInbox/getInvoiceInboxPdfAsZip', ('.pdf',))
            self.write({'pdf_dosya': base64.b64encode(pdf).decode(), 'pdf_adi': ad or f'{self.ettn}.pdf'})
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': f'/web/content/atlas.mysoft.gelen/{self.id}/pdf_dosya/{self.pdf_adi}'}

    # -------------------------------------------------------------------------
    # UBL'den alış faturası
    # -------------------------------------------------------------------------

    @staticmethod
    def _xml_coz(xml):
        try:
            return etree.fromstring(xml)
        except etree.XMLSyntaxError as hata:
            raise UserError('UBL XML okunamadı: %s' % hata) from hata

    def _xml_ozet_doldur(self, xml):
        kok = self._xml_coz(xml)
        x = lambda yol: (kok.xpath(yol, namespaces=NS) or [None])[0]  # noqa: E731
        tedarikci = x('cac:AccountingSupplierParty/cac:Party')
        vkn = tedarikci.xpath("cac:PartyIdentification/cbc:ID[@schemeID='VKN' or @schemeID='TCKN']/text()", namespaces=NS) \
            if tedarikci is not None else []
        ad = tedarikci.xpath('cac:PartyName/cbc:Name/text()', namespaces=NS) if tedarikci is not None else []
        if not ad and tedarikci is not None:
            ad = [' '.join(tedarikci.xpath('cac:Person/cbc:FirstName/text() | cac:Person/cbc:FamilyName/text()', namespaces=NS))]
        vals = {
            'belge_no': self.belge_no or x('cbc:ID/text()'),
            'tarih': self.tarih or x('cbc:IssueDate/text()'),
            'senaryo': self.senaryo or x('cbc:ProfileID/text()'),
            'fatura_tipi': self.fatura_tipi or x('cbc:InvoiceTypeCode/text()'),
            'para_birimi': x('cbc:DocumentCurrencyCode/text()') or self.para_birimi,
            'tutar': _sayi(x('cac:LegalMonetaryTotal/cbc:PayableAmount/text()')) or self.tutar,
        }
        if vkn:
            vals['gonderen_vkn'] = vkn[0]
        if ad and ad[0]:
            vals['gonderen_ad'] = ad[0]
        self.write(vals)
        return kok

    def _vergi_bul(self, oran):
        Tax = self.env['account.tax'].with_company(self.company_id)
        vergiler = Tax.search([('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent'), ('amount', '=', oran),
                               ('company_id', 'parent_of', self.company_id.id), ('price_include', '=', False)], limit=1)
        return vergiler

    def action_fatura_olustur(self):
        """UBL XML'den taslak alış faturası (veya iade faturasından alış iadesi) oluşturur."""
        for g in self:
            if g.fatura_id:
                continue
            if not g.xml_dosya:
                g.action_xml_al()
            kok = g._xml_ozet_doldur(g.xml_dosya.content)
            partner = g.partner_id
            if not partner:
                partner = self.env['res.partner'].create({'name': g.gonderen_ad or g.gonderen_vkn, 'vat': g.gonderen_vkn,
                                                          'is_company': len(g.gonderen_vkn or '') == 10, 'company_id': False})
                g.partner_id = partner
            para = self.env['res.currency'].search([('name', '=', g.para_birimi or 'TRY')], limit=1) or g.company_id.currency_id
            satirlar = []
            for satir in kok.xpath('cac:InvoiceLine', namespaces=NS):
                x = lambda yol, s=satir: (s.xpath(yol, namespaces=NS) or [None])[0]  # noqa: E731
                miktar = _sayi(x('cbc:InvoicedQuantity/text()')) or 1.0
                net = _sayi(x('cbc:LineExtensionAmount/text()'))
                fiyat = _sayi(x('cac:Price/cbc:PriceAmount/text()'))
                indirim = _sayi(x("cac:AllowanceCharge[cbc:ChargeIndicator='false']/cbc:Amount/text()"))
                oran = _sayi(x("cac:TaxTotal/cac:TaxSubtotal[cac:TaxCategory/cac:TaxScheme/cbc:TaxTypeCode='0015']/cbc:Percent/text()")
                             or x('cac:TaxTotal/cac:TaxSubtotal/cbc:Percent/text()'))
                ad = x('cac:Item/cbc:Name/text()') or x('cbc:Note/text()') or '-'
                kod = x('cac:Item/cac:SellersItemIdentification/cbc:ID/text()')
                urun = self.env['product.product'].search(['|', ('default_code', '=', kod), ('barcode', '=', kod)], limit=1) if kod else False
                brut = fiyat * miktar
                vergi = g._vergi_bul(oran)
                satirlar.append(Command.create({
                    'name': f'[{kod}] {ad}' if kod and not urun else ad, 'product_id': urun.id if urun else False, 'quantity': miktar,
                    'price_unit': fiyat or (net / miktar if miktar else net),
                    'discount': round(indirim / brut * 100, 4) if brut and indirim else 0.0,
                    'tax_ids': [Command.set(vergi.ids)] if vergi else [Command.clear()],
                }))
            iade = (g.fatura_tipi or '').upper() == 'IADE'
            fatura = self.env['account.move'].with_company(g.company_id).create({
                'move_type': 'in_refund' if iade else 'in_invoice', 'partner_id': partner.id, 'invoice_date': g.tarih,
                'ref': g.belge_no, 'currency_id': para.id, 'invoice_line_ids': satirlar, 'atlas_ettn': g.ettn,
            })
            fatura.message_post(body=self.env._('MySoft gelen e-faturadan oluşturuldu (ETTN %s).', g.ettn),
                                attachments=[(g.xml_adi or f'{g.ettn}.xml', g.xml_dosya.content)])
            fark = abs(fatura.amount_total - g.tutar) if g.tutar else 0
            if fark > 0.05:
                fatura.message_post(body=self.env._('Dikkat: e-faturadaki ödenecek tutar %(e)s, oluşan faturada %(f)s. Vergi ve satırları kontrol edin.',
                                                    e=g.tutar, f=fatura.amount_total))
            g.write({'fatura_id': fatura.id, 'durum': 'aktarildi'})
            try:
                self.env['atlas.mysoft.api']._istek(g.company_id, 'GET', '/api/InvoiceInbox/invoiceInboxSavedByCustomer',
                                                    params={'invoiceETTN': g.ettn}, islem='Gelen fatura işlendi', kayit=g)
            except UserError as hata:
                g.message_post(body=self.env._('MySoft\'a "işlendi" bildirilemedi: %s', hata))
        if len(self) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': self.fatura_id.id, 'view_mode': 'form'}
        return True

    def action_kabul(self):
        for g in self:
            if (g.senaryo or '').upper() != 'TICARIFATURA':
                raise UserError(self.env._('Yalnız ticari faturalar kabul/red edilebilir.'))
            self.env['atlas.mysoft.api']._istek(g.company_id, 'GET', '/api/InvoiceInbox/acceptInvoice',
                                                params={'invoiceETTN': g.ettn}, islem='Gelen fatura kabul', kayit=g)
            g.durum = 'kabul' if not g.fatura_id else g.durum
            g.message_post(body=self.env._('Fatura kabul edildi.'))
        return True

    def action_red_sihirbaz(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.mysoft.gelen.red', 'view_mode': 'form', 'target': 'new',
                'context': {'default_gelen_id': self.id}, 'name': self.env._('Faturayı Reddet')}

    def action_red(self, neden=None):
        for g in self:
            if (g.senaryo or '').upper() != 'TICARIFATURA':
                raise UserError(self.env._('Yalnız ticari faturalar kabul/red edilebilir.'))
            if g.fatura_id and g.fatura_id.state == 'posted':
                raise UserError(self.env._('Muhasebeleşmiş fatura reddedilemez.'))
            neden = neden or self.env.context.get('red_nedeni') or self.env._('Fatura içeriği uygun değil')
            self.env['atlas.mysoft.api']._istek(g.company_id, 'GET', '/api/InvoiceInbox/denyInvoice',
                                                params={'invoiceETTN': g.ettn, 'rejectReason': neden}, islem='Gelen fatura red', kayit=g)
            g.write({'durum': 'red', 'red_nedeni': neden})
            if g.fatura_id and g.fatura_id.state == 'draft':
                g.fatura_id.button_cancel()
        return True


class AtlasMysoftGelenRed(models.TransientModel):
    _name = 'atlas.mysoft.gelen.red'
    _description = 'Gelen e-Faturayı Reddet'

    gelen_id = fields.Many2one('atlas.mysoft.gelen', required=True, ondelete='cascade')
    neden = fields.Char(string='Red Nedeni', required=True)

    def action_reddet(self):
        self.gelen_id.action_red(self.neden)
        return {'type': 'ir.actions.act_window_close'}
