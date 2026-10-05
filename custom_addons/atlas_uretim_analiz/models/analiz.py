from odoo import api, fields, models


def _bol(a, b):
    return a / b if b else 0.0


class AtlasUretimAnaliz(models.Model):
    _name = 'atlas.uretim.analiz'
    _description = 'Üretim Analizi'
    _order = 'date_finished desc, id desc'
    _rec_name = 'production_id'

    production_id = fields.Many2one('mrp.production', string='Üretim Emri', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Ürün', index=True)
    company_id = fields.Many2one('res.company', string='Şirket')
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_finished = fields.Datetime(string='Bitiş Tarihi')
    qty_demanded = fields.Float(string='Talep Edilen Miktar', aggregator='sum')
    qty_produced = fields.Float(string='Üretilen Miktar', aggregator='sum')
    yield_rate = fields.Float(string='Verim (%)', aggregator='avg')
    duration = fields.Float(string='Toplam Süre (dk)', aggregator='sum')
    unit_duration = fields.Float(string='Birim Süre (dk)', aggregator='avg')
    component_cost = fields.Monetary(string='Bileşen Maliyeti', aggregator='sum')
    workcenter_cost = fields.Monetary(string='İş Merkezi Maliyeti', aggregator='sum')
    employee_cost = fields.Monetary(string='İşçilik Maliyeti', aggregator='sum')
    operation_cost = fields.Monetary(string='Operasyon Maliyeti', aggregator='sum', help='İş merkezi + işçilik')
    extra_cost = fields.Monetary(string='Ek Maliyet', aggregator='sum')
    total_cost = fields.Monetary(string='Toplam Maliyet', aggregator='sum')
    unit_component_cost = fields.Monetary(string='Birim Bileşen Maliyeti', aggregator='avg')
    unit_operation_cost = fields.Monetary(string='Birim Operasyon Maliyeti', aggregator='avg')
    unit_cost = fields.Monetary(string='Birim Maliyet', aggregator='avg')
    expected_component_cost_unit = fields.Monetary(string='Beklenen Birim Bileşen', aggregator='avg')
    expected_operation_cost_unit = fields.Monetary(string='Beklenen Birim Operasyon', aggregator='avg')
    expected_total_cost_unit = fields.Monetary(string='Beklenen Birim Maliyet', aggregator='avg')
    sapma_unit = fields.Monetary(string='Birim Sapma', aggregator='avg', help='Gerçekleşen − beklenen birim maliyet')
    sapma_yuzde = fields.Float(string='Sapma (%)', aggregator='avg')

    _uretim_benzersiz = models.Constraint('unique(production_id)', 'Üretim emri başına tek analiz satırı olur.')

    # ------------------------------------------------------------------ hesaplama
    @api.model
    def _iscilik(self, uretim):
        """Operatör kayıtlı zaman kayıtlarından işçilik maliyeti (atlas_shopfloor operatörü ya da kullanıcının çalışanı)."""
        toplam = 0.0
        Zaman = self.env['mrp.workcenter.productivity']
        for z in Zaman.search([('workorder_id', 'in', uretim.workorder_ids.ids), ('date_end', '!=', False)]):
            calisan = z['atlas_employee_id'] if 'atlas_employee_id' in z._fields else False
            if not calisan and z.user_id:
                calisan = z.user_id.employee_id
            if calisan:
                toplam += z.duration / 60.0 * (calisan.sudo().hourly_cost or 0.0)
        return toplam

    @api.model
    def _beklenen(self, uretim):
        """(birim bileşen, birim operasyon) — reçete açılımı × standart maliyet; operasyon süresi × saat ücreti."""
        bom = uretim.bom_id
        if not bom:
            return 0.0, 0.0
        urun = uretim.product_id
        sirket = uretim.company_id
        bilesen = 0.0
        _bom_satirlari, satirlar = bom.explode(urun, 1.0)
        for satir, veri in satirlar:
            miktar = satir.uom_id._compute_quantity(veri['qty'], satir.product_id.uom_id)
            bilesen += miktar * satir.product_id.with_company(sirket).standard_price
        operasyon = 0.0
        bom_miktar = bom.uom_id._compute_quantity(bom.product_qty, urun.uom_id) or 1.0
        for op in bom.operation_ids:
            dakika = (op.time_cycle or 0.0) / bom_miktar
            operasyon += dakika / 60.0 * (op.workcenter_id.costs_hour or 0.0)
        return bilesen, operasyon

    @api.model
    def _guncelle(self, uretimler):
        for u in uretimler.filtered(lambda p: p.state == 'done'):
            sirket = u.company_id
            bitmis = u.move_finished_ids.filtered(lambda m: m.state == 'done' and m.product_id == u.product_id)
            uretilen = sum(m.uom_id._compute_quantity(m.quantity, u.product_id.uom_id) for m in bitmis)
            talep = u.uom_id._compute_quantity(u.product_qty, u.product_id.uom_id)
            tuketim = u.move_raw_ids.filtered(lambda m: m.state == 'done')
            bilesen = abs(sum(tuketim.mapped('value')))
            is_merkezi = sum(wo._cal_cost() for wo in u.workorder_ids)
            iscilik = self._iscilik(u)
            ek = (u.extra_cost or 0.0) * uretilen
            sure = sum(u.workorder_ids.mapped('duration'))
            toplam = bilesen + is_merkezi + iscilik + ek
            b_bilesen, b_operasyon = self._beklenen(u)
            birim = _bol(toplam, uretilen)
            beklenen = b_bilesen + b_operasyon + (u.extra_cost or 0.0)
            vals = {
                'production_id': u.id, 'product_id': u.product_id.id, 'company_id': sirket.id, 'date_finished': u.date_finished,
                'qty_demanded': talep, 'qty_produced': uretilen, 'yield_rate': _bol(uretilen, talep) * 100,
                'duration': sure, 'unit_duration': _bol(sure, uretilen),
                'component_cost': bilesen, 'workcenter_cost': is_merkezi, 'employee_cost': iscilik,
                'operation_cost': is_merkezi + iscilik, 'extra_cost': ek, 'total_cost': toplam,
                'unit_component_cost': _bol(bilesen, uretilen), 'unit_operation_cost': _bol(is_merkezi + iscilik, uretilen),
                'unit_cost': birim, 'expected_component_cost_unit': b_bilesen, 'expected_operation_cost_unit': b_operasyon,
                'expected_total_cost_unit': beklenen, 'sapma_unit': birim - beklenen if beklenen else 0.0,
                'sapma_yuzde': _bol(birim - beklenen, beklenen) * 100 if beklenen else 0.0,
            }
            mevcut = self.search([('production_id', '=', u.id)])
            if mevcut:
                mevcut.write(vals)
            else:
                self.create(vals)

    @api.model
    def action_yenile(self):
        self._guncelle(self.env['mrp.production'].search([('state', '=', 'done')]))
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def button_mark_done(self):
        sonuc = super().button_mark_done()
        biten = self.filtered(lambda p: p.state == 'done')
        if biten:
            self.env['atlas.uretim.analiz'].sudo()._guncelle(biten)
        return sonuc

    def _atlas_maliyet_yapisi(self):
        """Maliyet Yapısı raporu verisi: ürün başına bileşen ve operasyon dökümü."""
        sonuc = []
        for urun in self.mapped('product_id'):
            uretimler = self.filtered(lambda p: p.product_id == urun and p.state == 'done')
            if not uretimler:
                continue
            Analiz = self.env['atlas.uretim.analiz']
            Analiz.sudo()._guncelle(uretimler.filtered(lambda p: not Analiz.search_count([('production_id', '=', p.id)])))
            analizler = Analiz.search([('production_id', 'in', uretimler.ids)])
            bilesenler = {}
            for m in uretimler.move_raw_ids.filtered(lambda m: m.state == 'done'):
                b = bilesenler.setdefault(m.product_id, {'urun': m.product_id, 'miktar': 0.0, 'maliyet': 0.0})
                b['miktar'] += m.uom_id._compute_quantity(m.quantity, m.product_id.uom_id)
                b['maliyet'] += abs(m.value)
            operasyonlar = {}
            for wo in uretimler.workorder_ids:
                anahtar = (wo.workcenter_id, wo.name)
                o = operasyonlar.setdefault(anahtar, {'is_merkezi': wo.workcenter_id, 'operasyon': wo.name, 'sure': 0.0, 'maliyet': 0.0,
                                                      'saat_ucreti': wo.costs_hour or wo.workcenter_id.costs_hour})
                o['sure'] += wo.duration
                o['maliyet'] += wo._cal_cost()
            uretilen = sum(analizler.mapped('qty_produced'))
            sonuc.append({
                'urun': urun, 'uretimler': uretimler, 'uretilen': uretilen,
                'bilesenler': sorted(bilesenler.values(), key=lambda b: -b['maliyet']),
                'operasyonlar': list(operasyonlar.values()),
                'bilesen': sum(analizler.mapped('component_cost')), 'is_merkezi': sum(analizler.mapped('workcenter_cost')),
                'iscilik': sum(analizler.mapped('employee_cost')), 'ek': sum(analizler.mapped('extra_cost')),
                'toplam': sum(analizler.mapped('total_cost')),
                'birim': _bol(sum(analizler.mapped('total_cost')), uretilen),
                'beklenen': analizler[:1].expected_total_cost_unit,
            })
        return sonuc
