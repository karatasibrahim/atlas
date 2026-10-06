from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sa_kaynak_satin_alma_id = fields.Many2one('purchase.order', string='Şirketler Arası Kaynak', copy=False, readonly=True,
                                              index='btree_not_null')
    sa_satin_alma_ids = fields.One2many('purchase.order', 'sa_kaynak_satis_id', string='Şirketler Arası Satın Alma')

    def _action_confirm(self):
        sonuc = super()._action_confirm()
        if not self.env.context.get('atlas_sa_olusturuldu'):
            for siparis in self.filtered(lambda s: not s.sa_kaynak_satin_alma_id and not s.sa_satin_alma_ids):
                hedef = self.env['res.company']._sa_hedef(siparis.partner_id, siparis.company_id)
                if hedef and hedef.sa_satin_alma_olustur:
                    siparis._sa_satin_alma_olustur(hedef)
        return sonuc

    def _sa_satin_alma_olustur(self, hedef):
        """Grup şirketine satış → karşı şirkette satın alma siparişi."""
        self.ensure_one()
        env = hedef._sa_ortam()
        depo = hedef.sa_depo_id or env['stock.warehouse'].search([('company_id', '=', hedef.id)], limit=1)
        if not depo:
            raise UserError(self.env._('Şirketler arası satın alma siparişi için %s şirketinde depo tanımlı değil.', hedef.name))
        satirlar = []
        for s in self.order_line:
            if s.display_type:
                satirlar.append(Command.create({'display_type': s.display_type, 'name': s.name}))
                continue
            urun = s.product_id
            satirlar.append(Command.create({
                'product_id': urun.id, 'name': s.name, 'product_qty': s.product_uom_qty, 'uom_id': s.product_uom_id.id,
                'price_unit': s.price_unit * (1 - (s.discount or 0.0) / 100.0),
                'date_planned': s.order_id.commitment_date or fields.Datetime.now(),
                'tax_ids': [Command.set(hedef._sa_vergiler(s.tax_ids, urun, 'purchase').ids)],
            }))
        po = env['purchase.order'].create({
            'partner_id': self.company_id.partner_id.id,
            'currency_id': self.currency_id.id,
            'partner_ref': self.name,
            'origin': self.name,
            'picking_type_id': depo.in_type_id.id if depo else False,
            'sa_kaynak_satis_id': self.id,
            'order_line': satirlar,
        })
        if hedef.sa_otomatik_onay:
            po.button_confirm()
        self.sudo().message_post(body=self.env._('Şirketler arası satın alma siparişi oluşturuldu: %(sirket)s / %(belge)s',
                                                 sirket=hedef.name, belge=po.name))
        return po
