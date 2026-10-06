from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

DURUMLAR = [('evet', 'Ödenebilir'), ('hayir', 'Teslimat bekleniyor'), ('istisna', 'İstisna')]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    ucyol_durum = fields.Selection(DURUMLAR, string='3\'lü Eşleştirme', compute='_compute_ucyol_durum', store=True)
    ucyol_aciklama = fields.Char(string='Eşleştirme Notu', compute='_compute_ucyol_durum', store=True)

    @api.depends('purchase_line_id.qty_received', 'purchase_line_id.qty_invoiced', 'purchase_line_id.product_qty',
                 'purchase_line_id.price_unit', 'quantity', 'price_unit', 'product_uom_id', 'move_id.move_type', 'move_id.state',
                 'move_id.company_id.ucyol_fiyat_tolerans', 'move_id.company_id.ucyol_miktar_tolerans')
    def _compute_ucyol_durum(self):
        for s in self:
            s.ucyol_durum, s.ucyol_aciklama = s._ucyol_degerlendir()

    def _ucyol_degerlendir(self):
        self.ensure_one()
        hat = self.purchase_line_id
        fatura = self.move_id
        if fatura.move_type not in ('in_invoice', 'in_refund') or self.display_type != 'product' or not hat:
            return False, False
        sirket = fatura.company_id
        uom = hat.uom_id
        basamak = self.env['decimal.precision'].precision_get('Product Unit')
        isaret = -1 if fatura.move_type == 'in_refund' else 1
        miktar = self.product_uom_id._compute_quantity(self.quantity, uom) * isaret if self.product_uom_id and uom else self.quantity * isaret
        # bu fatura dışında onaylanmış faturalarda faturalanan miktar
        diger = 0.0
        for d in hat.invoice_lines.filtered(lambda l: l.move_id.state == 'posted' and l.move_id != fatura):
            d_isaret = -1 if d.move_id.move_type == 'in_refund' else 1
            diger += (d.product_uom_id._compute_quantity(d.quantity, uom) if d.product_uom_id and uom else d.quantity) * d_isaret
        toplam = diger + miktar
        sinir = hat.product_qty * (1 + (sirket.ucyol_miktar_tolerans or 0.0) / 100.0)
        if float_compare(toplam, sinir, precision_digits=basamak) > 0:
            return 'istisna', self.env._('Faturalanan %(toplam)s > sipariş %(siparis)s', toplam=round(toplam, 4), siparis=hat.product_qty)
        fiyat = self.price_unit
        if self.product_uom_id and uom and self.product_uom_id != uom:
            fiyat = self.product_uom_id._compute_price(fiyat, uom)
        if fatura.currency_id != hat.currency_id:
            fiyat = fatura.currency_id._convert(fiyat, hat.currency_id, sirket, fatura.invoice_date or fields.Date.today())
        tolerans = abs(hat.price_unit) * (sirket.ucyol_fiyat_tolerans or 0.0) / 100.0
        if abs(fiyat - hat.price_unit) > tolerans + hat.currency_id.rounding:
            return 'istisna', self.env._('Birim fiyat %(fatura)s ≠ sipariş %(siparis)s', fatura=round(fiyat, 4), siparis=hat.price_unit)
        if hat.product_id.purchase_method == 'purchase' and hat.product_id.type == 'service':
            return 'evet', False
        if float_compare(toplam, hat.qty_received, precision_digits=basamak) > 0:
            return 'hayir', self.env._('Teslim alınan %(alinan)s < faturalanan %(toplam)s', alinan=hat.qty_received, toplam=round(toplam, 4))
        return 'evet', False


class AccountMove(models.Model):
    _inherit = 'account.move'

    ucyol_durum = fields.Selection(DURUMLAR, string='Ödemeye Uygunluk', compute='_compute_ucyol', store=True, tracking=True,
                                   help='Satın alma siparişi, mal kabul ve fatura eşleştirmesinin sonucu (elle değiştirilebilir)')
    ucyol_hesaplanan = fields.Selection(DURUMLAR, string='Hesaplanan Durum', compute='_compute_ucyol', store=True)
    ucyol_elle = fields.Selection([('evet', 'Serbest bırakıldı'), ('hayir', 'Bekletiliyor')], string='Elle Karar', copy=False, tracking=True)
    ucyol_siparisli = fields.Boolean(string='Siparişe Bağlı', compute='_compute_ucyol', store=True)

    @api.depends('invoice_line_ids.ucyol_durum', 'ucyol_elle', 'move_type')
    def _compute_ucyol(self):
        for m in self:
            if m.move_type not in ('in_invoice', 'in_refund'):
                m.ucyol_durum = m.ucyol_hesaplanan = False
                m.ucyol_siparisli = False
                continue
            durumlar = set(m.invoice_line_ids.mapped('ucyol_durum')) - {False}
            m.ucyol_siparisli = bool(durumlar)
            hesap = 'istisna' if 'istisna' in durumlar else 'hayir' if 'hayir' in durumlar else 'evet'
            m.ucyol_hesaplanan = hesap
            m.ucyol_durum = m.ucyol_elle or hesap

    def action_ucyol_serbest(self):
        self._ucyol_elle('evet')

    def action_ucyol_beklet(self):
        self._ucyol_elle('hayir')

    def action_ucyol_otomatik(self):
        self.write({'ucyol_elle': False})

    def _ucyol_elle(self, karar):
        for m in self:
            if m.move_type not in ('in_invoice', 'in_refund'):
                raise UserError(self.env._('Yalnız tedarikçi faturaları için geçerlidir.'))
            m.ucyol_elle = karar
            m.message_post(body=self.env._('3\'lü eşleştirme: %(karar)s (hesaplanan: %(hesap)s)',
                                           karar=dict(self._fields['ucyol_elle'].selection)[karar],
                                           hesap=dict(DURUMLAR).get(m.ucyol_hesaplanan, '-')))

    def _ucyol_odeme_kontrol(self):
        engelli = self.filtered(lambda m: m.move_type in ('in_invoice', 'in_refund') and m.company_id.ucyol_odeme_engeli
                                and m.ucyol_durum != 'evet')
        if engelli:
            raise UserError(self.env._('Şu faturalar 3\'lü eşleştirmede ödenebilir değil: %s. Mal kabulü bekleyin ya da '
                                       'faturayı elle ödemeye serbest bırakın.', ', '.join(engelli.mapped('name'))))

    def action_register_payment(self):
        self._ucyol_odeme_kontrol()
        return super().action_register_payment()


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        self.line_ids.move_id._ucyol_odeme_kontrol()
        return super()._create_payments()
