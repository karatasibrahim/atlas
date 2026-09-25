from odoo import api, fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    atlas_varsayilan_takip = fields.Selection(
        [('lot', 'Lot'), ('serial', 'Seri Numarası')], string='Varsayılan Takip',
        help='Bu kategoride açılan stoklu ürünlerin varsayılan lot/seri takibi.')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        Category = self.env['product.category']
        for vals in vals_list:
            if vals.get('is_storable') and 'tracking' not in vals and vals.get('categ_id'):
                default = Category.browse(vals['categ_id']).atlas_varsayilan_takip
                if default:
                    vals['tracking'] = default
        return super().create(vals_list)


class StockLot(models.Model):
    _inherit = 'stock.lot'

    atlas_qr = fields.Char(string='QR İçeriği', compute='_compute_atlas_qr')

    def _compute_atlas_qr(self):
        for lot in self:
            lot.atlas_qr = self.env['atlas.barkod']._qr_lot(lot)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    atlas_qr = fields.Char(string='QR İçeriği', compute='_compute_atlas_qr')

    def _compute_atlas_qr(self):
        for production in self:
            production.atlas_qr = f'ATL:MO:{production.name}'
