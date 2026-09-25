"""Barkod / QR işlemleri servisi.

Mobil ekran (OWL) ve ileride yazılacak native uygulama (/json/2 API) aynı metotları çağırır.
Tüm dış metotlar yalnızca JSON'a çevrilebilir sözlük/liste döndürür.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

ISLEM_PICKING_TYPE = {'mal_kabul': 'incoming', 'sevkiyat': 'outgoing'}
QR_PREFIX = 'ATL'


class AtlasBarkod(models.AbstractModel):
    _name = 'atlas.barkod'
    _description = 'Barkod İşlemleri'

    # -------------------------------------------------------------------------
    # QR içerikleri ve çözümleme
    # -------------------------------------------------------------------------

    @api.model
    def _product_ref(self, product):
        return product.default_code or f'P{product.id}'

    @api.model
    def _qr_lot(self, lot):
        return f'{QR_PREFIX}:LOT:{self._product_ref(lot.product_id)}:{lot.name}'

    @api.model
    def _find_product(self, ref):
        Product = self.env['product.product']
        if ref.startswith('P') and ref[1:].isdigit():
            product = Product.browse(int(ref[1:])).exists()
            if product:
                return product
        return Product.search(['|', ('barcode', '=', ref), ('default_code', '=', ref)], limit=1)

    @api.model
    def _parse(self, code, products=None):
        """Okutulan kodu çözümler.

        :param products: belgedeki ürünler; aynı seri no birden çok üründe varsa bunlar tercih edilir
        :return: {'tip': urun|seri|lokasyon|belge|uretim, 'product', 'lot', 'lot_name', 'location', 'record'}
        """
        code = (code or '').strip()
        if not code:
            raise UserError(self.env._('Boş kod okutuldu.'))
        company = self.env.company
        Lot, Location = self.env['stock.lot'], self.env['stock.location']
        result = {'tip': False, 'product': self.env['product.product'], 'lot': Lot, 'lot_name': False,
                  'location': Location, 'record': False, 'kod': code}

        if code.upper().startswith(f'{QR_PREFIX}:'):
            parts = code.split(':')
            kind = parts[1].upper() if len(parts) > 1 else ''
            if kind == 'LOT' and len(parts) >= 4:
                product = self._find_product(parts[2])
                name = ':'.join(parts[3:])
                lot = Lot.search([('product_id', '=', product.id), ('name', '=', name),
                                  ('company_id', 'in', (False, company.id))], limit=1) if product else Lot
                return {**result, 'tip': 'seri', 'product': product, 'lot': lot, 'lot_name': name}
            if kind == 'MO' and len(parts) >= 3:
                production = self.env['mrp.production'].search([('name', '=', ':'.join(parts[2:]))], limit=1)
                return {**result, 'tip': 'uretim', 'record': production}
            if kind == 'LOC' and len(parts) >= 3:
                value = ':'.join(parts[2:])
                location = Location.search(['|', ('barcode', '=', value), ('complete_name', '=', value)], limit=1)
                return {**result, 'tip': 'lokasyon', 'location': location}
            raise UserError(self.env._('Tanınmayan Atlas QR kodu: %s', code))

        product = self._find_product(code)
        if product:
            return {**result, 'tip': 'urun', 'product': product}
        lots = Lot.search([('name', '=', code), ('company_id', 'in', (False, company.id))])
        if products and len(lots) > 1:
            lots = lots.filtered(lambda l: l.product_id in products) or lots
        if lots:
            lot = lots[:1]
            return {**result, 'tip': 'seri', 'product': lot.product_id, 'lot': lot, 'lot_name': lot.name}
        location = Location.search([('barcode', '=', code)], limit=1)
        if location:
            return {**result, 'tip': 'lokasyon', 'location': location}
        picking = self.env['stock.picking'].search(['|', ('name', '=', code), ('atlas_irsaliye_no', '=', code)], limit=1)
        if picking:
            return {**result, 'tip': 'belge', 'record': picking}
        production = self.env['mrp.production'].search([('name', '=', code)], limit=1)
        if production:
            return {**result, 'tip': 'uretim', 'record': production}
        # Belgeye yeni gelen (henüz sistemde olmayan) seri: yalnızca belge ürünü seri takipliyse
        if products and len(products.filtered(lambda p: p.tracking in ('lot', 'serial'))) == 1:
            return {**result, 'tip': 'seri', 'product': products.filtered(lambda p: p.tracking in ('lot', 'serial')), 'lot_name': code}
        raise UserError(self.env._('"%s" kodu tanınmadı (ürün, seri, lokasyon veya belge bulunamadı).', code))

    @api.model
    def cozumle(self, code):
        """Genel okutma: kodun ne olduğunu ve ilgili bilgileri döndürür."""
        parsed = self._parse(code)
        product, lot = parsed['product'], parsed['lot']
        info = {'tip': parsed['tip'], 'kod': code}
        if product:
            info['urun'] = self._product_dict(product)
            info['stok'] = [{'lokasyon': q.location_id.complete_name, 'seri': q.lot_id.name or '', 'miktar': q.quantity}
                            for q in self.env['stock.quant'].search([
                                ('product_id', '=', product.id), ('location_id.usage', '=', 'internal'),
                                ('quantity', '!=', 0)] + ([('lot_id', '=', lot.id)] if lot else []), limit=50)]
        if lot:
            info['seri'] = {'id': lot.id, 'ad': lot.name, 'qr': self._qr_lot(lot)}
        if parsed['location']:
            info['lokasyon'] = {'id': parsed['location'].id, 'ad': parsed['location'].complete_name}
        record = parsed['record']
        if record:
            info['belge'] = {'model': record._name, 'id': record.id, 'ad': record.display_name,
                             'islem': 'uretim' if record._name == 'mrp.production' else
                             {'incoming': 'mal_kabul', 'outgoing': 'sevkiyat'}.get(record.picking_type_code)}
        return info

    @api.model
    def _product_dict(self, product):
        return {'id': product.id, 'ad': product.display_name, 'kod': product.default_code or '',
                'barkod': product.barcode or '', 'takip': product.tracking or 'none', 'birim': product.uom_id.name}

    # -------------------------------------------------------------------------
    # Ana ekran ve listeler
    # -------------------------------------------------------------------------

    @api.model
    def ana_ekran(self):
        Picking = self.env['stock.picking']
        open_states = ('confirmed', 'waiting', 'assigned')
        return {
            'mal_kabul': Picking.search_count([('picking_type_code', '=', 'incoming'), ('state', 'in', open_states)]),
            'sevkiyat': Picking.search_count([('picking_type_code', '=', 'outgoing'), ('state', 'in', open_states)]),
            'uretim': self.env['mrp.production'].search_count([('state', 'in', ('confirmed', 'progress', 'to_close'))]),
            'kullanici': self.env.user.name,
            'sirket': self.env.company.name,
        }

    @api.model
    def belge_listesi(self, islem, arama=''):
        if islem == 'uretim':
            domain = [('state', 'in', ('confirmed', 'progress', 'to_close'))]
            if arama:
                domain += ['|', ('name', 'ilike', arama), ('product_id', 'ilike', arama)]
            return [{'id': mo.id, 'ad': mo.name, 'alt': mo.product_id.display_name,
                     'bilgi': f'{mo.product_qty:g} {mo.uom_id.name}', 'tarih': fields.Date.to_string(mo.date_start.date()) if mo.date_start else '',
                     'durum': mo.state}
                    for mo in self.env['mrp.production'].search(domain, order='date_start, id', limit=100)]
        if islem == 'sayim':
            return [{'id': loc.id, 'ad': loc.complete_name, 'alt': loc.barcode or '', 'bilgi': '', 'tarih': '', 'durum': ''}
                    for loc in self.env['stock.location'].search([('usage', '=', 'internal')], order='complete_name', limit=200)]
        code = ISLEM_PICKING_TYPE.get(islem)
        if not code:
            raise UserError(self.env._('Tanımsız işlem: %s', islem))
        domain = [('picking_type_code', '=', code), ('state', 'in', ('confirmed', 'waiting', 'assigned'))]
        if arama:
            domain += ['|', '|', ('name', 'ilike', arama), ('partner_id', 'ilike', arama), ('origin', 'ilike', arama)]
        return [{'id': p.id, 'ad': p.name, 'alt': p.partner_id.display_name or '', 'bilgi': p.origin or '',
                 'tarih': fields.Date.to_string(p.scheduled_date.date()) if p.scheduled_date else '', 'durum': p.state}
                for p in self.env['stock.picking'].search(domain, order='scheduled_date, id', limit=100)]

    # -------------------------------------------------------------------------
    # Mal kabul / sevkiyat
    # -------------------------------------------------------------------------

    @api.model
    def _picking(self, picking_id):
        picking = self.env['stock.picking'].browse(picking_id).exists()
        if not picking:
            raise UserError(self.env._('Belge bulunamadı.'))
        return picking

    @api.model
    def _move_dict(self, move):
        lines = move.move_line_ids
        return {
            'move_id': move.id,
            'urun': self._product_dict(move.product_id),
            'istenen': move.product_uom_qty,
            'okutulan': move.quantity if move.picked else 0.0,
            'birim': move.uom_id.name,
            'seriler': [l.lot_id.name or l.lot_name for l in lines if move.picked and (l.lot_id or l.lot_name)],
            'tamam': move.picked and move.uom_id.compare(move.quantity, move.product_uom_qty) >= 0,
        }

    @api.model
    def belge_ac(self, islem, res_id):
        if islem == 'uretim':
            return self.uretim_ac(res_id)
        if islem == 'sayim':
            return self.sayim_ac(res_id)
        picking = self._picking(res_id)
        moves = picking.move_ids.filtered(lambda m: m.state != 'cancel')
        return {
            'id': picking.id, 'islem': islem, 'ad': picking.name,
            'cari': picking.partner_id.display_name or '', 'kaynak': picking.origin or '',
            'lokasyon': (picking.location_dest_id if islem == 'mal_kabul' else picking.location_id).complete_name,
            'durum': picking.state, 'irsaliye_no': picking.atlas_irsaliye_no or '',
            'satirlar': [self._move_dict(move) for move in moves],
        }

    @api.model
    def _start_move(self, move):
        """İlk okutmada öneri/rezervasyon satırları temizlenir; bundan sonra yalnızca okutulanlar sayılır."""
        if not move.picked:
            move.move_line_ids.unlink()
            move.picked = True

    @api.model
    def _serial_already(self, move, name):
        """Seri bu harekette okutuldu mu? (Okutma başlamadan önceki satırlar Odoo'nun rezervasyonudur.)"""
        return move.picked and any((l.lot_id.name or l.lot_name) == name for l in move.move_line_ids)

    @api.model
    def _add_tracked_line(self, move, lot, lot_name, qty, location=None):
        existing = move.move_line_ids.filtered(lambda l: (lot and l.lot_id == lot) or (not lot and l.lot_name == lot_name))
        if existing and move.product_id.tracking == 'lot':
            existing[:1].quantity += qty
            return
        self.env['stock.move.line'].create({
            'move_id': move.id,
            'picking_id': move.picking_id.id,
            'product_id': move.product_id.id,
            'uom_id': move.uom_id.id,
            'location_id': (location or move.location_id).id,
            'location_dest_id': move.location_dest_id.id,
            'lot_id': lot.id if lot else False,
            'lot_name': False if lot else lot_name,
            'quantity': 1.0 if move.product_id.tracking == 'serial' else qty,
            'picked': True,
        })

    @api.model
    def _consume(self, moves, parsed, qty, incoming=False):
        """Hareket(ler)e okutma uygular; mal kabulde yeni seri kabul edilir, çıkışta seri stokta aranır."""
        product, lot, lot_name = parsed['product'], parsed['lot'], parsed['lot_name']
        if not product:
            raise UserError(self.env._('Okutulan kod bir ürün veya seri değil.'))
        candidates = moves.filtered(lambda m: m.product_id == product and m.state not in ('done', 'cancel'))
        if not candidates:
            raise UserError(self.env._('%s bu belgede yok.', product.display_name))
        move = candidates.filtered(lambda m: not (m.picked and m.quantity >= m.product_uom_qty))[:1] or candidates[:1]
        tracking = product.tracking
        if tracking in ('lot', 'serial') and not (lot or lot_name):
            raise UserError(self.env._('%s %s takipli; ürün barkodu yerine seri/lot QR kodunu okutun.',
                                       product.display_name, 'seri' if tracking == 'serial' else 'lot'))
        name = lot.name if lot else lot_name
        if tracking == 'serial' and self._serial_already(move, name):
            raise UserError(self.env._('%s seri numarası zaten okutuldu.', name))

        self._start_move(move)
        if tracking in ('lot', 'serial'):
            location = None
            if not incoming:
                if not lot:
                    raise UserError(self.env._('%s seri/lot numarası sistemde yok.', name))
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id), ('lot_id', '=', lot.id),
                    ('location_id', 'child_of', move.location_id.id), ('quantity', '>', 0)], limit=1)
                if not quant:
                    raise UserError(self.env._('%(seri)s bu depoda / lokasyonda stokta değil.', seri=name))
                location = quant.location_id
            elif tracking == 'serial' and lot and self.env['stock.quant'].search_count([
                    ('lot_id', '=', lot.id), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]):
                raise UserError(self.env._('%s seri numarası zaten stokta; ikinci kez kabul edilemez.', name))
            self._add_tracked_line(move, lot, lot_name, qty, location)
        else:
            move.quantity = move.quantity + qty
        warning = False
        if move.uom_id.compare(move.quantity, move.product_uom_qty) > 0:
            warning = self.env._('%(urun)s istenenden fazla okutuldu (%(okutulan)s / %(istenen)s).',
                                 urun=product.display_name, okutulan=move.quantity, istenen=move.product_uom_qty)
        return move, warning

    @api.model
    def okut(self, islem, res_id, code, qty=1.0):
        """Belgeye okutma. Dönüş: güncel belge + mesaj (ses/uyarı için 'sonuc': ok|uyari)."""
        if islem == 'uretim':
            return self.uretim_okut(res_id, code, qty)
        if islem == 'sayim':
            return self.sayim_okut(res_id, code, qty)
        picking = self._picking(res_id)
        if picking.state in ('done', 'cancel'):
            raise UserError(self.env._('Belge tamamlanmış.'))
        parsed = self._parse(code, picking.move_ids.product_id)
        move, warning = self._consume(picking.move_ids, parsed, qty, incoming=picking.picking_type_code == 'incoming')
        return {'belge': self.belge_ac(islem, picking.id), 'sonuc': 'uyari' if warning else 'ok',
                'mesaj': warning or f'{move.product_id.display_name}: {move.quantity:g} / {move.product_uom_qty:g}'}

    @api.model
    def _new_serials(self, product, adet):
        """Ürünün seri dizisinden (yoksa genel diziden) yeni seri/lot kayıtları oluşturur."""
        Lot = self.env['stock.lot']
        lots = Lot
        generic = self.env.ref('stock.sequence_production_lots', raise_if_not_found=False)
        if product.default_code and (not product.lot_sequence_id or product.lot_sequence_id == generic):
            # Ürüne özel seri dizisi: stok kodu ön ekli (ör. KMB-1-0000001)
            product.product_tmpl_id.serial_prefix_format = f'{product.default_code}-'
        for _i in range(int(adet)):
            sequence = product.lot_sequence_id
            name = sequence.next_by_id() if sequence else self.env['ir.sequence'].next_by_code('stock.lot.serial')
            lots |= Lot.create({'name': name, 'product_id': product.id, 'company_id': self.env.company.id})
        return lots

    @api.model
    def seri_uret(self, islem, res_id, move_id, adet=None):
        """Mal kabulde seri takipli satır için kalan adet kadar seri üretir ve okutulmuş sayar.
        Dönüş: güncel belge + etiket yazdırma için seri id'leri."""
        if islem == 'uretim':
            return self.uretim_seri_uret(res_id)
        picking = self._picking(res_id)
        move = picking.move_ids.filtered(lambda m: m.id == move_id)
        if picking.picking_type_code != 'incoming' or not move or move.product_id.tracking not in ('lot', 'serial'):
            raise UserError(self.env._('Seri üretimi yalnızca mal kabulde, takipli ürünler için yapılır.'))
        done = move.quantity if move.picked else 0.0
        if move.product_id.tracking == 'serial':
            adet = int(adet or (move.product_uom_qty - done))
            if adet < 1:
                raise UserError(self.env._('Üretilecek seri kalmadı.'))
            lots = self._new_serials(move.product_id, adet)
            self._start_move(move)
            for lot in lots:
                self._add_tracked_line(move, lot, False, 1.0)
        else:
            lots = self._new_serials(move.product_id, 1)
            self._start_move(move)
            self._add_tracked_line(move, lots, False, float(adet or (move.product_uom_qty - done)))
        return {'belge': self.belge_ac(islem, picking.id), 'seri_ids': lots.ids, 'sonuc': 'ok',
                'mesaj': self.env._('%s seri/lot üretildi.', len(lots))}

    @api.model
    def dogrula(self, islem, res_id, kalan_icin_belge=True, sifirla=False):
        if islem == 'uretim':
            return self.uretim_tamamla(res_id, kalan_icin_belge)
        if islem == 'sayim':
            return self.sayim_uygula(res_id, sifirla)
        picking = self._picking(res_id)
        if not any(picking.move_ids.mapped('picked')):
            raise UserError(self.env._('Henüz hiçbir ürün okutulmadı.'))
        context = {'skip_backorder': True, 'skip_sms': True}
        if not kalan_icin_belge:
            context['picking_ids_not_to_backorder'] = picking.ids
        result = picking.with_context(**context).button_validate()
        if isinstance(result, dict) and result.get('res_model'):
            raise UserError(self.env._('Belge ek işlem istiyor (%s); masaüstü ekrandan tamamlayın.', result.get('name') or result['res_model']))
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)], limit=1)
        message = self.env._('%s tamamlandı.', picking.name)
        if picking.atlas_irsaliye_no:
            message += ' ' + self.env._('İrsaliye No: %s', picking.atlas_irsaliye_no)
        if backorder:
            message += ' ' + self.env._('Kalanlar için %s oluşturuldu.', backorder.name)
        return {'sonuc': 'ok', 'mesaj': message, 'irsaliye_no': picking.atlas_irsaliye_no or '',
                'kalan_belge_id': backorder.id or False}

    # -------------------------------------------------------------------------
    # Stok sayımı
    # -------------------------------------------------------------------------

    @api.model
    def _location(self, location_id):
        location = self.env['stock.location'].browse(location_id).exists()
        if not location or location.usage != 'internal':
            raise UserError(self.env._('Sayım için bir stok lokasyonu seçin.'))
        return location

    @api.model
    def sayim_ac(self, location_id):
        location = self._location(location_id)
        quants = self.env['stock.quant'].search([('location_id', '=', location.id),
                                                 '|', ('quantity', '!=', 0), ('inventory_quantity_set', '=', True)])
        return {
            'id': location.id, 'islem': 'sayim', 'ad': location.complete_name, 'cari': '', 'kaynak': '',
            'lokasyon': location.complete_name, 'durum': '', 'irsaliye_no': '',
            'satirlar': [{
                'quant_id': q.id, 'urun': self._product_dict(q.product_id), 'seri': q.lot_id.name or '',
                'sistem': q.quantity, 'sayilan': q.inventory_quantity if q.inventory_quantity_set else None,
                'fark': q.inventory_diff_quantity if q.inventory_quantity_set else None, 'birim': q.uom_id.name,
            } for q in quants.sorted(lambda q: (q.product_id.display_name, q.lot_id.name or ''))],
        }

    @api.model
    def sayim_okut(self, location_id, code, qty=1.0):
        location = self._location(location_id)
        parsed = self._parse(code)
        product, lot = parsed['product'], parsed['lot']
        if not product:
            raise UserError(self.env._('Okutulan kod bir ürün veya seri değil.'))
        if product.tracking in ('lot', 'serial') and not (lot or parsed['lot_name']):
            raise UserError(self.env._('%s takipli; seri/lot QR kodunu okutun.', product.display_name))
        if product.tracking in ('lot', 'serial') and not lot:
            lot = self.env['stock.lot'].create({'name': parsed['lot_name'], 'product_id': product.id,
                                                'company_id': self.env.company.id})
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        quant = Quant.search([('product_id', '=', product.id), ('location_id', '=', location.id),
                              ('lot_id', '=', lot.id if lot else False)], limit=1)
        warning = False
        if product.tracking == 'serial':
            if quant.inventory_quantity_set and quant.inventory_quantity >= 1:
                raise UserError(self.env._('%s seri numarası bu sayımda zaten okutuldu.', lot.name))
            elsewhere = self.env['stock.quant'].search([('lot_id', '=', lot.id), ('location_id.usage', '=', 'internal'),
                                                        ('location_id', '!=', location.id), ('quantity', '>', 0)], limit=1)
            if elsewhere:
                warning = self.env._('%(seri)s sistemde %(lok)s lokasyonunda görünüyor.', seri=lot.name, lok=elsewhere.location_id.complete_name)
            new_qty = 1.0
        else:
            new_qty = (quant.inventory_quantity if quant.inventory_quantity_set else 0.0) + qty
        if quant:
            quant.write({'inventory_quantity': new_qty, 'inventory_quantity_set': True})
        else:
            quant = Quant.create({'product_id': product.id, 'location_id': location.id,
                                  'lot_id': lot.id if lot else False, 'inventory_quantity': new_qty})
            quant.inventory_quantity_set = True
        return {'belge': self.sayim_ac(location.id), 'sonuc': 'uyari' if warning else 'ok',
                'mesaj': warning or f'{product.display_name}{" / " + lot.name if lot else ""}: {new_qty:g}'}

    @api.model
    def sayim_uygula(self, location_id, sifirla=False):
        """Sayılan miktarları stoğa işler. sifirla: lokasyonda olup okutulmayanlar sıfırlanır."""
        location = self._location(location_id)
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        quants = Quant.search([('location_id', '=', location.id), ('inventory_quantity_set', '=', True)])
        if sifirla:
            missing = Quant.search([('location_id', '=', location.id), ('inventory_quantity_set', '=', False),
                                    ('quantity', '>', 0)])
            missing.write({'inventory_quantity': 0.0, 'inventory_quantity_set': True})
            quants |= missing
        if not quants:
            raise UserError(self.env._('Bu lokasyonda sayılmış ürün yok.'))
        count = len(quants)
        quants.with_context(inventory_name=self.env._('Barkod sayımı: %s', location.complete_name))._apply_inventory()
        return {'sonuc': 'ok', 'mesaj': self.env._('%(adet)s kalem stoğa işlendi (%(lok)s).', adet=count, lok=location.complete_name)}

    # -------------------------------------------------------------------------
    # Üretim
    # -------------------------------------------------------------------------

    @api.model
    def _production(self, production_id):
        production = self.env['mrp.production'].browse(production_id).exists()
        if not production:
            raise UserError(self.env._('Üretim emri bulunamadı.'))
        return production

    @api.model
    def uretim_ac(self, production_id):
        production = self._production(production_id)
        return {
            'id': production.id, 'islem': 'uretim', 'ad': production.name,
            'cari': production.product_id.display_name, 'kaynak': production.origin or '',
            'lokasyon': production.location_src_id.complete_name, 'durum': production.state, 'irsaliye_no': '',
            'qr': production.atlas_qr,
            'mamul': {
                'urun': self._product_dict(production.product_id),
                'miktar': production.product_qty, 'birim': production.uom_id.name,
                'seriler': production.lot_producing_ids.mapped('name'),
                'seri_ids': production.lot_producing_ids.ids,
            },
            'satirlar': [self._move_dict(move) for move in production.move_raw_ids.filtered(lambda m: m.state != 'cancel')],
        }

    @api.model
    def uretim_okut(self, production_id, code, qty=1.0):
        production = self._production(production_id)
        if production.state in ('done', 'cancel'):
            raise UserError(self.env._('Üretim emri tamamlanmış.'))
        if production.state == 'draft':
            production.action_confirm()
        parsed = self._parse(code, production.move_raw_ids.product_id | production.product_id)
        if parsed['product'] == production.product_id and production.product_tracking in ('lot', 'serial'):
            return self._uretim_mamul_seri(production, parsed)
        move, warning = self._consume(production.move_raw_ids, parsed, qty)
        return {'belge': self.uretim_ac(production.id), 'sonuc': 'uyari' if warning else 'ok',
                'mesaj': warning or f'{move.product_id.display_name}: {move.quantity:g} / {move.product_uom_qty:g}'}

    @api.model
    def _uretim_mamul_seri(self, production, parsed):
        lot = parsed['lot'] or self.env['stock.lot'].create({
            'name': parsed['lot_name'], 'product_id': production.product_id.id, 'company_id': production.company_id.id})
        if lot in production.lot_producing_ids:
            raise UserError(self.env._('%s zaten bu üretime eklendi.', lot.name))
        if production.product_tracking == 'serial' and len(production.lot_producing_ids) >= production.product_qty:
            raise UserError(self.env._('Üretilecek miktar kadar seri zaten eklendi.'))
        production.lot_producing_ids = [Command.link(lot.id)]
        return {'belge': self.uretim_ac(production.id), 'sonuc': 'ok', 'mesaj': self.env._('Mamul serisi eklendi: %s', lot.name)}

    @api.model
    def uretim_seri_uret(self, production_id):
        production = self._production(production_id)
        if production.product_tracking not in ('lot', 'serial'):
            raise UserError(self.env._('Mamul seri/lot takipli değil.'))
        if production.product_tracking == 'serial':
            adet = int(production.product_qty - len(production.lot_producing_ids))
        else:
            adet = 0 if production.lot_producing_ids else 1
        if adet < 1:
            raise UserError(self.env._('Üretilecek seri kalmadı.'))
        lots = self._new_serials(production.product_id, adet)
        production.lot_producing_ids = [Command.link(lot.id) for lot in lots]
        return {'belge': self.uretim_ac(production.id), 'seri_ids': lots.ids, 'sonuc': 'ok',
                'mesaj': self.env._('%s mamul serisi üretildi.', len(lots))}

    @api.model
    def uretim_tamamla(self, production_id, kalan_icin_belge=True):
        production = self._production(production_id)
        if production.state == 'draft':
            production.action_confirm()
        if production.product_tracking == 'serial':
            qty = len(production.lot_producing_ids)
            if not qty:
                raise UserError(self.env._('Mamul seri numarası eklenmedi; seri üretin veya okutun.'))
        else:
            qty = production.product_qty - production.qty_produced
        production.qty_producing = qty
        production.set_qty_producing()
        context = {'skip_consumption': True, 'skip_backorder': True}
        if kalan_icin_belge and production.uom_id.compare(qty, production.product_qty) < 0:
            context['mo_ids_to_backorder'] = production.ids
        result = production.with_context(**context).button_mark_done()
        if isinstance(result, dict) and result.get('res_model'):
            raise UserError(self.env._('Üretim ek işlem istiyor (%s); masaüstü ekrandan tamamlayın.', result.get('name') or result['res_model']))
        backorder = production.production_group_id.production_ids.filtered(
            lambda mo: mo.state not in ('done', 'cancel') and mo != production)[:1]
        message = self.env._('%(ad)s tamamlandı: %(miktar)s %(urun)s.', ad=production.name, miktar=f'{qty:g}',
                             urun=production.product_id.display_name)
        return {'sonuc': 'ok', 'mesaj': message, 'kalan_belge_id': backorder.id if backorder else False,
                'seri_ids': production.lot_producing_ids.ids}

    # -------------------------------------------------------------------------
    # Etiket
    # -------------------------------------------------------------------------

    @api.model
    def etiket_url(self, seri_ids):
        ids = [int(i) for i in seri_ids or []]
        if not ids:
            raise UserError(self.env._('Yazdırılacak seri yok.'))
        return '/report/pdf/atlas_barkod.report_seri_etiket/' + ','.join(map(str, ids))
