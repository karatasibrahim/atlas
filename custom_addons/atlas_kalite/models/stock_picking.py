from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    atlas_kalite_kontrol_ids = fields.One2many('atlas.kalite.kontrol', 'picking_id', string='Kalite Kontrolleri')
    atlas_kalite_bekleyen = fields.Integer(compute='_compute_atlas_kalite', string='Bekleyen Kontrol')
    atlas_kalite_sayisi = fields.Integer(compute='_compute_atlas_kalite', string='Kalite Kontrolü')
    atlas_kalite_durum = fields.Selection(
        [('yok', 'Kontrol yok'), ('bekliyor', 'Kontrol bekliyor'), ('gecti', 'Geçti'), ('kaldi', 'Kaldı')],
        compute='_compute_atlas_kalite', string='Kalite')
    atlas_uyari_sayisi = fields.Integer(compute='_compute_atlas_kalite', string='Uygunsuzluk')

    @api.depends('atlas_kalite_kontrol_ids.durum')
    def _compute_atlas_kalite(self):
        uyari = dict(self.env['atlas.kalite.uyari']._read_group(
            [('picking_id', 'in', self.ids)], ['picking_id'], ['__count']))
        for picking in self:
            kontroller = picking.atlas_kalite_kontrol_ids
            picking.atlas_kalite_sayisi = len(kontroller)
            picking.atlas_kalite_bekleyen = len(kontroller.filtered(lambda k: k.durum == 'bekliyor'))
            if not kontroller:
                picking.atlas_kalite_durum = 'yok'
            elif picking.atlas_kalite_bekleyen:
                picking.atlas_kalite_durum = 'bekliyor'
            else:
                picking.atlas_kalite_durum = 'kaldi' if 'kaldi' in kontroller.mapped('durum') else 'gecti'
            picking.atlas_uyari_sayisi = uyari.get(picking, 0)

    def _atlas_kalite_asama(self):
        self.ensure_one()
        return {'incoming': 'giris', 'outgoing': 'sevkiyat'}.get(self.picking_type_code)

    def _atlas_kalite_olustur(self):
        """Kontrol noktalarına göre eksik kalite kontrollerini oluşturur."""
        Kontrol = self.env['atlas.kalite.kontrol']
        for picking in self:
            asama = picking._atlas_kalite_asama()
            if not asama or picking.state in ('draft', 'done', 'cancel'):
                continue
            noktalar = self.env['atlas.kalite.nokta']._noktalar(
                asama, picking.company_id, picking_type=picking.picking_type_id, partner=picking.partner_id)
            if not noktalar:
                continue
            hedefler = []
            for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                lotlu = [(ml.lot_id, ml.lot_id.name or ml.lot_name) for ml in move.move_line_ids
                         if ml.quantity and (ml.lot_id or ml.lot_name)]
                # Okutma başlamadıysa (picked değil) rezervasyon satırları kesin lot sayılmaz
                if lotlu and (move.picked or asama == 'giris'):
                    hedefler += [(move.product_id, lot, name) for lot, name in lotlu]
                else:
                    hedefler.append((move.product_id, False, False))
            Kontrol._uret(noktalar, {'picking_id': picking.id, 'company_id': picking.company_id.id},
                          picking.atlas_kalite_kontrol_ids, hedefler, f'picking:{picking.id}')

    def _pre_action_done_hook(self):
        if not self.env.context.get('atlas_kalite_atla'):
            self._atlas_kalite_olustur()
            for picking in self:
                picking.atlas_kalite_kontrol_ids._engel_kontrol(picking.name)
        return super()._pre_action_done_hook()

    def action_cancel(self):
        res = super().action_cancel()
        self.atlas_kalite_kontrol_ids.filtered(lambda k: k.durum == 'bekliyor').unlink()
        return res

    def action_atlas_kalite_kontrolleri(self):
        self.ensure_one()
        self._atlas_kalite_olustur()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_kontrol')
        action['domain'] = [('picking_id', '=', self.id)]
        action['context'] = {'default_picking_id': self.id, 'search_default_filter_bekliyor': 0}
        return action

    def action_atlas_uyarilar(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_uyari')
        action['domain'] = [('picking_id', '=', self.id)]
        action['context'] = {'default_picking_id': self.id, 'default_partner_id': self.partner_id.commercial_partner_id.id}
        return action


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_confirm(self, merge=True, merge_into=False, create_proc=True):
        moves = super()._action_confirm(merge=merge, merge_into=merge_into, create_proc=create_proc)
        moves.picking_id._atlas_kalite_olustur()
        return moves
