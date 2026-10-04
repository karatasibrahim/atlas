from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import html2plaintext

SATIS_DURUM = {'draft': 'Teklif', 'sent': 'Teklif Gönderildi', 'sale': 'Sipariş', 'cancel': 'İptal'}
MASRAF_DURUM = {'draft': 'Taslak', 'submitted': 'Onayda', 'approved': 'Onaylandı', 'posted': 'Muhasebeleşti',
                'in_payment': 'Ödemede', 'paid': 'Ödendi', 'refused': 'Reddedildi'}
IZIN_DURUM = {'confirm': 'Onay Bekliyor', 'validate1': 'İkinci Onayda', 'validate': 'Onaylandı',
              'refuse': 'Reddedildi', 'cancel': 'İptal'}
ONAY_DURUM = {'taslak': 'Taslak', 'beklemede': 'Onay Bekliyor', 'onaylandi': 'Onaylandı',
              'reddedildi': 'Reddedildi', 'iptal': 'İptal'}


class AtlasMobil(models.AbstractModel):
    """Mobil uygulama API'si. Metotlar kullanıcının kendi yetkisiyle çalışır; dönüşler JSON uyumlu sözlüklerdir.
    Tarih-saatler UTC ISO 8601 ('Z' ekli) döner, istemci yerel saate çevirir."""
    _name = 'atlas.mobil'
    _description = 'Atlas Mobil API'

    # -------------------------------------------------------------------------
    # Yardımcılar
    # -------------------------------------------------------------------------

    @api.model
    def _dt(self, value):
        return value.isoformat() + 'Z' if value else False

    @api.model
    def _d(self, value):
        return fields.Date.to_string(value) if value else False

    @api.model
    def _erisim(self, model, operation='read'):
        return model in self.env and self.env[model].has_access(operation)

    @api.model
    def _calisan(self):
        return self.env.user.employee_id

    @api.model
    def _gorsel(self, model, res_id, field='image_128'):
        return f'/web/image/{model}/{res_id}/{field}'

    @api.model
    def _bugun_utc(self):
        """Kullanıcının saat dilimine göre bugünün başlangıcı (UTC, naive)."""
        today = fields.Date.context_today(self)
        local = fields.Datetime.context_timestamp(self, datetime.combine(today, time.min))
        return datetime.combine(today, time.min) - local.utcoffset()

    @api.model
    def _sirket_tutari(self, order):
        rate = order.currency_rate or 1.0
        return order.amount_untaxed / rate if order.currency_id != self.env.company.currency_id else order.amount_untaxed

    # -------------------------------------------------------------------------
    # Profil ve ana sayfa
    # -------------------------------------------------------------------------

    @api.model
    def profil(self):
        user = self.env.user
        employee = self._calisan()
        company = self.env.company
        return {
            'id': user.id, 'ad': user.name, 'email': user.email or '', 'login': user.login,
            'avatar': self._gorsel('res.users', user.id, 'avatar_128'),
            'sirket': company.name, 'sirket_id': company.id,
            'sirketler': [{'id': c.id, 'ad': c.name} for c in user.company_ids],
            'logo': self._gorsel('res.company', company.id, 'logo'),
            'para_birimi': company.currency_id.name, 'para_simge': company.currency_id.symbol,
            'calisan_id': employee.id or False, 'unvan': employee.job_title or '',
            'departman': employee.department_id.name or '',
            'moduller': {
                'satis': self._erisim('sale.order'),
                'crm': self._erisim('crm.lead'),
                'cari': self._erisim('res.partner'),
                'depo': self._erisim('stock.picking', 'write'),
                'uretim': self._erisim('mrp.production', 'write'),
                'onay': self._erisim('atlas.onay.talep'),
                'devam': bool(employee),
                'masraf': bool(employee) and self._erisim('hr.expense', 'create'),
                'izin': bool(employee) and self._erisim('hr.leave', 'create') and self._erisim('hr.work.entry.type'),
            },
        }

    @api.model
    def ozet(self):
        """Ana sayfa göstergeleri; yetkisi olmayan bölümler dönmez."""
        company = self.env.company
        today = fields.Date.context_today(self)
        gun_bas = self._bugun_utc()
        ay_bas = gun_bas - timedelta(days=today.day - 1)
        onceki_ay_bas = (ay_bas - timedelta(days=1)).replace(day=1)
        onceki_ay_ayni_gun = onceki_ay_bas + (gun_bas + timedelta(days=1) - ay_bas)
        result = {'para_simge': company.currency_id.symbol, 'para_birimi': company.currency_id.name}

        if self._erisim('sale.order'):
            SO = self.env['sale.order']
            orders = SO.search([('state', '=', 'sale'), ('date_order', '>=', min(onceki_ay_bas, gun_bas - timedelta(days=6))),
                                ('company_id', '=', company.id)])
            seri = []
            for i in range(6, -1, -1):
                bas = gun_bas - timedelta(days=i)
                gun = today - timedelta(days=i)
                tutar = sum(self._sirket_tutari(o) for o in orders if bas <= o.date_order < bas + timedelta(days=1))
                seri.append({'tarih': self._d(gun), 'tutar': round(tutar, 2)})
            bu_ay = sum(self._sirket_tutari(o) for o in orders if o.date_order >= ay_bas)
            onceki = sum(self._sirket_tutari(o) for o in orders if onceki_ay_bas <= o.date_order < onceki_ay_ayni_gun)
            result['satis'] = {
                'bu_ay': round(bu_ay, 2), 'onceki_ay': round(onceki, 2),
                'degisim': round((bu_ay - onceki) / onceki * 100, 1) if onceki else None,
                'bugun': seri[-1]['tutar'], 'seri': seri,
                'acik_teklif': SO.search_count([('state', 'in', ('draft', 'sent')), ('company_id', '=', company.id)]),
                'faturalanacak': SO.search_count([('invoice_status', '=', 'to invoice'), ('company_id', '=', company.id)]),
            }

        if self._erisim('account.move'):
            moves = self.env['account.move'].search([
                ('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')), ('company_id', '=', company.id)])
            vadesi_gecen = moves.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today)
            result['tahsilat'] = {
                'acik': round(sum(moves.mapped('amount_residual_signed')), 2),
                'vadesi_gecen': round(sum(vadesi_gecen.mapped('amount_residual_signed')), 2),
                'vadesi_gecen_adet': len(vadesi_gecen),
            }

        if self._erisim('stock.picking'):
            result['depo'] = self.env['atlas.barkod'].ana_ekran()

        if self._erisim('crm.lead'):
            leads = self.env['crm.lead'].search([('type', '=', 'opportunity'), ('user_id', '=', self.env.uid)])
            result['crm'] = {'acik': len(leads), 'beklenen': round(sum(leads.mapped('expected_revenue')), 2),
                             'agirlikli': round(sum(l.expected_revenue * l.probability / 100 for l in leads), 2)}

        result['onay_bekleyen'] = len(self._onay_kalemleri())
        result['devam'] = self.devam_durum() if self._calisan() else False
        result['aktiviteler'] = self.aktiviteler(limit=5)
        result['aktivite_sayisi'] = self.env['mail.activity'].search_count(
            [('user_id', '=', self.env.uid), ('date_deadline', '<=', today)])
        return result

    @api.model
    def rozetler(self):
        today = fields.Date.context_today(self)
        return {
            'onay': len(self._onay_kalemleri()),
            'aktivite': self.env['mail.activity'].search_count([('user_id', '=', self.env.uid), ('date_deadline', '<=', today)]),
        }

    # -------------------------------------------------------------------------
    # Aktiviteler
    # -------------------------------------------------------------------------

    @api.model
    def aktiviteler(self, limit=50):
        activities = self.env['mail.activity'].search([('user_id', '=', self.env.uid)], order='date_deadline, id', limit=limit)
        return [self._aktivite_dict(a) for a in activities]

    @api.model
    def _aktivite_dict(self, a):
        return {
            'id': a.id, 'baslik': a.summary or a.activity_type_id.name or '', 'tur': a.activity_type_id.name or '',
            'ikon': a.activity_type_id.icon or '', 'kayit': a.res_name or '', 'model': a.res_model, 'res_id': a.res_id,
            'model_ad': self.env['ir.model']._get(a.res_model).name if a.res_model else '',
            'tarih': self._d(a.date_deadline), 'durum': a.state, 'not': self._duz(a.note),
        }

    @api.model
    def aktivite_tamamla(self, activity_id, geri_bildirim=''):
        activity = self.env['mail.activity'].browse(activity_id).exists()
        if not activity:
            raise UserError(self.env._('Aktivite bulunamadı; başka biri tamamlamış olabilir.'))
        activity.action_feedback(feedback=geri_bildirim or False)
        return True

    # -------------------------------------------------------------------------
    # Cari
    # -------------------------------------------------------------------------

    @api.model
    def _cari_ozet(self, partner):
        return {
            'id': partner.id, 'ad': partner.display_name, 'kod': partner.ref or '',
            'sirket': partner.is_company, 'telefon': partner.phone or '',
            'email': partner.email or '', 'sehir': partner.city or '', 'gorsel': self._gorsel('res.partner', partner.id, 'avatar_128'),
        }

    @api.model
    def cari_ara(self, arama='', offset=0, limit=40):
        domain = [('parent_id', '=', False)] if not arama else []
        if arama:
            domain = ['|', '|', '|', '|', ('name', 'ilike', arama), ('ref', 'ilike', arama), ('email', 'ilike', arama),
                      ('phone', 'ilike', arama), ('vat', 'ilike', arama)]
        partners = self.env['res.partner'].search(domain, offset=offset, limit=limit, order='name')
        return [self._cari_ozet(p) for p in partners]

    @api.model
    def cari_detay(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id).exists()
        if not partner:
            raise UserError(self.env._('Cari bulunamadı.'))
        data = self._cari_ozet(partner)
        address = ', '.join(filter(None, [partner.street, partner.street2, partner.zip, partner.city,
                                          partner.state_id.name, partner.country_id.name]))
        data.update({
            'adres': address, 'vergi_no': partner.vat or '', 'web': partner.website or '',
            'enlem': partner.partner_latitude or False, 'boylam': partner.partner_longitude or False,
            'kisiler': [self._cari_ozet(c) for c in partner.child_ids[:20]],
            'ust': self._cari_ozet(partner.parent_id) if partner.parent_id else False,
            'etiketler': partner.category_id.mapped('name'),
        })
        if 'atlas_bakiye' in partner._fields and self._erisim('atlas.cari.hareket'):
            data['bakiye'] = {'borc': partner.atlas_borc, 'alacak': partner.atlas_alacak, 'bakiye': partner.atlas_bakiye}
        if self._erisim('sale.order'):
            orders = self.env['sale.order'].search([('partner_id', 'child_of', partner.commercial_partner_id.id)],
                                                   order='date_order desc', limit=5)
            data['siparisler'] = [self._satis_ozet(o) for o in orders]
        if self._erisim('account.move'):
            invoices = self.env['account.move'].search([
                ('partner_id', 'child_of', partner.commercial_partner_id.id), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))], order='invoice_date_due', limit=10)
            today = fields.Date.context_today(self)
            data['acik_faturalar'] = [{
                'id': m.id, 'ad': m.name, 'tarih': self._d(m.invoice_date), 'vade': self._d(m.invoice_date_due),
                'tutar': m.amount_total, 'kalan': m.amount_residual, 'para_simge': m.currency_id.symbol,
                'gecikti': bool(m.invoice_date_due and m.invoice_date_due < today),
            } for m in invoices]
        return data

    @api.model
    def cari_olustur(self, ad, sirket=True, telefon='', email='', sehir='', vergi_no=''):
        if not (ad or '').strip():
            raise UserError(self.env._('Cari adını yazın.'))
        partner = self.env['res.partner'].create({
            'name': ad.strip(), 'is_company': sirket, 'phone': telefon or False, 'email': email or False,
            'city': sehir or False, 'vat': vergi_no or False,
        })
        return self._cari_ozet(partner)

    # -------------------------------------------------------------------------
    # Ürün
    # -------------------------------------------------------------------------

    @api.model
    def _urun_dict(self, product, stok=True):
        data = {
            'id': product.id, 'ad': product.display_name, 'kod': product.default_code or '', 'barkod': product.barcode or '',
            'fiyat': product.lst_price, 'birim': product.uom_id.name, 'tur': product.type,
            'gorsel': self._gorsel('product.product', product.id), 'gorsel_var': bool(product.image_128),
        }
        if stok and product.is_storable:
            data['stok'] = product.qty_available
            data['tahmini'] = product.virtual_available
        return data

    @api.model
    def urun_ara(self, arama='', satilabilir=True, limit=40, offset=0):
        domain = [('sale_ok', '=', True)] if satilabilir else []
        if arama:
            domain += ['|', '|', ('name', 'ilike', arama), ('default_code', 'ilike', arama), ('barcode', '=', arama)]
        products = self.env['product.product'].search(domain, limit=limit, offset=offset, order='default_code, name')
        return [self._urun_dict(p) for p in products]

    @api.model
    def urun_detay(self, product_id):
        product = self.env['product.product'].browse(product_id).exists()
        if not product:
            raise UserError(self.env._('Ürün bulunamadı.'))
        data = self._urun_dict(product)
        data.update({'kategori': product.categ_id.complete_name, 'aciklama': product.description_sale or '',
                     'maliyet': product.standard_price if self.env.user.has_group('base.group_user') else False,
                     'gorsel_buyuk': self._gorsel('product.product', product.id, 'image_512')})
        if product.is_storable and self._erisim('stock.quant'):
            data['stoklar'] = [{'lokasyon': q.location_id.complete_name, 'seri': q.lot_id.name or '', 'miktar': q.quantity,
                                'rezerve': q.reserved_quantity}
                               for q in self.env['stock.quant'].search([('product_id', '=', product.id),
                                                                        ('location_id.usage', '=', 'internal'),
                                                                        ('quantity', '!=', 0)], limit=50)]
        return data

    # -------------------------------------------------------------------------
    # Satış
    # -------------------------------------------------------------------------

    @api.model
    def _satis_ozet(self, order):
        return {
            'id': order.id, 'ad': order.name, 'cari': order.partner_id.display_name, 'cari_id': order.partner_id.id,
            'tarih': self._dt(order.date_order), 'tutar': order.amount_total, 'para_simge': order.currency_id.symbol,
            'durum': order.state, 'durum_ad': SATIS_DURUM.get(order.state, order.state),
            'fatura_durum': order.invoice_status or '', 'satici': order.user_id.name or '',
        }

    @api.model
    def satis_listesi(self, arama='', filtre='hepsi', offset=0, limit=30):
        domain = []
        if filtre == 'teklif':
            domain.append(('state', 'in', ('draft', 'sent')))
        elif filtre == 'siparis':
            domain.append(('state', '=', 'sale'))
        elif filtre == 'benim':
            domain.append(('user_id', '=', self.env.uid))
        if arama:
            domain += ['|', '|', ('name', 'ilike', arama), ('partner_id', 'ilike', arama), ('client_order_ref', 'ilike', arama)]
        orders = self.env['sale.order'].search(domain, offset=offset, limit=limit, order='date_order desc, id desc')
        return [self._satis_ozet(o) for o in orders]

    @api.model
    def satis_detay(self, order_id):
        order = self.env['sale.order'].browse(order_id).exists()
        if not order:
            raise UserError(self.env._('Sipariş bulunamadı.'))
        data = self._satis_ozet(order)
        data.update({
            'ara_toplam': order.amount_untaxed, 'vergi': order.amount_tax,
            'gecerlilik': self._d(order.validity_date), 'not': order.note and self._duz(order.note) or '',
            'odeme_kosulu': order.payment_term_id.name or '', 'referans': order.client_order_ref or '',
            'teslimatlar': [{'id': p.id, 'ad': p.name, 'durum': p.state, 'tarih': self._dt(p.scheduled_date)}
                            for p in order.picking_ids] if 'picking_ids' in order._fields else [],
            'faturalar': [{'id': m.id, 'ad': m.name, 'durum': m.payment_state, 'tutar': m.amount_total}
                          for m in order.invoice_ids if m.state == 'posted'],
            'satirlar': [{
                'id': l.id, 'urun_id': l.product_id.id, 'ad': l.product_id.display_name or l.name,
                'aciklama': l.name, 'miktar': l.product_uom_qty, 'birim': l.product_uom_id.name or '',
                'fiyat': l.price_unit, 'indirim': l.discount, 'tutar': l.price_subtotal,
                'teslim': l.qty_delivered, 'faturalanan': l.qty_invoiced,
                'gorsel': self._gorsel('product.product', l.product_id.id) if l.product_id else False,
            } for l in order.order_line if not l.display_type],
            'onaylanabilir': order.state in ('draft', 'sent') and order.has_access('write'),
            'pdf': f'/report/pdf/sale.report_saleorder/{order.id}',
        })
        return data

    @api.model
    def _duz(self, html):
        return html2plaintext(html or '').strip()

    @api.model
    def satis_olustur(self, partner_id, satirlar, not_metni='', onayla=False):
        """satirlar: [{'urun_id': int, 'miktar': float, 'fiyat': float|None, 'indirim': float|None}]"""
        if not satirlar:
            raise UserError(self.env._('En az bir ürün ekleyin.'))
        lines = []
        for satir in satirlar:
            vals = {'product_id': int(satir['urun_id']), 'product_uom_qty': float(satir.get('miktar') or 1)}
            if satir.get('fiyat') is not None:
                vals['price_unit'] = float(satir['fiyat'])
            if satir.get('indirim'):
                vals['discount'] = float(satir['indirim'])
            lines.append(Command.create(vals))
        order = self.env['sale.order'].create({'partner_id': int(partner_id), 'order_line': lines,
                                               'note': not_metni or False})
        # Fiyat listesinden gelen fiyat, kullanıcı elle girdiyse korunur
        for line, satir in zip(order.order_line, satirlar):
            if satir.get('fiyat') is not None and line.price_unit != float(satir['fiyat']):
                line.price_unit = float(satir['fiyat'])
        if onayla:
            order.action_confirm()
        return self.satis_detay(order.id)

    @api.model
    def satis_onayla(self, order_id):
        order = self.env['sale.order'].browse(order_id).exists()
        if not order or order.state not in ('draft', 'sent'):
            raise UserError(self.env._('Yalnızca teklifler onaylanabilir.'))
        order.action_confirm()
        return self.satis_detay(order.id)

    @api.model
    def satis_iptal(self, order_id):
        order = self.env['sale.order'].browse(order_id).exists()
        if not order:
            raise UserError(self.env._('Sipariş bulunamadı.'))
        order.with_context(disable_cancel_warning=True).action_cancel()
        return self.satis_detay(order.id)

    # -------------------------------------------------------------------------
    # CRM
    # -------------------------------------------------------------------------

    @api.model
    def _firsat_dict(self, lead):
        return {
            'id': lead.id, 'ad': lead.name, 'cari': lead.partner_id.display_name or lead.partner_name or lead.contact_name or '',
            'gelir': lead.expected_revenue, 'olasilik': lead.probability, 'asama_id': lead.stage_id.id,
            'asama': lead.stage_id.name or '', 'oncelik': int(lead.priority or 0), 'satici': lead.user_id.name or '',
            'kapanis': self._d(lead.date_deadline), 'etiketler': lead.tag_ids.mapped('name'),
            'para_simge': lead.company_currency.symbol or self.env.company.currency_id.symbol,
            'telefon': lead.phone or '', 'email': lead.email_from or '',
        }

    @api.model
    def crm_hat(self, arama='', benim=True):
        """Fırsat hattı: aşamalar + her aşamadaki fırsatlar."""
        domain = [('type', '=', 'opportunity')]
        if benim:
            domain.append(('user_id', '=', self.env.uid))
        if arama:
            domain += ['|', '|', ('name', 'ilike', arama), ('partner_id', 'ilike', arama), ('partner_name', 'ilike', arama)]
        leads = self.env['crm.lead'].search(domain, order='priority desc, id desc', limit=300)
        stages = self.env['crm.stage'].search([])
        result = []
        for stage in stages:
            items = leads.filtered(lambda l: l.stage_id == stage)
            result.append({'id': stage.id, 'ad': stage.name, 'kazanildi': stage.is_won, 'katlanir': stage.fold,
                           'toplam': round(sum(items.mapped('expected_revenue')), 2),
                           'firsatlar': [self._firsat_dict(l) for l in items]})
        return result

    @api.model
    def crm_asamalar(self):
        return [{'id': s.id, 'ad': s.name, 'kazanildi': s.is_won, 'katlanir': s.fold} for s in self.env['crm.stage'].search([])]

    @api.model
    def crm_detay(self, lead_id):
        lead = self.env['crm.lead'].browse(lead_id).exists()
        if not lead:
            raise UserError(self.env._('Fırsat bulunamadı.'))
        data = self._firsat_dict(lead)
        data.update({
            'aciklama': self._duz(lead.description), 'cari_id': lead.partner_id.id or False,
            'aktiviteler': [self._aktivite_dict(a) for a in lead.activity_ids],
            'mesajlar': [{'yazar': m.author_id.name or '', 'tarih': self._dt(m.date), 'metin': self._duz(m.body)}
                         for m in lead.message_ids.filtered(lambda m: m.message_type in ('comment', 'email') and m.body)[:10]],
            'teklifler': [self._satis_ozet(o) for o in lead.order_ids] if 'order_ids' in lead._fields else [],
        })
        return data

    @api.model
    def crm_asama(self, lead_id, asama_id):
        lead = self.env['crm.lead'].browse(lead_id).exists()
        lead.stage_id = asama_id
        return self._firsat_dict(lead)

    @api.model
    def crm_kazanildi(self, lead_id):
        lead = self.env['crm.lead'].browse(lead_id).exists()
        lead.action_set_won()
        return self._firsat_dict(lead)

    @api.model
    def crm_kaybedildi(self, lead_id, neden_id=False):
        lead = self.env['crm.lead'].browse(lead_id).exists()
        lead.action_set_lost(lost_reason_id=neden_id or False)
        return True

    @api.model
    def crm_kayip_nedenleri(self):
        return [{'id': r.id, 'ad': r.name} for r in self.env['crm.lost.reason'].search([])]

    @api.model
    def crm_olustur(self, ad, partner_id=False, gelir=0.0, olasilik=None, telefon='', email='', aciklama=''):
        vals = {'name': ad, 'type': 'opportunity', 'partner_id': partner_id or False, 'expected_revenue': gelir or 0.0,
                'phone': telefon or False, 'email_from': email or False, 'description': aciklama or False,
                'user_id': self.env.uid}
        if olasilik is not None:
            vals['probability'] = olasilik
        return self._firsat_dict(self.env['crm.lead'].create(vals))

    @api.model
    def not_ekle(self, model, res_id, metin):
        """Kayda (fırsat, sipariş, cari...) iç not ekler."""
        if model not in ('crm.lead', 'sale.order', 'res.partner', 'stock.picking', 'atlas.onay.talep'):
            raise AccessError(self.env._('Bu kayda mobilden not eklenemez.'))
        record = self.env[model].browse(res_id).exists()
        record.message_post(body=metin, message_type='comment', subtype_xmlid='mail.mt_note')
        return True

    # -------------------------------------------------------------------------
    # Onay merkezi
    # -------------------------------------------------------------------------

    @api.model
    def _onay_kalemleri(self):
        items = []
        if self._erisim('atlas.onay.satir'):
            satirlar = self.env['atlas.onay.satir'].search([('user_id', '=', self.env.uid), ('durum', '=', 'bekliyor'),
                                                            ('talep_durum', '=', 'beklemede')])
            for s in satirlar:
                t = s.talep_id
                items.append({
                    'kaynak': 'onay', 'id': t.id, 'baslik': t.konu, 'no': t.name, 'kategori': t.kategori_id.name,
                    'kisi': t.talep_eden_id.name, 'kisi_gorsel': self._gorsel('res.users', t.talep_eden_id.id, 'avatar_128'),
                    'tutar': t.tutar or False, 'para_simge': t.currency_id.symbol, 'tarih': self._dt(t.create_date),
                    'ilerleme': f'{t.onaylayan_sayisi}/{t.gereken_onay}',
                })
        if self._erisim('hr.expense'):
            expenses = self.env['hr.expense'].search([('state', '=', 'submitted')]).filtered(
                lambda e: e.can_approve and e.employee_id.user_id != self.env.user)
            for e in expenses:
                items.append({
                    'kaynak': 'masraf', 'id': e.id, 'baslik': e.name, 'no': '', 'kategori': 'Masraf',
                    'kisi': e.employee_id.name, 'kisi_gorsel': self._gorsel('hr.employee', e.employee_id.id, 'avatar_128'),
                    'tutar': e.total_amount_currency, 'para_simge': e.currency_id.symbol, 'tarih': self._dt(e.create_date),
                    'ilerleme': '',
                })
        if self._erisim('hr.leave'):
            leaves = self.env['hr.leave'].search([('state', 'in', ('confirm', 'validate1'))]).filtered(
                lambda l: (l.can_approve or l.can_validate) and l.employee_id.user_id != self.env.user)
            for l in leaves:
                items.append({
                    'kaynak': 'izin', 'id': l.id, 'baslik': f'{l.work_entry_type_id.name} — {l.duration_display}',
                    'no': '', 'kategori': 'İzin', 'kisi': l.employee_id.name,
                    'kisi_gorsel': self._gorsel('hr.employee', l.employee_id.id, 'avatar_128'),
                    'tutar': False, 'para_simge': '', 'tarih': self._dt(l.create_date), 'ilerleme': '',
                    'donem': f'{self._d(l.request_date_from)} → {self._d(l.request_date_to)}',
                })
        items.sort(key=lambda i: i['tarih'] or '', reverse=True)
        return items

    @api.model
    def onay_listesi(self):
        return self._onay_kalemleri()

    @api.model
    def onay_taleplerim(self):
        talepler = self.env['atlas.onay.talep'].search([('talep_eden_id', '=', self.env.uid)], order='id desc', limit=50)
        return [{
            'id': t.id, 'no': t.name, 'baslik': t.konu, 'kategori': t.kategori_id.name, 'durum': t.durum,
            'durum_ad': ONAY_DURUM.get(t.durum, t.durum), 'tutar': t.tutar or False, 'para_simge': t.currency_id.symbol,
            'tarih': self._dt(t.create_date), 'ilerleme': f'{t.onaylayan_sayisi}/{t.gereken_onay}',
        } for t in talepler]

    @api.model
    def onay_detay(self, kaynak, res_id):
        if kaynak == 'onay':
            t = self.env['atlas.onay.talep'].browse(res_id).exists()
            alanlar = []
            if t.tarih:
                alanlar.append(['Tarih', self._dt(t.tarih)])
            if t.tarih_bas:
                alanlar.append(['Dönem', f'{self._dt(t.tarih_bas)} → {self._dt(t.tarih_bit)}'])
            if t.partner_id:
                alanlar.append(['Cari', t.partner_id.display_name])
            if t.urun_id:
                alanlar.append(['Ürün', t.urun_id.display_name])
            if t.miktar:
                alanlar.append(['Miktar', f'{t.miktar:g}'])
            if t.referans:
                alanlar.append(['Referans', t.referans])
            return {
                'kaynak': kaynak, 'id': t.id, 'no': t.name, 'baslik': t.konu, 'kategori': t.kategori_id.name,
                'kisi': t.talep_eden_id.name, 'durum': t.durum, 'durum_ad': ONAY_DURUM.get(t.durum),
                'tutar': t.tutar or False, 'para_simge': t.currency_id.symbol, 'aciklama': self._duz(t.aciklama),
                'alanlar': alanlar, 'tarih': self._dt(t.create_date),
                'onaylayicilar': [{'ad': s.user_id.name, 'durum': s.durum, 'zorunlu': s.zorunlu, 'not': s.aciklama or '',
                                   'tarih': self._dt(s.tarih), 'gorsel': self._gorsel('res.users', s.user_id.id, 'avatar_128')}
                                  for s in t.sudo().onay_ids.sorted('sira')],
                'karar_verebilir': t.durum == 'beklemede' and t.benim_durumum == 'bekliyor',
                'ilgili': t.res_model and {'model': t.res_model, 'id': t.res_id} or False,
            }
        if kaynak == 'masraf':
            e = self.env['hr.expense'].browse(res_id).exists()
            return {
                'kaynak': kaynak, 'id': e.id, 'baslik': e.name, 'kategori': e.product_id.name or 'Masraf',
                'kisi': e.employee_id.name, 'durum': e.state, 'durum_ad': MASRAF_DURUM.get(e.state),
                'tutar': e.total_amount_currency, 'para_simge': e.currency_id.symbol, 'aciklama': e.description or '',
                'alanlar': [['Tarih', self._d(e.date)], ['Ödeme', 'Çalışan' if e.payment_mode == 'own_account' else 'Şirket']],
                'tarih': self._dt(e.create_date), 'onaylayicilar': [],
                'ekler': [{'id': a.id, 'ad': a.name, 'tip': a.mimetype, 'url': f'/web/content/{a.id}'} for a in e.attachment_ids],
                'karar_verebilir': e.state == 'submitted' and e.can_approve,
            }
        if kaynak == 'izin':
            l = self.env['hr.leave'].browse(res_id).exists()
            return {
                'kaynak': kaynak, 'id': l.id, 'baslik': l.work_entry_type_id.name, 'kategori': 'İzin',
                'kisi': l.employee_id.name, 'durum': l.state, 'durum_ad': IZIN_DURUM.get(l.state),
                'tutar': False, 'para_simge': '', 'aciklama': l.notes or '',
                'alanlar': [['Başlangıç', self._d(l.request_date_from)], ['Bitiş', self._d(l.request_date_to)],
                            ['Süre', l.duration_display]],
                'tarih': self._dt(l.create_date), 'onaylayicilar': [],
                'karar_verebilir': l.state in ('confirm', 'validate1') and (l.can_approve or l.can_validate),
            }
        raise UserError(self.env._('Tanımsız onay kaynağı: %s', kaynak))

    @api.model
    def onay_ver(self, kaynak, res_id, aciklama=''):
        if kaynak == 'onay':
            self.env['atlas.onay.talep'].browse(res_id).action_onayla(aciklama=aciklama or None)
        elif kaynak == 'masraf':
            expense = self.env['hr.expense'].browse(res_id)
            expense._check_can_approve()
            expense._do_approve()
        elif kaynak == 'izin':
            self.env['hr.leave'].browse(res_id).action_approve()
        else:
            raise UserError(self.env._('Tanımsız onay kaynağı: %s', kaynak))
        return True

    @api.model
    def onay_reddet(self, kaynak, res_id, neden):
        if not (neden or '').strip():
            raise UserError(self.env._('Red nedenini yazın.'))
        if kaynak == 'onay':
            self.env['atlas.onay.talep'].browse(res_id).action_reddet(neden)
        elif kaynak == 'masraf':
            expense = self.env['hr.expense'].browse(res_id)
            expense._check_can_refuse()
            expense._do_refuse(neden)
        elif kaynak == 'izin':
            leave = self.env['hr.leave'].browse(res_id)
            leave.action_refuse()
            leave.message_post(body=self.env._('Red nedeni: %s', neden), subtype_xmlid='mail.mt_note')
        else:
            raise UserError(self.env._('Tanımsız onay kaynağı: %s', kaynak))
        return True

    @api.model
    def onay_kategorileri(self):
        return [{'id': k.id, 'ad': k.name, 'aciklama': k.aciklama or '',
                 'alanlar': {a: k[f'alan_{a}'] for a in ('tarih', 'donem', 'tutar', 'partner', 'urun', 'miktar', 'referans', 'ek')}}
                for k in self.env['atlas.onay.kategori'].search([])]

    @api.model
    def onay_talep_olustur(self, kategori_id, konu, aciklama='', tutar=0.0, tarih=False, tarih_bas=False, tarih_bit=False,
                           partner_id=False, referans='', miktar=0.0, gonder=True):
        talep = self.env['atlas.onay.talep'].create({
            'kategori_id': kategori_id, 'konu': konu, 'aciklama': aciklama or False, 'tutar': tutar or 0.0,
            'tarih': tarih or False, 'tarih_bas': tarih_bas or False, 'tarih_bit': tarih_bit or False,
            'partner_id': partner_id or False, 'referans': referans or False, 'miktar': miktar or 0.0,
        })
        if gonder:
            talep.action_gonder()
        return {'id': talep.id, 'no': talep.name, 'durum': talep.durum}

    # -------------------------------------------------------------------------
    # Personel: giriş/çıkış, masraf, izin
    # -------------------------------------------------------------------------

    @api.model
    def _calisan_zorunlu(self):
        employee = self._calisan()
        if not employee:
            raise UserError(self.env._('Kullanıcınız bir çalışan kaydına bağlı değil.'))
        return employee

    @api.model
    def devam_durum(self):
        employee = self._calisan_zorunlu()
        Attendance = self.env['hr.attendance'].sudo()
        gun_bas = self._bugun_utc()
        today_atts = Attendance.search([('employee_id', '=', employee.id), ('check_in', '>=', gun_bas)])
        open_att = Attendance.search([('employee_id', '=', employee.id), ('check_out', '=', False)], limit=1)
        now = fields.Datetime.now()
        hours = sum(a.worked_hours for a in today_atts if a.check_out)
        if open_att:
            hours += (now - max(open_att.check_in, gun_bas)).total_seconds() / 3600
        return {
            'durum': employee.sudo().attendance_state, 'giris': self._dt(open_att.check_in) if open_att else False,
            'bugun_saat': round(hours, 2), 'sunucu_saati': self._dt(now),
        }

    @api.model
    def devam_degistir(self, enlem=False, boylam=False, konum=''):
        employee = self._calisan_zorunlu()
        geo = None
        if enlem and boylam:
            geo = {'latitude': enlem, 'longitude': boylam, 'location': konum or f'{enlem:.5f}, {boylam:.5f}',
                   'mode': 'systray', 'browser': 'Atlas Mobil'}
        employee.sudo()._attendance_action_change(geo)
        return self.devam_durum()

    @api.model
    def devam_gecmis(self, gun=14):
        employee = self._calisan_zorunlu()
        atts = self.env['hr.attendance'].sudo().search([('employee_id', '=', employee.id)], order='check_in desc', limit=gun * 3)
        return [{'id': a.id, 'giris': self._dt(a.check_in), 'cikis': self._dt(a.check_out), 'saat': round(a.worked_hours, 2),
                 'konum': a.in_location or ''} for a in atts]

    @api.model
    def masraf_urunleri(self):
        return [{'id': p.id, 'ad': p.name, 'fiyat': p.standard_price, 'kod': p.default_code or ''}
                for p in self.env['product.product'].search([('can_be_expensed', '=', True)], order='name')]

    @api.model
    def _masraf_dict(self, e):
        return {'id': e.id, 'ad': e.name, 'tarih': self._d(e.date), 'tutar': e.total_amount_currency,
                'para_simge': e.currency_id.symbol, 'durum': e.state, 'durum_ad': MASRAF_DURUM.get(e.state, e.state),
                'kategori': e.product_id.name or '', 'ek': e.nb_attachment}

    @api.model
    def masraf_listesi(self):
        employee = self._calisan_zorunlu()
        return [self._masraf_dict(e) for e in self.env['hr.expense'].search(
            [('employee_id', '=', employee.id)], order='date desc, id desc', limit=60)]

    @api.model
    def masraf_olustur(self, ad, tutar, urun_id=False, tarih=False, aciklama='', fis_b64=False, fis_adi='fis.jpg',
                       sirket_odedi=False, gonder=False):
        employee = self._calisan_zorunlu()
        if not tutar or float(tutar) <= 0:
            raise UserError(self.env._('Masraf tutarını girin.'))
        if not urun_id:
            raise UserError(self.env._('Masraf kategorisini seçin.'))
        vals = {'name': ad, 'employee_id': employee.id, 'total_amount_currency': float(tutar),
                'date': tarih or fields.Date.context_today(self), 'description': aciklama or False,
                'payment_mode': 'company_account' if sirket_odedi else 'own_account', 'product_id': urun_id}
        expense = self.env['hr.expense'].create(vals)
        if expense.product_id and expense.product_has_cost:
            # Ürün maliyetli ise birim fiyat üründen gelir; mobilde girilen toplamı koru
            expense.write({'quantity': 1, 'price_unit': float(tutar)})
        if fis_b64:
            attachment = self.env['ir.attachment'].create({
                'name': fis_adi or 'fis.jpg', 'datas': fis_b64, 'res_model': 'hr.expense', 'res_id': expense.id})
            expense.message_main_attachment_id = attachment
        if gonder:
            expense.action_submit()
        return self._masraf_dict(expense)

    @api.model
    def masraf_gonder(self, expense_id):
        expense = self.env['hr.expense'].browse(expense_id).exists()
        expense.action_submit()
        return self._masraf_dict(expense)

    @api.model
    def izin_turleri(self):
        employee = self._calisan_zorunlu()
        types = self.env['hr.work.entry.type'].with_context(employee_id=employee.id).search(
            [('time_off_selectable', '=', True)] if 'time_off_selectable' in self.env['hr.work.entry.type']._fields else [])
        result = []
        for t in types:
            if t.requires_allocation and not t.has_valid_allocation:
                continue
            item = {'id': t.id, 'ad': t.name, 'birim': t.request_unit, 'tahsis': t.requires_allocation}
            if t.requires_allocation:
                item['kalan'] = t.virtual_remaining_leaves if 'virtual_remaining_leaves' in t._fields else False
            result.append(item)
        return result

    @api.model
    def izin_listesi(self):
        employee = self._calisan_zorunlu()
        leaves = self.env['hr.leave'].search([('employee_id', '=', employee.id)], order='request_date_from desc', limit=40)
        return [{'id': l.id, 'tur': l.work_entry_type_id.name, 'bas': self._d(l.request_date_from),
                 'bit': self._d(l.request_date_to), 'sure': l.duration_display, 'durum': l.state,
                 'durum_ad': IZIN_DURUM.get(l.state, l.state), 'aciklama': l.notes or ''} for l in leaves]

    @api.model
    def izin_olustur(self, tur_id, bas, bit, aciklama=''):
        employee = self._calisan_zorunlu()
        leave = self.env['hr.leave'].create({
            'employee_id': employee.id, 'work_entry_type_id': tur_id,
            'request_date_from': bas, 'request_date_to': bit, 'notes': aciklama or False,
        })
        return {'id': leave.id, 'durum': leave.state, 'durum_ad': IZIN_DURUM.get(leave.state), 'sure': leave.duration_display}

    @api.model
    def izin_iptal(self, leave_id):
        leave = self.env['hr.leave'].browse(leave_id).exists()
        if leave.state not in ('confirm', 'validate1'):
            raise UserError(self.env._('Yalnızca onay bekleyen izinler geri çekilebilir.'))
        leave.unlink()
        return True
