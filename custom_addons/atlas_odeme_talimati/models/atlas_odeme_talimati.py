import csv
import io

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.atlas_kasa_banka.models.account_journal import is_valid_iban, normalize_iban


class AtlasOdemeTalimat(models.Model):
    _name = 'atlas.odeme.talimat'
    _description = 'Toplu Ödeme Talimatı'
    _inherit = ['mail.thread']
    _order = 'tarih desc, id desc'

    name = fields.Char(string='Talimat No', required=True, copy=False, readonly=True, default='/')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    journal_id = fields.Many2one('account.journal', string='Ödeme Yapılacak Banka', required=True, tracking=True,
                                 domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]")
    tarih = fields.Date(string='Ödeme Tarihi', required=True, default=fields.Date.context_today, tracking=True)
    aciklama = fields.Char(string='Açıklama')
    durum = fields.Selection([('taslak', 'Taslak'), ('onaylandi', 'Onaylandı'), ('gonderildi', 'Bankaya Gönderildi'),
                              ('tamamlandi', 'Tamamlandı'), ('iptal', 'İptal')], string='Durum', default='taslak',
                             required=True, tracking=True, copy=False)
    satir_ids = fields.One2many('atlas.odeme.talimat.satir', 'talimat_id', string='Ödemeler', copy=True)
    toplam = fields.Monetary(string='Toplam', compute='_compute_toplam', store=True)
    satir_sayisi = fields.Integer(string='Ödeme Sayısı', compute='_compute_toplam', store=True)
    payment_ids = fields.One2many('account.payment', 'atlas_talimat_id', string='Ödeme Kayıtları')
    eslesen_sayisi = fields.Integer(string='Ekstreyle Eşleşen', compute='_compute_eslesen')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.odeme.talimat') or '/'
        return super().create(vals_list)

    @api.depends('satir_ids.tutar')
    def _compute_toplam(self):
        for t in self:
            t.toplam = sum(t.satir_ids.mapped('tutar'))
            t.satir_sayisi = len(t.satir_ids)

    @api.depends('payment_ids.is_matched')
    def _compute_eslesen(self):
        for t in self:
            t.eslesen_sayisi = len(t.payment_ids.filtered('is_matched'))

    # -------------------------------------------------------------------------
    # Onay
    # -------------------------------------------------------------------------

    def _kontrol(self):
        self.ensure_one()
        if not self.satir_ids:
            raise UserError(self.env._('Talimatta ödeme satırı yok.'))
        hatalar = []
        for satir in self.satir_ids:
            if satir.tutar <= 0:
                hatalar.append(self.env._('%s: tutar sıfırdan büyük olmalı', satir.partner_id.name))
            if not satir.partner_bank_id:
                hatalar.append(self.env._('%s: banka hesabı (IBAN) seçilmemiş', satir.partner_id.name))
            elif not is_valid_iban(satir.partner_bank_id.account_number):
                hatalar.append(self.env._('%(cari)s: geçersiz IBAN %(iban)s', cari=satir.partner_id.name, iban=satir.partner_bank_id.account_number))
            acik = sum(satir.move_ids.mapped('amount_residual'))
            if satir.move_ids and self.currency_id.compare_amounts(satir.tutar, acik) > 0:
                hatalar.append(self.env._('%(cari)s: tutar faturaların açık bakiyesini (%(acik)s) aşıyor', cari=satir.partner_id.name, acik=f'{acik:,.2f}'))
        if hatalar:
            raise UserError(self.env._('Talimat onaylanamadı:\n- %s', '\n- '.join(hatalar)))

    def action_onayla(self):
        """Her satır için ödeme kaydı oluşturur; faturalı satırlarda faturalar ödeme ile kapanır."""
        for t in self:
            if t.durum != 'taslak':
                raise UserError(self.env._('Yalnızca taslak talimat onaylanır.'))
            t._kontrol()
            method = t.journal_id.outbound_payment_method_line_ids[:1]
            for satir in t.satir_ids:
                ref = satir.aciklama or t.aciklama or t.name
                if satir.move_ids:
                    wizard = self.env['account.payment.register'].with_context(
                        active_model='account.move', active_ids=satir.move_ids.ids).create({
                            'journal_id': t.journal_id.id, 'payment_date': t.tarih, 'amount': satir.tutar,
                            'group_payment': True, 'partner_bank_id': satir.partner_bank_id.id,
                            'communication': ref, 'payment_method_line_id': method.id,
                        })
                    payment = wizard._create_payments()
                else:
                    payment = self.env['account.payment'].create({
                        'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': satir.partner_id.id,
                        'amount': satir.tutar, 'date': t.tarih, 'journal_id': t.journal_id.id, 'memo': ref,
                        'partner_bank_id': satir.partner_bank_id.id, 'payment_method_line_id': method.id,
                    })
                    payment.action_post()
                payment.atlas_talimat_id = t
                satir.payment_id = payment[:1]
            t.durum = 'onaylandi'
            t.message_post(body=self.env._('%(adet)s ödeme kaydı oluşturuldu, toplam %(tutar)s.', adet=len(t.satir_ids),
                                           tutar=f'{t.toplam:,.2f}'))
        return True

    def action_iptal(self):
        for t in self:
            if t.payment_ids.filtered('is_matched'):
                raise UserError(self.env._('%s: bankayla eşleşmiş ödeme var; önce ekstre eşleşmesini geri alın.', t.name))
            for payment in t.payment_ids.filtered(lambda p: p.state not in ('draft', 'canceled')):
                payment.action_draft()
                payment.action_cancel()
            t.satir_ids.write({'payment_id': False})
            t.durum = 'iptal'
        return True

    def action_taslaga_al(self):
        self.filtered(lambda t: t.durum == 'iptal').write({'durum': 'taslak'})
        return True

    def _durum_guncelle(self):
        for t in self.filtered(lambda t: t.durum in ('onaylandi', 'gonderildi')):
            if t.payment_ids and all(t.payment_ids.mapped('is_matched')):
                t.durum = 'tamamlandi'

    # -------------------------------------------------------------------------
    # Banka dosyası
    # -------------------------------------------------------------------------

    def _dosya_satirlari(self):
        self.ensure_one()
        satirlar = []
        for i, s in enumerate(self.satir_ids, start=1):
            ticari = s.partner_id.commercial_partner_id
            satirlar.append({
                'sira': i, 'alici': (s.partner_bank_id.holder_name or ticari.name or '')[:70],
                'vkn': (ticari.vat or '').upper().removeprefix('TR'), 'iban': normalize_iban(s.partner_bank_id.account_number),
                'tutar': round(s.tutar, 2), 'para': self.currency_id.name, 'aciklama': (s.aciklama or self.aciklama or self.name)[:140],
                'tarih': self.tarih.strftime('%d.%m.%Y'),
            })
        return satirlar

    BASLIKLAR = [('sira', 'Sıra'), ('alici', 'Alıcı Adı / Unvanı'), ('vkn', 'VKN / TCKN'), ('iban', 'IBAN'),
                 ('tutar', 'Tutar'), ('para', 'Para Birimi'), ('aciklama', 'Açıklama'), ('tarih', 'Ödeme Tarihi')]

    def _xlsx(self):
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet('Talimat')
        kalin = wb.add_format({'bold': True, 'bg_color': '#E5E7EB'})
        para = wb.add_format({'num_format': '#,##0.00'})
        for c, (_k, baslik) in enumerate(self.BASLIKLAR):
            ws.write(0, c, baslik, kalin)
        for r, s in enumerate(self._dosya_satirlari(), start=1):
            for c, (k, _b) in enumerate(self.BASLIKLAR):
                ws.write(r, c, s[k], para if k == 'tutar' else None)
        ws.set_column(1, 1, 36)
        ws.set_column(3, 3, 32)
        ws.set_column(6, 6, 40)
        wb.close()
        return buf.getvalue()

    def _csv(self):
        buf = io.StringIO()
        yazici = csv.writer(buf, delimiter=';')
        yazici.writerow([b for _k, b in self.BASLIKLAR])
        for s in self._dosya_satirlari():
            yazici.writerow([f'{s[k]:.2f}'.replace('.', ',') if k == 'tutar' else s[k] for k, _b in self.BASLIKLAR])
        return buf.getvalue().encode('utf-8-sig')

    def _dosya(self, tur):
        self.ensure_one()
        if self.durum == 'taslak':
            raise UserError(self.env._('Banka dosyası onaylanmış talimattan alınır.'))
        icerik = self._xlsx() if tur == 'xlsx' else self._csv()
        ad = f'{self.name}.{tur}'
        ek = self.env['ir.attachment'].create({'name': ad, 'raw': icerik, 'res_model': self._name, 'res_id': self.id})
        if self.durum == 'onaylandi':
            self.durum = 'gonderildi'
        return {'type': 'ir.actions.act_url', 'target': 'self', 'url': f'/web/content/{ek.id}?download=true'}

    def action_xlsx(self):
        return self._dosya('xlsx')

    def action_csv(self):
        return self._dosya('csv')

    def action_odemeler(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.payment', 'name': self.name,
                'view_mode': 'list,form', 'domain': [('atlas_talimat_id', '=', self.id)]}


