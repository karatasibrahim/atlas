from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    atlas_versiyon = fields.Integer(string='Sürüm', default=1, copy=False, tracking=True,
                                    help='Uygulanan son mühendislik değişikliğiyle artar.')
    atlas_eco_sayisi = fields.Integer(compute='_compute_atlas_eco_sayisi', string='Değişiklik')

    def _compute_atlas_eco_sayisi(self):
        data = dict(self.env['atlas.plm.eco']._read_group([('product_tmpl_id', 'in', self.ids)], ['product_tmpl_id'], ['__count']))
        for tmpl in self:
            tmpl.atlas_eco_sayisi = data.get(tmpl, 0)

    def action_atlas_ecolar(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_plm.action_atlas_plm_eco')
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {'default_product_tmpl_id': self.id}
        return action


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    atlas_versiyon = fields.Integer(string='Sürüm', default=1, copy=False)
    atlas_onceki_bom_id = fields.Many2one('mrp.bom', string='Önceki Sürüm', copy=False, readonly=True, index=True)
    atlas_eco_ids = fields.One2many('atlas.plm.eco', 'bom_id', string='Değişiklikler')
    atlas_eco_sayisi = fields.Integer(compute='_compute_atlas_plm', string='Değişiklik')
    atlas_surum_sayisi = fields.Integer(compute='_compute_atlas_plm', string='Sürüm Sayısı')
    atlas_revizyon_eco_id = fields.Many2one('atlas.plm.eco', compute='_compute_atlas_plm', string='Revizyonu Hazırlayan ECO')

    def _compute_atlas_plm(self):
        Eco = self.env['atlas.plm.eco']
        for bom in self:
            bom.atlas_eco_sayisi = Eco.search_count(['|', ('bom_id', '=', bom.id), ('yeni_bom_id', '=', bom.id)]) if bom.id else 0
            bom.atlas_surum_sayisi = len(bom._atlas_surumler())
            bom.atlas_revizyon_eco_id = Eco.search([('yeni_bom_id', '=', bom.id)], limit=1) if bom.id else Eco

    def _atlas_surumler(self):
        """Bu reçetenin önceki ve sonraki tüm sürümleri (kendisi dahil)."""
        self.ensure_one()
        if not self.id:
            return self
        Bom = self.with_context(active_test=False)
        surumler = Bom.browse(self.id)
        sinir = Bom.browse(self.id)
        while sinir:
            yeni = Bom.search([('atlas_onceki_bom_id', 'in', sinir.ids), ('id', 'not in', surumler.ids)])
            yeni |= sinir.atlas_onceki_bom_id - surumler
            surumler |= yeni
            sinir = yeni
        return surumler

    def _atlas_revizyon_kopyala(self):
        """Taslak (arşivli) revizyon kopyası; operasyonlar aktif kalır ki düzenlenebilsin."""
        self.ensure_one()
        yeni = self.copy({'active': False, 'atlas_versiyon': self.atlas_versiyon + 1, 'atlas_onceki_bom_id': self.id})
        for eski_op, yeni_op in zip(self.operation_ids, yeni.operation_ids.sorted()):
            yeni_op.atlas_onceki_operation_id = eski_op
        return yeni

    def _atlas_bagli_kayitlari_tasi(self, eski):
        """Uygulamada eski reçeteye bağlı kayıtları yeni sürüme taşır."""
        self.ensure_one()
        Orderpoint = self.env['stock.warehouse.orderpoint'].with_context(active_test=False)
        if 'bom_id' in Orderpoint._fields:
            Orderpoint.search([('bom_id', '=', eski.id)]).bom_id = self
        # Kalite kontrol noktalarındaki operasyon filtreleri yeni operasyonlara genişletilir
        if 'atlas.kalite.nokta' in self.env:
            Nokta = self.env['atlas.kalite.nokta'].with_context(active_test=False)
            for op in self.operation_ids.filtered('atlas_onceki_operation_id'):
                for nokta in Nokta.search([('operation_ids', 'in', op.atlas_onceki_operation_id.ids)]):
                    nokta.operation_ids = [(4, op.id)]

    @api.model_create_multi
    def create(self, vals_list):
        boms = super().create(vals_list)
        boms._atlas_eco_guncelle()
        return boms

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('atlas_plm_hesapla'):
            self._atlas_eco_guncelle()
        return res

    def _atlas_eco_guncelle(self):
        if self.env.context.get('atlas_plm_hesapla') or not self:
            return
        ecolar = self.env['atlas.plm.eco'].sudo().search(['|', ('yeni_bom_id', 'in', self.ids), ('bom_id', 'in', self.ids),
                                                          ('durum', '=', 'islemde')])
        ecolar._degisiklik_hesapla()

    def action_atlas_eco_baslat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'atlas.plm.eco', 'view_mode': 'form', 'target': 'current',
            'context': {'default_product_tmpl_id': self.product_tmpl_id.id, 'default_bom_id': self.id,
                        'default_uygulama': 'bom', 'default_tip_id': self.env.ref('atlas_plm.tip_revizyon', raise_if_not_found=False).id or False},
        }

    def action_atlas_ecolar(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_plm.action_atlas_plm_eco')
        action['domain'] = ['|', ('bom_id', '=', self.id), ('yeni_bom_id', '=', self.id)]
        action['context'] = {'default_bom_id': self.id, 'default_product_tmpl_id': self.product_tmpl_id.id}
        return action

    def action_atlas_surumler(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'mrp.bom', 'name': self.env._('Reçete Sürümleri'),
            'view_mode': 'list,form', 'domain': [('id', 'in', self._atlas_surumler().ids)],
            'context': {'active_test': False}, 'target': 'current',
        }


class AtlasPlmBomAltKayit(models.AbstractModel):
    """Reçete satırı / operasyon doğrudan değiştiğinde açık ECO farklarını yeniler."""
    _name = 'atlas.plm.bom.alt.kayit'
    _description = 'PLM reçete alt kayıt izleyici'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.bom_id._atlas_eco_guncelle()
        return records

    def write(self, vals):
        boms = self.bom_id
        res = super().write(vals)
        if not self.env.context.get('atlas_plm_hesapla'):
            (boms | self.bom_id)._atlas_eco_guncelle()
        return res

    def unlink(self):
        boms = self.bom_id
        res = super().unlink()
        boms.exists()._atlas_eco_guncelle()
        return res


class MrpBomLine(models.Model):
    _name = 'mrp.bom.line'
    _inherit = ['mrp.bom.line', 'atlas.plm.bom.alt.kayit']


class MrpRoutingWorkcenter(models.Model):
    _name = 'mrp.routing.workcenter'
    _inherit = ['mrp.routing.workcenter', 'atlas.plm.bom.alt.kayit']

    atlas_onceki_operation_id = fields.Many2one('mrp.routing.workcenter', string='Önceki Sürümdeki Operasyon',
                                                copy=False, readonly=True)
