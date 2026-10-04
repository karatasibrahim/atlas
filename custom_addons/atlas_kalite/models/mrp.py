from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    atlas_kalite_kontrol_ids = fields.One2many('atlas.kalite.kontrol', 'production_id', string='Kalite Kontrolleri')
    atlas_kalite_bekleyen = fields.Integer(compute='_compute_atlas_kalite', string='Bekleyen Kontrol')
    atlas_kalite_sayisi = fields.Integer(compute='_compute_atlas_kalite', string='Kalite Kontrolü')
    atlas_uyari_sayisi = fields.Integer(compute='_compute_atlas_kalite', string='Uygunsuzluk')

    @api.depends('atlas_kalite_kontrol_ids.durum')
    def _compute_atlas_kalite(self):
        uyari = dict(self.env['atlas.kalite.uyari']._read_group(
            [('production_id', 'in', self.ids)], ['production_id'], ['__count']))
        for production in self:
            kontroller = production.atlas_kalite_kontrol_ids
            production.atlas_kalite_sayisi = len(kontroller)
            production.atlas_kalite_bekleyen = len(kontroller.filtered(lambda k: k.durum == 'bekliyor'))
            production.atlas_uyari_sayisi = uyari.get(production, 0)

    def _atlas_kalite_hedefler(self):
        self.ensure_one()
        if self.lot_producing_ids:
            return [(self.product_id, lot, lot.name) for lot in self.lot_producing_ids]
        return [(self.product_id, False, False)]

    def _atlas_kalite_olustur(self):
        """Final (üretim emri) ve ara (iş emri) kontrollerini oluşturur."""
        Kontrol = self.env['atlas.kalite.kontrol']
        Nokta = self.env['atlas.kalite.nokta']
        for production in self:
            if production.state in ('draft', 'done', 'cancel'):
                continue
            hedefler = production._atlas_kalite_hedefler()
            mevcut = production.atlas_kalite_kontrol_ids
            finaller = Nokta._noktalar('final', production.company_id, picking_type=production.picking_type_id)
            Kontrol._uret(finaller, {'production_id': production.id, 'company_id': production.company_id.id},
                          mevcut.filtered(lambda k: not k.workorder_id), hedefler, f'mo:{production.id}')
            for workorder in production.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
                aralar = Nokta._noktalar('ara', production.company_id, picking_type=production.picking_type_id,
                                         workorder=workorder)
                Kontrol._uret(aralar, {'production_id': production.id, 'workorder_id': workorder.id,
                                       'company_id': production.company_id.id},
                              mevcut.filtered(lambda k: k.workorder_id == workorder), hedefler, f'wo:{workorder.id}')

    def action_confirm(self):
        res = super().action_confirm()
        self._atlas_kalite_olustur()
        return res

    def pre_button_mark_done(self):
        if not self.env.context.get('atlas_kalite_atla'):
            self._atlas_kalite_olustur()
            for production in self:
                production.atlas_kalite_kontrol_ids._engel_kontrol(production.name)
        return super().pre_button_mark_done()

    def action_cancel(self):
        res = super().action_cancel()
        self.atlas_kalite_kontrol_ids.filtered(lambda k: k.durum == 'bekliyor').unlink()
        return res

    def action_atlas_kalite_kontrolleri(self):
        self.ensure_one()
        self._atlas_kalite_olustur()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_kontrol')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {'default_production_id': self.id, 'search_default_filter_bekliyor': 0}
        return action

    def action_atlas_uyarilar(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_uyari')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {'default_production_id': self.id, 'default_product_id': self.product_id.id}
        return action


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    atlas_kalite_kontrol_ids = fields.One2many('atlas.kalite.kontrol', 'workorder_id', string='Kalite Kontrolleri')
    atlas_kalite_bekleyen = fields.Integer(compute='_compute_atlas_kalite_bekleyen', string='Bekleyen Kontrol')

    @api.depends('atlas_kalite_kontrol_ids.durum')
    def _compute_atlas_kalite_bekleyen(self):
        for workorder in self:
            workorder.atlas_kalite_bekleyen = len(workorder.atlas_kalite_kontrol_ids.filtered(lambda k: k.durum == 'bekliyor'))

    def button_finish(self):
        if not self.env.context.get('atlas_kalite_atla'):
            acik = self.filtered(lambda w: w.state not in ('done', 'cancel'))
            acik.production_id._atlas_kalite_olustur()
            for workorder in acik:
                workorder.atlas_kalite_kontrol_ids._engel_kontrol(f'{workorder.production_id.name} / {workorder.name}')
        return super().button_finish()

    def action_atlas_kalite_kontrolleri(self):
        self.ensure_one()
        self.production_id._atlas_kalite_olustur()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_kontrol')
        action['domain'] = [('workorder_id', '=', self.id)]
        action['context'] = {'default_workorder_id': self.id, 'default_production_id': self.production_id.id}
        return action