class AtlasOdemeTalimatSatir(models.Model):
    _name = 'atlas.odeme.talimat.satir'
    _description = 'Ödeme Talimatı Satırı'
    _order = 'talimat_id, id'

    talimat_id = fields.Many2one('atlas.odeme.talimat', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='talimat_id.company_id')
    currency_id = fields.Many2one(related='talimat_id.currency_id')
    partner_id = fields.Many2one('res.partner', string='Cari', required=True)
    partner_bank_id = fields.Many2one('res.partner.bank', string='IBAN', compute='_compute_partner_bank', store=True, readonly=False,
                                      domain="[('partner_id', 'in', (partner_id, commercial_partner_id))]")
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id')
    move_ids = fields.Many2many('account.move', string='Faturalar', domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), "
                                                                         "('payment_state', 'in', ('not_paid', 'partial')), "
                                                                         "('commercial_partner_id', '=', commercial_partner_id)]")
    acik_bakiye = fields.Monetary(string='Açık Bakiye', compute='_compute_acik')
    tutar = fields.Monetary(string='Ödenecek Tutar', required=True)
    aciklama = fields.Char(string='Açıklama')
    payment_id = fields.Many2one('account.payment', string='Ödeme', readonly=True, copy=False)
    payment_durum = fields.Selection(related='payment_id.state', string='Ödeme Durumu')
    eslesti = fields.Boolean(related='payment_id.is_matched', string='Bankada')

    @api.depends('partner_id', 'move_ids')
    def _compute_partner_bank(self):
        for satir in self:
            if satir.partner_bank_id and satir.partner_bank_id.partner_id.commercial_partner_id == satir.commercial_partner_id:
                continue
            banka = satir.move_ids.partner_bank_id[:1] or satir.commercial_partner_id.bank_ids[:1] or satir.partner_id.bank_ids[:1]
            satir.partner_bank_id = banka

    @api.depends('move_ids.amount_residual')
    def _compute_acik(self):
        for satir in self:
            satir.acik_bakiye = sum(satir.move_ids.mapped('amount_residual'))

    @api.onchange('move_ids')
    def _onchange_move_ids(self):
        if self.move_ids:
            self.tutar = sum(self.move_ids.mapped('amount_residual'))
            if not self.aciklama:
                self.aciklama = ', '.join(self.move_ids.mapped(lambda m: m.ref or m.name))[:140]


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    atlas_talimat_id = fields.Many2one('atlas.odeme.talimat', string='Ödeme Talimatı', index='btree_not_null', copy=False, readonly=True)


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def action_atlas_eslestir(self):
        """Ekstre satırı eşleşince bağlı ödeme talimatının durumu güncellenir."""
        odemeler = self.atlas_bekleyen_line_id.payment_id
        res = super().action_atlas_eslestir()
        (odemeler | self.atlas_bekleyen_line_id.payment_id).atlas_talimat_id._durum_guncelle()
        return res
