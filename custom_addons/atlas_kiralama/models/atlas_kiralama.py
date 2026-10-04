import math
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

BIRIM_SAAT = {'saat': 1, 'gun': 24, 'hafta': 24 * 7, 'ay': 24 * 30}
BIRIMLER = [('saat', 'Saat'), ('gun', 'Gün'), ('hafta', 'Hafta'), ('ay', 'Ay')]
DURUMLAR = [('rezervasyon', 'Rezerve'), ('teslim', 'Teslim edildi'), ('iade', 'İade alındı')]


def _bool_arama(operator, value):
    """Boolean hesaplanmış alan araması: Odoo 20 '=' True'yu 'in' [True] olarak da iletebilir."""
    if operator in ('in', 'not in'):
        degerler = {value} if isinstance(value, (bool, int, str)) or value is None else set(value)
        sonuc = True in degerler
        return sonuc if operator == 'in' else not sonuc
    if operator in ('=', '!='):
        return bool(value) if operator == '=' else not bool(value)
    raise ValueError(operator)


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_kirada_lokasyon_id = fields.Many2one('stock.location', string='Kirada Lokasyonu')

    @api.model
    def _atlas_kiralama_lokasyonlari(self):
        for company in self.search([]):
            company._atlas_kirada_lokasyon()

    def _atlas_kirada_lokasyon(self):
        self.ensure_one()
        if not self.atlas_kirada_lokasyon_id:
            ust = self.env['stock.warehouse'].search([('company_id', '=', self.id)], limit=1).view_location_id
            self.atlas_kirada_lokasyon_id = self.env['stock.location'].create({
                'name': 'Kirada', 'usage': 'internal', 'location_id': ust.id or False, 'company_id': self.id,
                'replenish_location': False})
        return self.atlas_kirada_lokasyon_id


