import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .account_move import MYSOFT_DURUMLARI, durum_eslestir
from .mysoft_api import anahtar_bul, sadece_rakam, zipten_dosya


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    atlas_ettn = fields.Char(string='ETTN', copy=False, readonly=True, index='btree_not_null')
    atlas_mysoft_durum = fields.Selection(MYSOFT_DURUMLARI, string='e-İrsaliye Durumu', default='gonderilmedi', copy=False, tracking=True)
    atlas_mysoft_durum_metin = fields.Char(string='MySoft Durumu', copy=False, readonly=True)
    atlas_mysoft_mesaj = fields.Text(string='MySoft Mesajı', copy=False, readonly=True)
    atlas_mysoft_tarih = fields.Datetime(string='Gönderim Zamanı', copy=False, readonly=True)
    atlas_mysoft_gosterilsin = fields.Boolean(compute='_compute_atlas_mysoft_gosterilsin')

    @api.depends('picking_type_code', 'company_id.atlas_mysoft_aktif', 'company_id.atlas_eirsaliye', 'atlas_irsaliye_tipi')
    def _compute_atlas_mysoft_gosterilsin(self):
        for p in self:
            p.atlas_mysoft_gosterilsin = bool(p.picking_type_code == 'outgoing' and p.company_id.atlas_mysoft_aktif
                                              and p.company_id.atlas_eirsaliye and p.atlas_irsaliye_tipi != 'MATBUDAN')

    def _action_done(self):
        res = super()._action_done()
        for p in self.filtered(lambda x: x.atlas_mysoft_gosterilsin and x.state == 'done'):
            if not p.atlas_ettn:
                p.atlas_ettn = str(uuid.uuid4()).upper()
            if p.company_id.atlas_mysoft_otomatik and p.atlas_mysoft_durum == 'gonderilmedi':
                p.atlas_mysoft_durum = 'kuyrukta'
        return res

    @staticmethod
    def _atlas_adres(partner):
        return {
            'city': {'name': (partner.state_id.name or partner.city or '').upper() or None},
            'country': {'code': partner.country_id.code or 'TR', 'name': (partner.country_id.name or 'Türkiye').upper()},
            'streetName': ' '.join(filter(None, [partner.street, partner.street2])) or None,
            'citySubdivision': (partner.city if partner.state_id else None) or None,
            'postalCode': partner.zip or None,
            'telephone1': partner.phone or None,
            'email1': partner.email or None,
        }

    def _atlas_mysoft_json(self):
        self.ensure_one()
        alici = self.partner_id
        ticari = alici.commercial_partner_id
        company = self.company_id
        sevk = fields.Datetime.context_timestamp(self, self.atlas_fiili_sevk_tarihi or self.date_done or fields.Datetime.now())
        belge = fields.Datetime.context_timestamp(self, self.date_done or fields.Datetime.now())
        satirlar = []
        for move in self.move_ids.filtered(lambda m: m.state == 'done' and m.quantity):
            urun = move.product_id
            satirlar.append({'product': {'productCode': urun.default_code or urun.barcode or str(urun.id), 'productName': urun.display_name},
                             'unitCode': move.uom_id._atlas_birim_kodu(),
                             'qty': move.quantity, 'unitPriceTra': None, 'amtTra': None, 'currencyCode': company.currency_id.name})
        if not satirlar:
            raise UserError(self.env._('%s irsaliyesinde sevk edilen ürün yok.', self.name))
        sofor = self.atlas_sofor_ids[:1]
        govde = {
            'eDespatchType': 'SEVK',
            'ettn': self.atlas_ettn,
            'docDate': belge.strftime('%Y-%m-%dT00:00:00'),
            'docTime': belge.strftime('%Y-%m-%dT%H:%M:%S'),
            'actualReferalDate': sevk.strftime('%Y-%m-%dT00:00:00'),
            'actualReferalTime': sevk.strftime('%Y-%m-%dT%H:%M:%S'),
            'pkAlias': ticari.atlas_efatura_etiket or None,
            'gbAlias': company.atlas_mysoft_gb_etiket or None,
            'deliveryAccount': dict(self._atlas_adres(ticari), identifierNumber=sadece_rakam(ticari.vat), accountName=ticari.name,
                                    taxOffice=ticari.l10n_tr_tax_office_id.name if 'l10n_tr_tax_office_id' in ticari._fields
                                    and ticari.l10n_tr_tax_office_id else None),
            'deliveryAddress': self._atlas_adres(alici),
            'driverIdentifierNumber': sofor.tckn or self.atlas_sofor_tckn or None,
            'driverName': sofor.ad or None,
            'driverSurname': sofor.soyad or None,
            'driverPhone': sofor.telefon or None,
            'lisancePlate': (self.atlas_arac_id.name or self.atlas_arac_plaka or '').replace(' ', '') or None,
            'trailerNo': ', '.join(self.atlas_dorse_ids.mapped('name')) or None,
            'notes': [{'note': html2plaintext(self.note).strip()}] if self.note and html2plaintext(self.note).strip() else None,
            'despatchDetail': satirlar,
        }
        if self.atlas_tasiyici_id:
            t = self.atlas_tasiyici_id.commercial_partner_id
            govde['cargoAccount'] = dict(self._atlas_adres(t), identifierNumber=sadece_rakam(t.vat), accountName=t.name)
        if company.atlas_mysoft_numara == 'atlas':
            govde['docNo'] = self.atlas_irsaliye_no
        else:
            govde.update({'docNo': None, 'prefix': company.atlas_mysoft_eirsaliye_onek or None})
        if 'sale_id' in self._fields and self.sale_id:
            govde['orderList'] = [{'orderNo': self.sale_id.client_order_ref or self.sale_id.name,
                                   'orderDate': fields.Date.to_string(self.sale_id.date_order.date())}]
        return govde

    def _atlas_mysoft_gonder(self):
        Api = self.env['atlas.mysoft.api']
        for p in self:
            if not p.atlas_mysoft_gosterilsin or p.state != 'done':
                raise UserError(self.env._('%s gönderilecek bir e-İrsaliye değil (tamamlanmış çıkış ve e-İrsaliye ayarı gerekir).', p.name))
            if p.atlas_mysoft_durum in ('gonderildi', 'basarili', 'kabul'):
                raise UserError(self.env._('%s zaten gönderildi.', p.name))
            eksik = p._atlas_eirsaliye_eksikler()
            if eksik:
                raise UserError(self.env._('%(b)s e-İrsaliye eksik bilgi: %(e)s', b=p.name, e=', '.join(eksik)))
            simdi = fields.Datetime.now()
            try:
                yanit = Api._istek(p.company_id, 'POST', '/api/DespatchOutbox/despatchOutbox', p._atlas_mysoft_json(),
                                   islem='e-İrsaliye gönder', kayit=p)
            except UserError as hata:
                p.write({'atlas_mysoft_durum': 'hata', 'atlas_mysoft_mesaj': str(hata)[:2000], 'atlas_mysoft_tarih': simdi})
                p.message_post(body=self.env._('e-İrsaliye gönderilemedi: %s', hata))
                continue
            ettn = anahtar_bul(yanit, [r'(despatch)?ettn', r'uuid'])
            no = anahtar_bul(yanit, [r'docNo', r'despatchNo', r'documentNo'])
            vals = {'atlas_mysoft_durum': 'gonderildi', 'atlas_mysoft_tarih': simdi, 'atlas_mysoft_mesaj': False}
            if ettn:
                vals['atlas_ettn'] = str(ettn).upper()
            if no and not p.atlas_irsaliye_no:
                vals['atlas_irsaliye_no'] = no
            p.write(vals)
            p.message_post(body=self.env._('e-İrsaliye MySoft\'a iletildi. ETTN: %s', p.atlas_ettn))

    def action_atlas_mysoft_gonder(self):
        self._atlas_mysoft_gonder()
        if len(self) == 1 and self.atlas_mysoft_durum == 'hata':
            raise UserError(self.atlas_mysoft_mesaj)
        return True

    def action_atlas_mysoft_durum(self):
        for p in self.filtered('atlas_ettn'):
            yanit = self.env['atlas.mysoft.api']._istek(p.company_id, 'GET', '/api/DespatchOutbox/getDespatchOutboxStatus',
                                                        params={'despatchETTN': p.atlas_ettn}, islem='e-İrsaliye durum', kayit=p)
            metin = anahtar_bul(yanit, [r'.*status(Name|Desc|Description|Text)?', r'.*state'])
            yeni = durum_eslestir(metin)
            vals = {'atlas_mysoft_durum_metin': str(metin)[:200] if metin else False}
            if yeni:
                vals['atlas_mysoft_durum'] = yeni
            p.write(vals)
        return True

    def action_atlas_mysoft_pdf(self):
        self.ensure_one()
        icerik = self.env['atlas.mysoft.api']._istek(self.company_id, 'GET', '/api/DespatchOutbox/getDespatchOutboxPdfAsZip',
                                                     params={'despatchETTN': self.atlas_ettn}, ikili=True, islem='e-İrsaliye PDF', kayit=self)
        _ad, pdf = zipten_dosya(icerik, ('.pdf',))
        ek = self.env['ir.attachment'].create({'name': f'{self.atlas_irsaliye_no or self.name}.pdf'.replace('/', '-'), 'raw': pdf,
                                               'res_model': 'stock.picking', 'res_id': self.id, 'mimetype': 'application/pdf'})
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{ek.id}?download=true', 'target': 'new'}

    @api.model
    def _cron_atlas_mysoft(self):
        for company in self.env['res.company'].search([('atlas_mysoft_aktif', '=', True), ('atlas_eirsaliye', '=', True)]):
            for p in self.search([('company_id', '=', company.id), ('atlas_mysoft_durum', '=', 'kuyrukta'), ('state', '=', 'done')], limit=100):
                try:
                    with self.env.cr.savepoint():
                        p._atlas_mysoft_gonder()
                except UserError as hata:
                    p.write({'atlas_mysoft_durum': 'hata', 'atlas_mysoft_mesaj': str(hata)[:2000]})
            for p in self.search([('company_id', '=', company.id), ('atlas_mysoft_durum', '=', 'gonderildi')], limit=30):
                try:
                    with self.env.cr.savepoint():
                        p.action_atlas_mysoft_durum()
                except UserError:
                    continue
