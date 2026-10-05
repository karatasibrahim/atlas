from odoo import api, fields, models
from odoo.tools import SQL


class SiparisSatiri(models.Model):
    _inherit = 'sale.order.line'

    atlas_fatura_kesilecek = fields.Boolean(string='Düzenlenecek Faturalar', compute='_compute_atlas_tahakkuk', search='_search_atlas_fatura_kesilecek')

    def _search_atlas_fatura_kesilecek(self, operator, value):
        return self._atlas_tahakkuk_ara('qty_delivered > qty_invoiced', operator, value)

    atlas_teslim_edilmemis = fields.Boolean(string='Faturalanıp Teslim Edilmeyen', compute='_compute_atlas_tahakkuk', search='_search_atlas_teslim_edilmemis')

    def _search_atlas_teslim_edilmemis(self, operator, value):
        return self._atlas_tahakkuk_ara('qty_invoiced > qty_delivered', operator, value)

    atlas_tahakkuk_miktar = fields.Float(string='Fark Miktarı', compute='_compute_atlas_tahakkuk', digits='Product Unit')
    atlas_tahakkuk_tutar = fields.Monetary(string='Fark Tutarı (KDV hariç)', compute='_compute_atlas_tahakkuk', currency_field='currency_id')

    def action_open_accrual_wizard(self):
        """Community'deki "Tahakkuk Kaydı" sunucu eylemi bu metodu çağırır (Enterprise'da tanımlı, Community'de yok)."""
        return {'type': 'ir.actions.act_window', 'res_model': 'account.accrued.orders.wizard', 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Tahakkuk Kaydı'), 'views': [[False, 'form']],
                'context': {'active_model': self._name, 'active_ids': self.ids,
                            'default_account_id': self.env.company.revenue_accrual_account_id.id or self.env.company._atlas_tahakkuk_hesabi('revenue_accrual_account_id', '181').id,
                            'default_accrual_type': self.env.context.get('accrual_type') or (
                                'invoice_to_be_issued' if all(s.qty_delivered >= s.qty_invoiced for s in self) else 'invoiced_not_delivered')}}

    def _compute_atlas_tahakkuk(self):
        for s in self:
            fark = s.qty_delivered - s.qty_invoiced
            s.atlas_tahakkuk_miktar = fark
            s.atlas_tahakkuk_tutar = fark * s.price_unit * (1 - (s.discount or 0) / 100)
            s.atlas_fatura_kesilecek = s.qty_delivered > s.qty_invoiced
            s.atlas_teslim_edilmemis = s.qty_invoiced > s.qty_delivered

    def _atlas_tahakkuk_ara(self, kosul, operator, value):
        # Odoo 20: ('alan', '=', True) aramaları ('in', {True}) olarak da gelebilir
        if operator in ('in', 'not in'):
            degerler = set(value)
            if len(degerler) != 1 or not isinstance(next(iter(degerler)), bool):
                return NotImplemented
            operator, value = ('=' if operator == 'in' else '!='), next(iter(degerler))
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        self.flush_model(['qty_delivered', 'qty_invoiced', 'display_type'])
        self.env[self._fields['order_id'].comodel_name].flush_model(['state'])
        self.env.cr.execute(SQL(
            "SELECT l.id FROM sale_order_line l JOIN sale_order o ON o.id = l.order_id "
            "WHERE l.display_type IS NULL AND o.state IN ('sale', 'done') AND " + kosul.replace('qty_', 'l.qty_')))
        ids = [r[0] for r in self.env.cr.fetchall()]
        return [('id', 'in' if (operator == '=') == value else 'not in', ids)]


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _atlas_tahakkuk_hesabi(self, alan, kod):
        """Şirketin tahakkuk hesabı; boşsa TDHP 181 grubundaki ilk hesap atanır."""
        self.ensure_one()
        if not self[alan]:
            hesap = self.env['account.account'].with_company(self).search(
                [('company_ids', 'in', self.id), ('code', '=like', '181%')], order='code', limit=1)
            if hesap:
                self.sudo()[alan] = hesap
        return self[alan]

    @api.model
    def _atlas_tahakkuk_kur(self):
        for sirket in self.search([]):
            if sirket.chart_template:
                sirket._atlas_tahakkuk_hesabi('revenue_accrual_account_id', '181')
