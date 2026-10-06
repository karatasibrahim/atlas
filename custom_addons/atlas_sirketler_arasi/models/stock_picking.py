from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        sonuc = super()._action_done()
        for teslimat in self.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state == 'done'):
            try:
                teslimat._sa_lot_aktar()
            except Exception as e:  # lot aktarımı teslimatı engellememeli
                teslimat.message_post(body=self.env._('Şirketler arası lot aktarımı yapılamadı: %s', e))
        return sonuc

    def _sa_karsi_alimlar(self):
        """Bu teslimatın karşı şirketteki bekleyen mal kabulleri."""
        self.ensure_one()
        siparis = self.sale_id.sudo() if 'sale_id' in self._fields else self.env['sale.order']
        if not siparis:
            return self.env['stock.picking']
        satin_almalar = siparis.sa_satin_alma_ids | siparis.sa_kaynak_satin_alma_id
        return satin_almalar.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel'))

    def _sa_lot_aktar(self):
        """Gönderen şirketin teslim ettiği lot / seri numaralarını alıcı şirketin mal kabulüne yazar (lot yoksa açılır)."""
        self.ensure_one()
        alimlar = self._sa_karsi_alimlar()
        if not alimlar:
            return
        Lot = self.env['stock.lot'].sudo()
        aktarilan = 0
        for ml in self.move_line_ids.filtered(lambda l: l.lot_id and l.quantity):
            urun = ml.product_id
            hareket = alimlar.move_ids.filtered(lambda m: m.product_id == urun and m.state not in ('done', 'cancel'))[:1]
            if not hareket or urun.tracking == 'none':
                continue
            sirket = hareket.company_id
            lot = Lot.search([('name', '=', ml.lot_id.name), ('product_id', '=', urun.id), ('company_id', 'in', (sirket.id, False))], limit=1)
            if not lot:
                lot = Lot.create({'name': ml.lot_id.name, 'product_id': urun.id, 'company_id': sirket.id})
            bos = hareket.move_line_ids.filtered(lambda l: not l.lot_id and not l.lot_name)[:1]
            degerler = {'lot_id': lot.id, 'quantity': ml.quantity}
            if bos:
                bos.sudo().write(degerler)
            else:
                self.env['stock.move.line'].sudo().create(dict(degerler, move_id=hareket.id, product_id=urun.id,
                                                               picking_id=hareket.picking_id.id, company_id=sirket.id,
                                                               location_id=hareket.location_id.id, location_dest_id=hareket.location_dest_id.id,
                                                               uom_id=hareket.uom_id.id))
            aktarilan += 1
        if aktarilan:
            alimlar.sudo().message_post(body=self.env._('Lot / seri numaraları %(sirket)s şirketinin %(belge)s teslimatından aktarıldı.',
                                                        sirket=self.company_id.name, belge=self.name))
