from odoo import fields, models

SISTEM = ("Masraf fişlerini (yazar kasa fişi, e-Arşiv fatura, taksi/otopark/yemek fişi) okuyan bir asistansın. "
          "Bulamadığını boş bırak; tutarlar sayı, tarih YYYY-AA-GG. Yalnız 'masraf' aracını çağır.")


class HrExpense(models.Model):
    _name = 'hr.expense'
    _inherit = ['hr.expense', 'atlas.ai.okunabilir']

    def _atlas_ai_kategoriler(self):
        return self.env['product.product'].search([('can_be_expensed', '=', True)], limit=100)

    def _atlas_ai_okuma(self):
        kategoriler = self._atlas_ai_kategoriler()
        return SISTEM, {
            'name': 'masraf', 'description': 'Masraf fişinden okunan veri',
            'input_schema': {'type': 'object', 'properties': {
                'aciklama': {'type': 'string', 'description': 'Kısa masraf açıklaması, ör. "Taksi - Kadıköy"'},
                'tarih': {'type': 'string'}, 'toplam': {'type': 'number', 'description': 'KDV dahil ödenen tutar'},
                'kdv_tutari': {'type': 'number'}, 'para_birimi': {'type': 'string'},
                'satici': {'type': 'string'}, 'satici_vkn': {'type': 'string'},
                'kategori': {'type': 'string', 'enum': kategoriler.mapped('display_name') or ['Diğer']},
                'guven': {'type': 'number'}},
                'required': ['toplam', 'guven']}}

    def _atlas_ai_uygula(self, s):
        self.ensure_one()
        if self.state not in ('draft', False):
            return
        vals = {}
        kategori = self._atlas_ai_kategoriler().filtered(lambda p: p.display_name == s.get('kategori'))[:1]
        if kategori and not self.product_id:
            vals['product_id'] = kategori.id
        if s.get('aciklama') and (not self.name or self.name.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))):
            vals['name'] = s['aciklama']
        if s.get('tarih'):
            try:
                vals['date'] = fields.Date.to_date(s['tarih'][:10])
            except ValueError:
                pass
        if s.get('para_birimi'):
            para = self.env['res.currency'].search([('name', '=', s['para_birimi'].upper()[:3])], limit=1)
            if para:
                vals['currency_id'] = para.id
        if s.get('satici'):
            satici = self.env['res.partner'].search([('name', '=ilike', s['satici'].strip())], limit=1)
            if satici:
                vals['vendor_id'] = satici.id
        if vals:
            self.write(vals)
        if s.get('toplam'):
            self.write({'total_amount_currency': s['toplam']})