class AtlasKiralamaFiyat(models.Model):
    _name = 'atlas.kiralama.fiyat'
    _description = 'Kira Fiyatı'
    _order = 'product_tmpl_id, sure, birim'

    product_tmpl_id = fields.Many2one('product.template', string='Ürün', required=True, ondelete='cascade', index=True)
    sure = fields.Integer(string='Süre', required=True, default=1)
    birim = fields.Selection(BIRIMLER, string='Birim', required=True, default='gun')
    fiyat = fields.Float(string='Fiyat', required=True, digits='Product Price')

    _sure_pozitif = models.Constraint('CHECK(sure > 0)', 'Süre sıfırdan büyük olmalı.')

    def _saat(self):
        return self.sure * BIRIM_SAAT[self.birim]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    atlas_kiralik = fields.Boolean(string='Kiralanabilir')
    atlas_kira_fiyat_ids = fields.One2many('atlas.kiralama.fiyat', 'product_tmpl_id', string='Kira Fiyatları')
    atlas_gecikme_ucreti = fields.Float(string='Günlük Gecikme Bedeli', digits='Product Price')
    atlas_hazirlik_saat = fields.Float(string='Hazırlık Süresi (saat)', help='İadeden sonra yeniden kiralanabilmesi için gereken süre.')

    @api.onchange('atlas_kiralik')
    def _onchange_atlas_kiralik(self):
        # Kiralama, teslimat beklemeden sipariş üzerinden faturalanır
        if self.atlas_kiralik and 'invoice_policy' in self._fields:
            self.invoice_policy = 'order'

    def _atlas_kira_bedeli(self, saat):
        """Süre (saat) için en düşük kira bedeli: her fiyat satırı için gereken dönem sayısı × fiyat."""
        self.ensure_one()
        if not self.atlas_kira_fiyat_ids or saat <= 0:
            return None
        return min(math.ceil(saat / f._saat() - 1e-9) * f.fiyat for f in self.atlas_kira_fiyat_ids)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    atlas_kiralama = fields.Boolean(string='Kiralama Siparişi', copy=True)
    atlas_kira_bas = fields.Datetime(string='Teslim (Kiralama Başlangıcı)', copy=False)
    atlas_kira_bit = fields.Datetime(string='İade (Kiralama Bitişi)', copy=False)
    atlas_kira_durum = fields.Selection(DURUMLAR, string='Kiralama Durumu', copy=False, tracking=True, index=True)
    atlas_teslim_zamani = fields.Datetime(string='Teslim Edildi', copy=False, readonly=True)
    atlas_iade_zamani = fields.Datetime(string='İade Alındı', copy=False, readonly=True)
    atlas_kira_picking_ids = fields.One2many('stock.picking', 'atlas_kiralama_id', string='Kiralama Transferleri')
    atlas_gecikmis = fields.Boolean(string='Gecikmiş', compute='_compute_atlas_gecikmis', search='_search_atlas_gecikmis')
    atlas_kira_sure = fields.Char(string='Süre', compute='_compute_atlas_kira_sure')

    @api.depends('atlas_kira_bas', 'atlas_kira_bit')
    def _compute_atlas_kira_sure(self):
        for order in self:
            if order.atlas_kira_bas and order.atlas_kira_bit:
                saat = (order.atlas_kira_bit - order.atlas_kira_bas).total_seconds() / 3600
                gun, kalan = divmod(round(saat), 24)
                order.atlas_kira_sure = (f'{gun} gün ' if gun else '') + (f'{kalan} saat' if kalan else '')
            else:
                order.atlas_kira_sure = ''

    def _compute_atlas_gecikmis(self):
        simdi = fields.Datetime.now()
        for order in self:
            order.atlas_gecikmis = order.atlas_kira_durum == 'teslim' and bool(order.atlas_kira_bit) and order.atlas_kira_bit < simdi

    def _search_atlas_gecikmis(self, operator, value):
        domain = [('atlas_kira_durum', '=', 'teslim'), ('atlas_kira_bit', '<', fields.Datetime.now())]
        ids = self.search(domain).ids
        return [('id', 'in' if _bool_arama(operator, value) else 'not in', ids)]

    def _atlas_kira_saat(self):
        self.ensure_one()
        if not self.atlas_kira_bas or not self.atlas_kira_bit:
            return 0.0
        return (self.atlas_kira_bit - self.atlas_kira_bas).total_seconds() / 3600

    def _atlas_kira_fiyat_guncelle(self):
        # _reset_price_unit tekil kayıt ister
        for line in self.order_line.filtered(lambda l: l.product_id.atlas_kiralik):
            line._reset_price_unit()

    @api.onchange('atlas_kira_bas', 'atlas_kira_bit')
    def _onchange_atlas_kira_tarih(self):
        self._atlas_kira_fiyat_guncelle()

    def write(self, vals):
        res = super().write(vals)
        if vals.keys() & {'atlas_kira_bas', 'atlas_kira_bit'}:
            for order in self.filtered(lambda o: o.atlas_kiralama and o.state in ('draft', 'sent')):
                order._atlas_kira_fiyat_guncelle()
        return res

    # -------------------------------------------------------------------------
    # Müsaitlik
    # -------------------------------------------------------------------------

    def _atlas_kira_cakisan(self, product, bas, bit):
        """Aynı ürün için tarih aralığı çakışan (bu sipariş dışındaki) onaylı kiralamalar."""
        domain = [('order_id.atlas_kiralama', '=', True), ('order_id.state', '=', 'sale'), ('product_id', '=', product.id),
                  ('order_id.atlas_kira_durum', 'in', ('rezervasyon', 'teslim')),
                  ('order_id.atlas_kira_bas', '<', bit), ('order_id.atlas_kira_bit', '>', bas)]
        if self.ids:
            domain.append(('order_id', 'not in', self.ids))
        return self.env['sale.order.line'].search(domain)

    def _atlas_musaitlik_kontrol(self):
        for order in self:
            if not order.atlas_kira_bas or not order.atlas_kira_bit or order.atlas_kira_bit <= order.atlas_kira_bas:
                raise UserError(self.env._('%s: teslim ve iade tarihlerini girin (iade, teslimden sonra olmalı).', order.name))
            kirada = order.company_id._atlas_kirada_lokasyon()
            wh = order.warehouse_id
            for product, lines in order.order_line.filtered(lambda l: l.product_id.atlas_kiralik).grouped('product_id').items():
                istenen = sum(lines.mapped('product_uom_qty'))
                if not product.is_storable:
                    continue
                hazirlik = product.atlas_hazirlik_saat or 0.0
                cakisan = order._atlas_kira_cakisan(product, order.atlas_kira_bas - timedelta(hours=hazirlik),
                                                    order.atlas_kira_bit + timedelta(hours=hazirlik))
                # Toplam filo: depodaki + kiradaki stok
                filo = product.with_context(location=wh.lot_stock_id.id).qty_available + \
                    product.with_context(location=kirada.id).qty_available
                ayrilan = sum(cakisan.mapped('product_uom_qty'))
                if product.uom_id.compare(istenen + ayrilan, filo) > 0:
                    raise UserError(self.env._(
                        '%(urun)s bu tarihlerde müsait değil: istenen %(istenen)s, toplam %(filo)s, çakışan kiralamalarda %(ayrilan)s.',
                        urun=product.display_name, istenen=f'{istenen:g}', filo=f'{filo:g}', ayrilan=f'{ayrilan:g}'))

    def action_confirm(self):
        kiralama = self.filtered('atlas_kiralama')
        kiralama._atlas_musaitlik_kontrol()
        res = super().action_confirm()
        kiralama.write({'atlas_kira_durum': 'rezervasyon'})
        return res

    # -------------------------------------------------------------------------
    # Teslim / iade
    # -------------------------------------------------------------------------

    def _atlas_transfer(self, kaynak, hedef, moves_vals, ad):
        self.ensure_one()
        picking_type = self.warehouse_id.int_type_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id, 'location_id': kaynak.id, 'location_dest_id': hedef.id,
            'partner_id': self.partner_shipping_id.id, 'origin': f'{self.name} - {ad}', 'atlas_kiralama_id': self.id,
            'move_ids': [Command.create({**v, 'location_id': kaynak.id, 'location_dest_id': hedef.id,
                                         'company_id': self.company_id.id}) for v in moves_vals],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def action_atlas_teslim_et(self):
        """Kiralanan ürünleri stoktan 'Kirada' lokasyonuna transfer eder."""
        for order in self:
            if order.atlas_kira_durum != 'rezervasyon':
                raise UserError(self.env._('%s teslim edilmeye hazır değil.', order.name))
            kirada = order.company_id._atlas_kirada_lokasyon()
            satirlar = order.order_line.filtered(lambda l: l.product_id.atlas_kiralik and l.product_id.is_storable)
            if satirlar:
                picking = order._atlas_transfer(order.warehouse_id.lot_stock_id, kirada, [
                    {'product_id': l.product_id.id, 'product_uom_qty': l.product_uom_qty, 'uom_id': l.product_uom_id.id,
                     'sale_line_id': l.id} for l in satirlar], self.env._('Kiralama teslimi'))
                if picking.state != 'assigned':
                    raise UserError(self.env._('%s için stok yetersiz; teslim transferi rezerve edilemedi.', order.name))
                for move in picking.move_ids:
                    move.picked = True
                picking.with_context(skip_backorder=True, atlas_kalite_atla=True)._action_done()
            order.write({'atlas_kira_durum': 'teslim', 'atlas_teslim_zamani': fields.Datetime.now()})
        return True

    def action_atlas_iade_al(self):
        """Ürünleri 'Kirada' lokasyonundan stoğa geri alır; gecikme varsa bedeli siparişe ekler."""
        for order in self:
            if order.atlas_kira_durum != 'teslim':
                raise UserError(self.env._('%s teslim edilmemiş.', order.name))
            kirada = order.company_id._atlas_kirada_lokasyon()
            teslim = order.atlas_kira_picking_ids.filtered(lambda p: p.location_dest_id == kirada and p.state == 'done')
            if teslim:
                picking = order._atlas_transfer(kirada, order.warehouse_id.lot_stock_id, [
                    {'product_id': m.product_id.id, 'product_uom_qty': m.quantity, 'uom_id': m.uom_id.id}
                    for m in teslim.move_ids], self.env._('Kiralama iadesi'))
                # Teslim edilen seri/lotların aynısı geri alınır
                for move in picking.move_ids:
                    kaynak_satirlar = teslim.move_line_ids.filtered(lambda ml: ml.product_id == move.product_id)
                    move.move_line_ids.unlink()
                    for ml in kaynak_satirlar:
                        self.env['stock.move.line'].create({
                            'move_id': move.id, 'picking_id': picking.id, 'product_id': ml.product_id.id, 'lot_id': ml.lot_id.id,
                            'quantity': ml.quantity, 'uom_id': ml.uom_id.id, 'location_id': kirada.id,
                            'location_dest_id': order.warehouse_id.lot_stock_id.id})
                    move.picked = True
                picking.with_context(skip_backorder=True, atlas_kalite_atla=True)._action_done()
            simdi = fields.Datetime.now()
            order.write({'atlas_kira_durum': 'iade', 'atlas_iade_zamani': simdi})
            order._atlas_gecikme_bedeli(simdi)
        return True

    def _atlas_gecikme_bedeli(self, iade_zamani):
        self.ensure_one()
        if not self.atlas_kira_bit or iade_zamani <= self.atlas_kira_bit:
            return
        gun = math.ceil((iade_zamani - self.atlas_kira_bit).total_seconds() / 86400 - 1e-9)
        urun = self.env.ref('atlas_kiralama.urun_gecikme')
        for line in self.order_line.filtered(lambda l: l.product_id.atlas_kiralik and l.product_id.atlas_gecikme_ucreti):
            self.env['sale.order.line'].create({
                'order_id': self.id, 'product_id': urun.id, 'product_uom_qty': gun * line.product_uom_qty,
                'price_unit': line.product_id.atlas_gecikme_ucreti,
                'name': self.env._('%(urun)s gecikme bedeli (%(gun)s gün)', urun=line.product_id.display_name, gun=gun),
                'tax_ids': [Command.set(line.tax_ids.ids)],
            })
        self.message_post(body=self.env._('İade %s gün gecikmeli alındı.', gun))

    def action_atlas_transferler(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'stock.picking', 'view_mode': 'list,form',
                'domain': [('atlas_kiralama_id', '=', self.id)], 'name': self.env._('Kiralama Transferleri')}


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_display_price(self):
        order = self.order_id
        if order.atlas_kiralama and self.product_id.atlas_kiralik:
            bedel = self.product_id.product_tmpl_id._atlas_kira_bedeli(order._atlas_kira_saat())
            if bedel is not None:
                return bedel
        return super()._get_display_price()

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        # Kiralama satırları teslimat oluşturmaz; teslim / iade kiralama transferiyle yapılır
        normal = self.filtered(lambda l: not l.order_id.atlas_kiralama)
        return super(SaleOrderLine, normal)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    atlas_kiralama_id = fields.Many2one('sale.order', string='Kiralama', index='btree_not_null', copy=False, readonly=True)
