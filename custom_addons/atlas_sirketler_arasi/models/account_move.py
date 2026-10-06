from odoo import fields, models
from odoo.fields import Command

KARSILIK = {'out_invoice': 'in_invoice', 'out_refund': 'in_refund', 'in_invoice': 'out_invoice', 'in_refund': 'out_refund'}


class AccountMove(models.Model):
    _inherit = 'account.move'

    sa_kaynak_fatura_id = fields.Many2one('account.move', string='Şirketler Arası Kaynak', copy=False, readonly=True, index='btree_not_null')
    sa_karsilik_ids = fields.One2many('account.move', 'sa_kaynak_fatura_id', string='Şirketler Arası Karşılık')

    def _post(self, soft=True):
        sonuc = super()._post(soft)
        if not self.env.context.get('atlas_sa_olusturuldu'):
            for fatura in sonuc.filtered(lambda m: m.move_type in KARSILIK and not m.sa_kaynak_fatura_id and not m.sa_karsilik_ids):
                hedef = self.env['res.company']._sa_hedef(fatura.partner_id, fatura.company_id)
                if hedef and hedef.sa_fatura:
                    fatura._sa_karsilik_olustur(hedef)
        return sonuc

    def _sa_karsilik_olustur(self, hedef):
        self.ensure_one()
        env = hedef._sa_ortam()
        tur = KARSILIK[self.move_type]
        satis_mi = tur in ('out_invoice', 'out_refund')
        vergi_tipi = 'sale' if satis_mi else 'purchase'
        satirlar = []
        for s in self.invoice_line_ids:
            if s.display_type in ('line_section', 'line_note'):
                satirlar.append(Command.create({'display_type': s.display_type, 'name': s.name}))
                continue
            if s.display_type != 'product':
                continue
            urun = s.product_id.sudo()
            if urun and urun.company_id and urun.company_id != hedef:
                urun = env['product.product']
            po_satir = self._sa_po_satiri(s, hedef) if not satis_mi else self.env['purchase.order.line']
            so_satir = self._sa_so_satiri(s, hedef) if satis_mi else self.env['sale.order.line']
            satirlar.append(Command.create({
                'purchase_line_id': po_satir.id or False,
                'sale_line_ids': [Command.set(so_satir.ids)],
                'product_id': urun.id or False, 'name': s.name, 'quantity': s.quantity, 'price_unit': s.price_unit,
                'discount': s.discount, 'product_uom_id': s.product_uom_id.id,
                'tax_ids': [Command.set(hedef._sa_vergiler(s.tax_ids, urun, vergi_tipi).ids)],
            }))
        karsilik_po = self.env['purchase.order']
        if not satis_mi:
            karsilik_po = self._sa_karsilik_po(hedef)
        karsilik = env['account.move'].create({
            'move_type': tur,
            'partner_id': self.company_id.partner_id.id,
            'invoice_date': self.invoice_date,
            'invoice_date_due': self.invoice_date_due,
            'currency_id': self.currency_id.id,
            'ref': self.name,
            'invoice_origin': karsilik_po.name or self.invoice_origin or self.name,
            'sa_kaynak_fatura_id': self.id,
            'invoice_line_ids': satirlar,
        })
        karsilik.message_post(body=self.env._('Şirketler arası: %(sirket)s şirketinin %(belge)s belgesinden oluşturuldu.',
                                              sirket=self.company_id.name, belge=self.name))
        if hedef.sa_fatura_durum == 'onayli':
            karsilik.action_post()
        self.sudo().message_post(body=self.env._('Şirketler arası karşılık oluşturuldu: %(sirket)s / %(belge)s',
                                                 sirket=hedef.name, belge=karsilik.name or karsilik.display_name))
        return karsilik

    def _sa_karsilik_po(self, hedef):
        satis_satirlari = self.invoice_line_ids.sale_line_ids.sudo()
        po_satirlari = self.env['purchase.order.line'].sudo().search([('sa_kaynak_satis_satir_id', 'in', satis_satirlari.ids)])
        po_satirlari |= satis_satirlari.sa_kaynak_satin_alma_satir_id
        return po_satirlari.order_id.filtered(lambda p: p.company_id == hedef)[:1]

    def _sa_so_satiri(self, satir, hedef):
        """Tedarikçi faturası satırının karşı şirketteki satış satırı (karşı şirkette kesilen müşteri faturası için)."""
        SO = self.env['sale.order.line'].sudo()
        pol = satir.purchase_line_id.sudo()
        if not pol:
            return SO
        bagli = SO.search([('sa_kaynak_satin_alma_satir_id', '=', pol.id), ('company_id', '=', hedef.id)], limit=1)
        if bagli:
            return bagli
        return pol.sa_kaynak_satis_satir_id if pol.sa_kaynak_satis_satir_id.company_id == hedef else SO

    def _sa_po_satiri(self, satir, hedef):
        """Fatura satırının karşı şirketteki satın alma satırı (3'lü eşleştirme ve faturalanan miktar için).

        - Bu şirketin satışı karşı şirkette satın alma doğurduysa: o satın alma satırı
        - Bu şirketin satışı karşı şirketin satın almasından doğduysa: kaynak satın alma satırı
        """
        PO = self.env['purchase.order.line'].sudo()
        for s in satir.sale_line_ids.sudo():
            bagli = PO.search([('sa_kaynak_satis_satir_id', '=', s.id), ('company_id', '=', hedef.id)], limit=1)
            if bagli:
                return bagli
            if s.sa_kaynak_satin_alma_satir_id.company_id == hedef:
                return s.sa_kaynak_satin_alma_satir_id
        return PO
