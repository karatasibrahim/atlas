from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.atlas_donem.models.tools import account_by_code

# TDHP stok kategorileri: (xml kimliği, kategori adı, stok hesabı, stok değişim hesabı)
# Yarı mamul değişimi 152'ye gider: tamamlanan üretim 151 → 152, satılan mamul 152 → 620.
STOK_KATEGORILERI = [
    ('atlas_stok.categ_ticari_mal', 'Ticari Mallar', '153', '621'),
    ('atlas_stok.categ_ilk_madde', 'İlk Madde ve Malzeme', '150', '710'),
    ('atlas_stok.categ_yari_mamul', 'Yarı Mamuller', '151', '152'),
    ('atlas_stok.categ_mamul', 'Mamuller', '152', '620'),
    ('atlas_stok.categ_diger_stok', 'Diğer Stoklar', '157', '770'),
    ('product.product_category_goods', 'Mallar', '153', '621'),  # yeni ürünlerin varsayılan kategorisi
]
GELIR_HESABI = '600'
HIZMET_GIDER_HESABI = '770'


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _atlas_setup_stock_accounting(self):
        """TDHP stok kategorilerini ve stok değişim hesaplarını kurar; varsayılanlar: ortalama maliyet, aralıklı envanter."""
        for company in self:
            company = company.with_company(company)
            acc = lambda code: account_by_code(self.env, company, code)  # noqa: E731
            if company.cost_method == 'standard' and not self.env['product.product'].search_count([('is_storable', '=', True)]):
                company.cost_method = 'average'
            company.account_stock_valuation_id = acc('153')

            Category = self.env['product.category'].with_company(company)
            parent = self.env.ref('product.product_category_all', raise_if_not_found=False)
            for xmlid, name, stock_code, variation_code in STOK_KATEGORILERI:
                stock_account, variation = acc(stock_code), acc(variation_code)
                # Aralıklı envanterde stok gider bağlantısı (sürekli envanter içindir) kapanışa gereksiz satır ekler
                stock_account.sudo().write({'account_stock_variation_id': variation.id, 'account_stock_expense_id': False})
                category = self.env.ref(xmlid, raise_if_not_found=False)
                if not category:
                    module, xml_name = xmlid.split('.')
                    category = Category.create({'name': name, 'parent_id': parent.id if parent else False})
                    self.env['ir.model.data'].sudo().create({
                        'module': module, 'name': xml_name, 'model': 'product.category',
                        'res_id': category.id, 'noupdate': True})
                category.with_company(company).write({
                    'property_stock_valuation_account_id': stock_account.id,
                    'property_account_income_categ_id': acc(GELIR_HESABI).id,
                })
            # Stok tutulmayan kalemler (hizmet, gider) stok hesabına değil gidere yazılsın
            for category in Category.search([]) - self._atlas_stock_categories():
                category.with_company(company).write({
                    'property_account_expense_categ_id': acc(HIZMET_GIDER_HESABI).id,
                    'property_account_income_categ_id': acc(GELIR_HESABI).id,
                })
            company._atlas_apply_inventory_mode()

    def _atlas_stock_categories(self):
        records = self.env['product.category']
        for xmlid, *_rest in STOK_KATEGORILERI:
            records |= self.env.ref(xmlid, raise_if_not_found=False) or records.browse()
        return records

    def _atlas_apply_inventory_mode(self):
        """Stok kategorilerinin alış (gider) hesabını envanter yöntemine göre ayarlar.

        Aralıklı: alışlar doğrudan stok hesabına (150/153...), dönem sonu kapanışta fark maliyete (710/620/621).
        Sürekli: stok hareketinde stok hesabı, satılan malın maliyeti gider hesabına (621/620/710).
        """
        for company in self:
            for category in company._atlas_stock_categories():
                category = category.with_company(company)
                stock_account = category.property_stock_valuation_account_id
                expense = stock_account if company.inventory_valuation == 'periodic' else stock_account.account_stock_variation_id
                if expense and category.property_account_expense_categ_id != expense:
                    category.property_account_expense_categ_id = expense


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_cost_method = fields.Selection(related='company_id.cost_method', readonly=False, string='Maliyet Yöntemi')
    atlas_inventory_valuation = fields.Selection(related='company_id.inventory_valuation', readonly=False, string='Envanter Yöntemi')
    atlas_inventory_period = fields.Selection(related='company_id.inventory_period', readonly=False, string='Stok Kapanışı')
    atlas_stock_valuation_account_id = fields.Many2one(related='company_id.account_stock_valuation_id', readonly=False,
                                                       string='Varsayılan Stok Hesabı')

    def set_values(self):
        old = {company: company.inventory_valuation for company in self.company_id}
        super().set_values()
        if any(company.inventory_valuation != mode for company, mode in old.items()):
            self.company_id._atlas_apply_inventory_mode()

    def _atlas_enable_stock_features(self):
        """Lot/seri, çoklu lokasyon, ölçü birimi, iş emirleri ve yan ürünleri açar."""
        self.ensure_one()
        self.write({
            'group_stock_production_lot': True,
            'group_stock_multi_locations': True,
            'group_uom': True,
            'group_mrp_routings': True,
            'group_mrp_byproducts': True,
        })
        self.execute()

    @api.onchange('atlas_inventory_valuation')
    def _onchange_atlas_inventory_valuation(self):
        if self.atlas_inventory_valuation == 'real_time' and self.env['account.move'].search_count(
                [('company_id', '=', self.company_id.id), ('inventory_closing', '=', True)], limit=1):
            return {'warning': {
                'title': self.env._('Envanter yöntemi değişikliği'),
                'message': self.env._('Daha önce aralıklı envanter kapanışı yapılmış. Yöntemi dönem başında değiştirmeniz önerilir.'),
            }}
