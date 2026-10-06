from odoo import fields, models
from odoo.fields import Command


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    sa_kaynak_satis_id = fields.Many2one('sale.order', string='Şirketler Arası Kaynak', copy=False, readonly=True, index='btree_not_null')
    sa_satis_ids = fields.One2many('sale.order', 'sa_kaynak_satin_alma_id', string='Şirketler Arası Satış')

    def button_confirm(self):
        sonuc = super().button_confirm()
        if not self.env.context.get('atlas_sa_olusturuldu'):
            for siparis in self.filtered(lambda p: p.state in ('purchase', 'done') and not p.sa_kaynak_satis_id and not p.sa_satis_ids):
                hedef = self.env['res.company']._sa_hedef(siparis.partner_id, siparis.company_id)
                if hedef and hedef.sa_satis_olustur:
                    siparis._sa_satis_olustur(hedef)
        return sonuc

    def _sa_satis_olustur(self, hedef):
        """Grup şirketinden satın alma → karşı şirkette satış siparişi."""
        self.ensure_one()
        env = hedef._sa_ortam()
        depo = hedef._sa_depo(env)
        liste = env['product.pricelist'].search([('currency_id', '=', self.currency_id.id),
                                                 ('company_id', 'in', (hedef.id, False))], limit=1)
        if not liste:
            liste = env['product.pricelist'].create({'name': self.currency_id.name, 'currency_id': self.currency_id.id, 'company_id': hedef.id})
        satirlar = []
        for s in self.order_line:
            if s.display_type:
                satirlar.append(Command.create({'display_type': s.display_type, 'name': s.name}))
                continue
            satirlar.append(Command.create({
                'product_id': s.product_id.id, 'name': s.name, 'product_uom_qty': s.product_qty, 'product_uom_id': s.uom_id.id,
                'price_unit': s.price_unit,
                'tax_ids': [Command.set(hedef._sa_vergiler(s.tax_ids, s.product_id, 'sale').ids)],
                'sa_kaynak_satin_alma_satir_id': s.id,
            }))
        so = env['sale.order'].create({
            'partner_id': self.company_id.partner_id.id,
            'pricelist_id': liste.id,
            'client_order_ref': self.name,
            'origin': self.name,
            'warehouse_id': depo.id if depo else False,
            'commitment_date': self.date_planned,
            'sa_kaynak_satin_alma_id': self.id,
            'order_line': satirlar,
        })
        # liste fiyatları yeniden hesaplanmış olabilir: satın alma fiyatı esas alınır
        for so_satir, po_satir in zip(so.order_line.filtered(lambda l: not l.display_type), self.order_line.filtered(lambda l: not l.display_type)):
            so_satir.price_unit = po_satir.price_unit
        if hedef.sa_otomatik_onay:
            so.action_confirm()
        self.sudo().message_post(body=self.env._('Şirketler arası satış siparişi oluşturuldu: %(sirket)s / %(belge)s',
                                                 sirket=hedef.name, belge=so.name))
        return so


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    sa_kaynak_satis_satir_id = fields.Many2one('sale.order.line', string='Şirketler Arası Satış Satırı', copy=False, index='btree_not_null')
