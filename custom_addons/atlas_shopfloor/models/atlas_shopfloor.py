"""Üretim alanı (Shop Floor) operatör ekranı servisi. Dış metotlar JSON'a çevrilebilir sözlük döndürür."""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

ACIK_DURUMLAR = ('blocked', 'ready', 'progress')
DURUM_ADLARI = {'blocked': 'Önceki işlem bekleniyor', 'ready': 'Hazır', 'progress': 'Çalışıyor', 'done': 'Bitti',
                'cancel': 'İptal'}


class MrpWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    atlas_employee_id = fields.Many2one('hr.employee', string='Operatör', index='btree_not_null')


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    atlas_hatali_adet = fields.Float(string='Hatalı Adet', digits='Product Unit', copy=False,
                                     help='Operatörün bildirdiği kusurlu üretim (OEE kalite oranı).')


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    atlas_talimat = fields.Html(string='Operatör Talimatı', help='Üretim alanı ekranında iş emri açılınca gösterilir.')


class AtlasShopfloor(models.AbstractModel):
    _name = 'atlas.shopfloor'
    _description = 'Üretim Alanı'

    # -------------------------------------------------------------------------
    # Yardımcılar
    # -------------------------------------------------------------------------

    @api.model
    def _wo(self, wo_id):
        wo = self.env['mrp.workorder'].browse(wo_id).exists()
        if not wo:
            raise UserError(self.env._('İş emri bulunamadı.'))
        return wo

    @api.model
    def _employee(self, employee_id):
        employee = self.env['hr.employee'].sudo().browse(employee_id).exists() if employee_id else False
        if not employee:
            raise UserError(self.env._('Önce operatör seçin.'))
        return employee

    @api.model
    def _calisan_mi(self, wo):
        return bool(wo.time_ids.filtered(lambda t: not t.date_end and t.loss_type in ('productive', 'performance')))

    @api.model
    def _gecen_dk(self, wo):
        """Toplam gerçekleşen süre (dakika), açık zaman kaydı dahil."""
        toplam = sum(t.duration for t in wo.time_ids if t.date_end)
        simdi = fields.Datetime.now()
        for t in wo.time_ids.filtered(lambda t: not t.date_end):
            toplam += (simdi - t.date_start).total_seconds() / 60.0
        return round(toplam, 2)

    # -------------------------------------------------------------------------
    # Seçim ekranları
    # -------------------------------------------------------------------------

    @api.model
    def merkezler(self):
        Wo = self.env['mrp.workorder']
        sayac = {}
        for wc, durum, adet in Wo._read_group([('state', 'in', ACIK_DURUMLAR), ('production_state', 'not in', ('draft', 'cancel', 'done'))],
                                               ['workcenter_id', 'state'], ['__count']):
            sayac.setdefault(wc.id, {})[durum] = adet
        return [{
            'id': wc.id, 'ad': wc.name, 'kod': wc.code or '', 'durum': wc.working_state,
            'hazir': sayac.get(wc.id, {}).get('ready', 0), 'calisan': sayac.get(wc.id, {}).get('progress', 0),
            'bekleyen': sayac.get(wc.id, {}).get('blocked', 0),
        } for wc in self.env['mrp.workcenter'].search([('company_id', 'in', self.env.companies.ids + [False])])]

    @api.model
    def operatorler(self):
        calisanlar = self.env['hr.employee'].sudo().search([('company_id', 'in', self.env.companies.ids)], order='name')
        return [{'id': e.id, 'ad': e.name, 'unvan': e.job_title or '', 'pin': bool(e.pin),
                 'avatar': f'/web/image/hr.employee.public/{e.id}/avatar_128'} for e in calisanlar]

    @api.model
    def operator_dogrula(self, employee_id, pin=''):
        employee = self._employee(employee_id)
        if employee.pin and employee.pin != (pin or ''):
            raise UserError(self.env._('PIN hatalı.'))
        return {'id': employee.id, 'ad': employee.name}

    @api.model
    def is_emirleri(self, workcenter_id):
        wc = self.env['mrp.workcenter'].browse(workcenter_id).exists()
        if not wc:
            raise UserError(self.env._('İş merkezi bulunamadı.'))
        wos = self.env['mrp.workorder'].search([
            ('workcenter_id', '=', wc.id), ('state', 'in', ACIK_DURUMLAR),
            ('production_state', 'not in', ('draft', 'cancel', 'done'))], order='date_start, id', limit=100)
        return {
            'merkez': {'id': wc.id, 'ad': wc.name, 'durum': wc.working_state},
            'kayip_nedenleri': [{'id': l.id, 'ad': l.name, 'tip': l.loss_type} for l in
                                self.env['mrp.workcenter.productivity.loss'].search([('manual', '=', True)])],
            'is_emirleri': [{
                'id': wo.id, 'ad': wo.name, 'uretim': wo.production_id.name, 'urun': wo.product_id.display_name,
                'miktar': wo.qty_production, 'uretilen': wo.qty_produced, 'birim': wo.production_id.uom_id.name,
                'durum': wo.state, 'durum_ad': DURUM_ADLARI.get(wo.state, wo.state), 'calisiyor': self._calisan_mi(wo),
                'baslangic': fields.Datetime.to_string(wo.date_start) if wo.date_start else '',
                'planlanan_dk': wo.duration_expected,
            } for wo in wos],
        }

    # -------------------------------------------------------------------------
    # İş emri
    # -------------------------------------------------------------------------

    @api.model
    def is_emri_ac(self, wo_id):
        wo = self._wo(wo_id)
        mo = wo.production_id
        operasyon = wo.operation_id
        tek_operasyon = len(mo.workorder_ids) == 1
        hareketler = mo.move_raw_ids.filtered(lambda m: m.state != 'cancel' and (tek_operasyon or m.operation_id == operasyon
                                                                                  or (not m.operation_id and wo == mo.workorder_ids[:1])))
        kontroller = self.env['atlas.kalite.kontrol'].search([('workorder_id', '=', wo.id)]) if 'atlas.kalite.kontrol' in self.env else []
        acik_loglar = wo.time_ids.filtered(lambda t: not t.date_end)
        sonraki = mo.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel') and w != wo)
        return {
            'id': wo.id, 'ad': wo.name, 'durum': wo.state, 'durum_ad': DURUM_ADLARI.get(wo.state, wo.state),
            'uretim': {'id': mo.id, 'ad': mo.name, 'durum': mo.state, 'qr': getattr(mo, 'atlas_qr', '') or ''},
            'urun': wo.product_id.display_name, 'birim': wo.production_id.uom_id.name,
            'miktar': wo.qty_production, 'uretilen': wo.qty_produced, 'uretiliyor': wo.qty_producing or wo.qty_remaining,
            'kalan': wo.qty_remaining, 'hatali': wo.atlas_hatali_adet,
            'merkez': {'id': wo.workcenter_id.id, 'ad': wo.workcenter_id.name, 'durum': wo.workcenter_id.working_state},
            'planlanan_dk': wo.duration_expected, 'gecen_dk': self._gecen_dk(wo), 'calisiyor': self._calisan_mi(wo),
            'operatorler': sorted({t.atlas_employee_id.sudo().name for t in acik_loglar if t.atlas_employee_id}),
            'talimat': operasyon.atlas_talimat or '' if operasyon else '',
            'talimat_metin': html2plaintext(operasyon.atlas_talimat or '') if operasyon else '',
            'bilesenler': [{
                'id': m.id, 'urun': m.product_id.display_name, 'gereken': m.product_uom_qty,
                'tuketilen': m.quantity if m.picked else 0.0, 'birim': m.uom_id.name,
                'takip': m.product_id.tracking or 'none', 'hazir': m.state == 'assigned' or m.picked,
            } for m in hareketler],
            'kalite': [{'id': k.id, 'ad': k.name, 'nokta': k.nokta_id.name, 'tip': k.test_tipi, 'durum': k.durum}
                       for k in kontroller],
            'son_islem': not sonraki,
            'hurda_urunleri': [{'id': p.id, 'ad': p.display_name} for p in (hareketler.product_id | wo.product_id)
                               if p.tracking not in ('lot', 'serial')],
        }

    @api.model
    def baslat(self, wo_id, employee_id):
        wo = self._wo(wo_id)
        employee = self._employee(employee_id)
        if wo.workcenter_id.working_state == 'blocked':
            raise UserError(self.env._('%s duruşta; önce duruşu bitirin.', wo.workcenter_id.name))
        if wo.state == 'blocked' and wo.blocked_by_workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
            raise UserError(self.env._('Önceki işlem bitmeden bu iş emri başlatılamaz.'))
        if wo.production_id.state == 'confirmed' and wo.production_id.reservation_state != 'assigned':
            wo.production_id.action_assign()
        wo.button_start()
        acik = wo.time_ids.filtered(lambda t: not t.date_end and t.user_id == self.env.user)
        acik.write({'atlas_employee_id': employee.id, 'description': self.env._('Operatör: %s', employee.name)})
        return self.is_emri_ac(wo.id)

    @api.model
    def duraklat(self, wo_id):
        wo = self._wo(wo_id)
        wo.end_all()
        return self.is_emri_ac(wo.id)

    @api.model
    def miktar_yaz(self, wo_id, uretilen, hatali=0.0):
        wo = self._wo(wo_id)
        if wo.state in ('done', 'cancel'):
            raise UserError(self.env._('İş emri kapanmış.'))
        uretilen = float(uretilen or 0.0)
        if uretilen < 0 or float(hatali or 0) < 0:
            raise UserError(self.env._('Miktar negatif olamaz.'))
        wo.write({'qty_producing': uretilen, 'atlas_hatali_adet': float(hatali or 0.0)})
        return self.is_emri_ac(wo.id)

    @api.model
    def tuketim_yaz(self, wo_id, move_id, miktar):
        wo = self._wo(wo_id)
        move = wo.production_id.move_raw_ids.filtered(lambda m: m.id == move_id)
        if not move:
            raise UserError(self.env._('Bileşen bulunamadı.'))
        if move.product_id.tracking in ('lot', 'serial'):
            raise UserError(self.env._('%s lot/seri takipli; barkod uygulamasından seri okutun.', move.product_id.display_name))
        move._set_quantity_done(float(miktar or 0.0))
        move.picked = True
        return self.is_emri_ac(wo.id)

    @api.model
    def bitir(self, wo_id, uretilen=None, hatali=None):
        wo = self._wo(wo_id)
        if uretilen is not None:
            self.miktar_yaz(wo.id, uretilen, hatali if hatali is not None else wo.atlas_hatali_adet)
        wo.button_finish()
        return self.is_emri_ac(wo.id)

    @api.model
    def uretimi_tamamla(self, wo_id):
        """Son iş emri bittiğinde üretim emrini kapatır (eksik kalanlar için yeni emir)."""
        wo = self._wo(wo_id)
        mo = wo.production_id
        if mo.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
            raise UserError(self.env._('Bitmemiş iş emirleri var.'))
        if mo.product_tracking in ('lot', 'serial') and not mo.lot_producing_ids:
            raise UserError(self.env._('Mamul seri/lot takipli; seri numaralarını barkod uygulamasından ya da üretim emrinden girin.'))
        qty = wo.qty_produced or mo.product_qty
        mo.qty_producing = qty
        context = {'skip_consumption': True, 'skip_backorder': True}
        if mo.uom_id.compare(qty, mo.product_qty) < 0:
            context['mo_ids_to_backorder'] = mo.ids
        sonuc = mo.with_context(**context).button_mark_done()
        if isinstance(sonuc, dict) and sonuc.get('res_model'):
            raise UserError(self.env._('Üretim ek işlem istiyor (%s); masaüstü ekrandan tamamlayın.', sonuc.get('name') or sonuc['res_model']))
        return {'sonuc': 'ok', 'mesaj': self.env._('%(mo)s tamamlandı (%(qty)s %(birim)s).', mo=mo.name, qty=f'{qty:g}', birim=mo.uom_id.name)}

    # -------------------------------------------------------------------------
    # Hurda, sorun, duruş
    # -------------------------------------------------------------------------

    @api.model
    def hurda(self, wo_id, product_id, miktar, neden=''):
        wo = self._wo(wo_id)
        mo = wo.production_id
        product = self.env['product.product'].browse(product_id).exists()
        miktar = float(miktar or 0.0)
        if not product or miktar <= 0:
            raise UserError(self.env._('Hurda için ürün ve pozitif miktar girin.'))
        if product.tracking in ('lot', 'serial'):
            raise UserError(self.env._('Seri/lot takipli ürünün hurdası masaüstü ekrandan yapılır.'))
        move = self.env['stock.move'].with_context(default_production_id=mo.id).create({
            'product_id': product.id, 'product_uom_qty': miktar, 'quantity': miktar, 'uom_id': product.uom_id.id,
            'location_id': mo.location_src_id.id, 'location_dest_id': mo.company_id.scrap_location_id.id or
            self.env.ref('stock.stock_location_scrapped').id, 'company_id': mo.company_id.id, 'is_scrap': True,
            'production_id': mo.id, 'origin': mo.name,
        })
        if neden:
            move.origin = f'{mo.name} - {neden}'
        move._action_scrap()
        mo.message_post(body=self.env._('Üretim alanından hurda: %(urun)s %(miktar)s %(neden)s', urun=product.display_name,
                                         miktar=f'{miktar:g}', neden=f'({neden})' if neden else ''))
        return {'sonuc': 'ok', 'mesaj': self.env._('%(miktar)s %(urun)s hurdaya ayrıldı.', miktar=f'{miktar:g}', urun=product.display_name)}

    @api.model
    def sorun_bildir(self, wo_id, baslik, aciklama='', employee_id=False):
        wo = self._wo(wo_id)
        if 'atlas.kalite.uyari' not in self.env:
            raise UserError(self.env._('Kalite modülü kurulu değil.'))
        employee = self.env['hr.employee'].sudo().browse(employee_id).exists() if employee_id else False
        uyari = self.env['atlas.kalite.uyari'].create({
            'baslik': baslik or self.env._('Üretim alanı sorunu'),
            'aciklama': (aciklama or '') + (f'<p>Bildiren: {employee.name}</p>' if employee else ''),
            'product_id': wo.product_id.id, 'production_id': wo.production_id.id, 'workorder_id': wo.id,
            'workcenter_id': wo.workcenter_id.id, 'oncelik': '2',
        })
        return {'sonuc': 'ok', 'mesaj': self.env._('Uygunsuzluk açıldı: %s', uyari.name)}

    @api.model
    def durus_bildir(self, workcenter_id, loss_id, aciklama='', employee_id=False):
        wc = self.env['mrp.workcenter'].browse(workcenter_id).exists()
        loss = self.env['mrp.workcenter.productivity.loss'].browse(loss_id).exists()
        if not wc or not loss:
            raise UserError(self.env._('İş merkezi ve duruş nedeni seçin.'))
        # Çalışan iş emirlerinin sayacı durur
        self.env['mrp.workorder'].search([('workcenter_id', '=', wc.id), ('state', '=', 'progress')]).end_all()
        self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': wc.id, 'loss_id': loss.id, 'description': aciklama or loss.name,
            'atlas_employee_id': employee_id or False, 'company_id': wc.company_id.id or self.env.company.id,
        })
        return {'sonuc': 'uyari', 'mesaj': self.env._('%(wc)s duruşta: %(neden)s', wc=wc.name, neden=loss.name)}

    @api.model
    def durus_bitir(self, workcenter_id):
        wc = self.env['mrp.workcenter'].browse(workcenter_id).exists()
        if not wc:
            raise UserError(self.env._('İş merkezi bulunamadı.'))
        if wc.working_state == 'blocked':
            wc.unblock()
        return {'sonuc': 'ok', 'mesaj': self.env._('%s duruşu bitti.', wc.name)}

    @api.model
    def kalite_sonuc(self, kontrol_id, islem, degerler=None):
        return self.env['atlas.barkod'].kalite_sonuc(kontrol_id, islem, degerler)
