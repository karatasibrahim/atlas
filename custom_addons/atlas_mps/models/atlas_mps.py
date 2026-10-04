from collections import defaultdict
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

AYLAR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']
SATIR_ALANLARI = ('tahmini_talep', 'ikmal_miktar')


class AtlasMps(models.Model):
    """Ana üretim planı satırı: bir deponun bir ürünü için dönemsel plan."""
    _name = 'atlas.mps'
    _description = 'Ana Üretim Planı'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    warehouse_id = fields.Many2one('stock.warehouse', string='Depo', required=True, index=True,
                                   default=lambda self: self.env['stock.warehouse'].search(
                                       [('company_id', '=', self.env.company.id)], limit=1),
                                   domain="[('company_id', '=', company_id)]")
    product_id = fields.Many2one('product.product', string='Ürün', required=True, index=True,
                                 domain="[('is_storable', '=', True)]")
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Birim')
    tedarik = fields.Selection([('uretim', 'Üretim'), ('satinalma', 'Satınalma')], string='Tedarik',
                               compute='_compute_tedarik', store=True, readonly=False, required=True, precompute=True)
    bom_id = fields.Many2one('mrp.bom', string='Ürün Reçetesi', compute='_compute_tedarik', store=True, readonly=False, precompute=True,
                             domain="['|', ('product_id', '=', product_id), '&', ('product_id', '=', False), ('product_tmpl_id', '=', product_tmpl_id)]")
    guvenlik_stok = fields.Float(string='Güvenlik Stoğu', digits='Product Unit',
                                 help='Her dönem sonunda elde kalması hedeflenen miktar.')
    min_ikmal = fields.Float(string='En Az İkmal', digits='Product Unit', help='Öneri bundan küçükse bu miktara yuvarlanır.')
    max_ikmal = fields.Float(string='En Çok İkmal', digits='Product Unit', help='Bir dönemde önerilecek en çok miktar (0 = sınırsız).')
    ikmal_tetik = fields.Selection([('manuel', 'Elle'), ('otomatik', 'Otomatik')], string='İkmal', default='manuel', required=True,
                                   help='Otomatik: günlük görev ilk dönemin önerisini sipariş eder.')
    tahmin_ids = fields.One2many('atlas.mps.tahmin', 'mps_id', string='Dönem Tahminleri')

    _urun_depo_uniq = models.UniqueIndex('(company_id, warehouse_id, product_id)', 'Bu ürün için bu depoda zaten plan var.')

    @api.depends('product_id', 'company_id')
    def _compute_tedarik(self):
        for mps in self:
            if not mps.product_id:
                continue
            bom = self.env['mrp.bom']._bom_find(mps.product_id, company_id=mps.company_id.id, bom_type='normal').get(mps.product_id)
            mps.bom_id = bom
            mps.tedarik = 'uretim' if bom else 'satinalma'

    @api.depends('product_id', 'warehouse_id')
    def _compute_display_name(self):
        for mps in self:
            mps.display_name = f'{mps.product_id.display_name} ({mps.warehouse_id.code or ""})'

    # -------------------------------------------------------------------------
    # Dönemler
    # -------------------------------------------------------------------------

    @api.model
    def _periyotlar(self, company=None, bugun=None):
        """[(başlangıç, bitiş_hariç, etiket)] — ilk dönem bugünü içerir."""
        company = company or self.env.company
        bugun = bugun or fields.Date.context_today(self)
        tip, sayi = company.atlas_mps_periyot, max(company.atlas_mps_periyot_sayisi, 1)
        if tip == 'ay':
            bas = bugun.replace(day=1)
            adim = relativedelta(months=1)
        elif tip == 'hafta':
            bas = bugun - timedelta(days=bugun.weekday())
            adim = timedelta(weeks=1)
        else:
            bas = bugun
            adim = timedelta(days=1)
        sonuc = []
        for _i in range(sayi):
            son = bas + adim
            if tip == 'ay':
                etiket = f'{AYLAR[bas.month - 1]} {bas.year}'
            elif tip == 'hafta':
                etiket = f'{bas.isocalendar()[1]}. Hf ({bas.strftime("%d.%m")})'
            else:
                etiket = bas.strftime('%d.%m')
            sonuc.append((bas, son, etiket))
            bas = son
        return sonuc

    @staticmethod
    def _donem_index(periyotlar, tarih):
        """Tarihin düştüğü dönem; ilk dönemden önceki (gecikmiş) tarihler ilk döneme, son dönemden sonrakiler None."""
        if isinstance(tarih, datetime):
            tarih = tarih.date()
        for i, (_bas, son, _e) in enumerate(periyotlar):
            if tarih < son:
                return i
        return None

    # -------------------------------------------------------------------------
    # Hesap
    # -------------------------------------------------------------------------

    def _depo_lokasyonlari(self, warehouse):
        return self.env['stock.location'].search([('id', 'child_of', warehouse.view_location_id.id), ('usage', '=', 'internal')])

    def _hareketler(self, warehouse, periyotlar):
        """Depoya giren ve depodan çıkan açık hareketler, dönem dönem: {product_id: {'gercek': [..], 'gelen': [..]}}"""
        n = len(periyotlar)
        sonuc = defaultdict(lambda: {'gercek': [0.0] * n, 'gelen': [0.0] * n})
        products = self.product_id
        lokasyonlar = self._depo_lokasyonlari(warehouse)
        if not lokasyonlar:
            return sonuc
        lok = set(lokasyonlar.ids)
        hareketler = self.env['stock.move'].search([
            ('product_id', 'in', products.ids), ('state', 'not in', ('done', 'cancel')),
            '|', ('location_id', 'in', lokasyonlar.ids), ('location_dest_id', 'in', lokasyonlar.ids)])
        for move in hareketler:
            if move.state == 'draft' and not (move.raw_material_production_id or move.production_id):
                continue
            kaynak_ic, hedef_ic = move.location_id.id in lok, move.location_dest_id.id in lok
            if kaynak_ic == hedef_ic:
                continue
            i = self._donem_index(periyotlar, move.date)
            if i is None:
                continue
            sonuc[move.product_id.id]['gercek' if kaynak_ic else 'gelen'][i] += move.product_qty
        # Onaylanmamış satınalma teklifleri de beklenen girişe dahil
        if 'purchase.order.line' in self.env:
            satirlar = self.env['purchase.order.line'].search([
                ('product_id', 'in', products.ids), ('order_id.state', 'in', ('draft', 'sent', 'to approve')),
                ('order_id.picking_type_id.warehouse_id', '=', warehouse.id)])
            for line in satirlar:
                i = self._donem_index(periyotlar, line.date_planned or fields.Datetime.now())
                if i is not None:
                    sonuc[line.product_id.id]['gelen'][i] += line.product_uom_qty
        return sonuc

    def _baslangic_stoklari(self, warehouse):
        lokasyonlar = self._depo_lokasyonlari(warehouse)
        veri = self.env['stock.quant']._read_group(
            [('product_id', 'in', self.product_id.ids), ('location_id', 'in', lokasyonlar.ids)],
            ['product_id'], ['quantity:sum'])
        return {product.id: qty for product, qty in veri}

    def _bilesen_oranlari(self):
        """Üretilen planlar için: {bileşen product_id: 1 birim üst ürün başına miktar} (kitler açılarak)."""
        self.ensure_one()
        if self.tedarik != 'uretim' or not self.bom_id:
            return {}
        bom = self.bom_id
        # explode: reçetenin kaç kez uygulanacağı (1 birim ürün = reçete miktarının kesri)
        kez = self.product_id.uom_id._compute_quantity(1.0, bom.uom_id) / (bom.product_qty or 1.0)
        _boms, lines = bom.explode(self.product_id, kez)
        oran = defaultdict(float)
        for line, data in lines:
            if line.product_id.type != 'consu':
                continue
            oran[line.product_id.id] += line.uom_id._compute_quantity(data['qty'], line.product_id.uom_id)
        return oran

    def _sirala(self):
        """Üst ürünler önce (dolaylı talep alt ürünlere aktarılabilsin)."""
        plan_urun = {(m.warehouse_id.id, m.product_id.id): m for m in self}
        cocuklar = {m.id: [] for m in self}
        giris = {m.id: 0 for m in self}
        oranlar = {}
        for m in self:
            oranlar[m.id] = m._bilesen_oranlari()
            for urun_id in oranlar[m.id]:
                cocuk = plan_urun.get((m.warehouse_id.id, urun_id))
                if cocuk and cocuk != m:
                    cocuklar[m.id].append(cocuk)
                    giris[cocuk.id] += 1
        sira, kuyruk = [], [m for m in self if not giris[m.id]]
        while kuyruk:
            m = kuyruk.pop(0)
            sira.append(m)
            for c in cocuklar[m.id]:
                giris[c.id] -= 1
                if not giris[c.id]:
                    kuyruk.append(c)
        sira += [m for m in self if m not in sira]  # döngü varsa kalanlar
        return sira, oranlar

    def _hesapla(self, periyotlar=None):
        """{mps_id: [dönem sözlüğü]}"""
        company = self.company_id[:1] or self.env.company
        periyotlar = periyotlar or self._periyotlar(company)
        n = len(periyotlar)
        talep_yontemi = company.atlas_mps_talep
        sonuc = {}
        for warehouse in self.warehouse_id:
            planlar = self.filtered(lambda m: m.warehouse_id == warehouse)
            hareket = planlar._hareketler(warehouse, periyotlar)
            stok = planlar._baslangic_stoklari(warehouse)
            sira, oranlar = planlar._sirala()
            dolayli = defaultdict(lambda: [0.0] * n)
            for mps in sira:
                uom = mps.product_id.uom_id
                tahmin = mps._tahmin_haritasi(periyotlar)
                h = hareket[mps.product_id.id]
                eldeki = stok.get(mps.product_id.id, 0.0)
                donemler = []
                for i, (bas, _son, etiket) in enumerate(periyotlar):
                    kayit = tahmin.get(i)
                    tahmini = kayit.tahmini_talep if kayit else 0.0
                    gercek = h['gercek'][i]
                    talep = {'en_buyuk': max(tahmini, gercek), 'tahmin': tahmini, 'gercek': gercek}[talep_yontemi]
                    dol = dolayli[mps.product_id.id][i]
                    gelen = h['gelen'][i]
                    oncesi = eldeki - talep - dol + gelen
                    elle = bool(kayit and kayit.ikmal_elle)
                    if elle:
                        ikmal = kayit.ikmal_miktar
                    else:
                        ihtiyac = mps.guvenlik_stok - oncesi
                        ikmal = 0.0
                        if uom.compare(ihtiyac, 0.0) > 0:
                            ikmal = max(ihtiyac, mps.min_ikmal)
                            if mps.max_ikmal > 0:
                                ikmal = min(ikmal, mps.max_ikmal)
                            ikmal = uom.round(ikmal)
                    sonu = oncesi + ikmal
                    if uom.compare(sonu, mps.guvenlik_stok) < 0:
                        durum = 'eksik'
                    elif uom.compare(ikmal, 0.0) > 0 and uom.compare(sonu - ikmal, mps.guvenlik_stok) >= 0:
                        durum = 'fazla'
                    else:
                        durum = 'yeterli'
                    donemler.append({
                        'tarih': fields.Date.to_string(bas), 'etiket': etiket,
                        'baslangic_stok': eldeki, 'tahmini_talep': tahmini, 'gercek_talep': gercek,
                        'dolayli_talep': dol, 'gelen': gelen, 'ikmal': ikmal, 'ikmal_elle': elle,
                        'stok_sonu': sonu, 'durum': durum,
                    })
                    # Önerilen üretim, bileşen planlarına dolaylı talep olarak iner
                    for urun_id, oran in oranlar[mps.id].items():
                        dolayli[urun_id][i] += ikmal * oran
                    eldeki = sonu
                sonuc[mps.id] = donemler
        return sonuc

    def _tahmin_haritasi(self, periyotlar):
        self.ensure_one()
        harita = {}
        for kayit in self.tahmin_ids:
            i = self._donem_index(periyotlar, kayit.tarih)
            if i is not None and kayit.tarih >= periyotlar[0][0]:
                harita.setdefault(i, kayit)
        return harita

    # -------------------------------------------------------------------------
    # Ekran (OWL) metotları
    # -------------------------------------------------------------------------

    @api.model
    def ekran_verisi(self, warehouse_id=False):
        company = self.env.company
        depolar = self.env['stock.warehouse'].search([('company_id', '=', company.id)])
        warehouse = depolar.filtered(lambda w: w.id == warehouse_id)[:1] if warehouse_id else self.env['stock.warehouse']
        domain = [('company_id', '=', company.id)] + ([('warehouse_id', '=', warehouse.id)] if warehouse else [])
        planlar = self.search(domain)
        periyotlar = self._periyotlar(company)
        hesap = planlar._hesapla(periyotlar)
        return {
            'periyotlar': [{'etiket': e, 'tarih': fields.Date.to_string(b)} for b, _s, e in periyotlar],
            'depolar': [{'id': w.id, 'ad': w.name} for w in depolar],
            'depo_id': warehouse.id or False,
            'yonetici': self.env.user.has_group('mrp.group_mrp_manager'),
            'talep_yontemi': dict(self.env['res.company']._fields['atlas_mps_talep'].selection)[company.atlas_mps_talep],
            'satirlar': [{
                'id': m.id, 'urun': m.product_id.display_name, 'urun_id': m.product_id.id, 'depo': m.warehouse_id.code,
                'birim': m.uom_id.name, 'tedarik': m.tedarik, 'tedarik_ad': dict(m._fields['tedarik'].selection)[m.tedarik],
                'guvenlik_stok': m.guvenlik_stok, 'min_ikmal': m.min_ikmal, 'max_ikmal': m.max_ikmal,
                'ikmal_tetik': m.ikmal_tetik, 'donemler': hesap[m.id],
                'dolayli_var': any(d['dolayli_talep'] for d in hesap[m.id]),
            } for m in planlar],
        }

    def tahmin_yaz(self, donem_tarihi, alan, deger):
        """Bir dönemin tahmini talebini veya önerilen ikmalini yazar (ikmal yazılırsa elle değiştirilmiş sayılır)."""
        self.ensure_one()
        if alan not in SATIR_ALANLARI:
            raise UserError(self.env._('Bu alan değiştirilemez.'))
        if not self.env.user.has_group('mrp.group_mrp_manager'):
            raise UserError(self.env._('Planı yalnızca üretim yöneticileri değiştirebilir.'))
        tarih = fields.Date.to_date(donem_tarihi)
        periyotlar = self._periyotlar(self.company_id)
        i = self._donem_index(periyotlar, tarih)
        if i is None:
            raise UserError(self.env._('Dönem bulunamadı.'))
        kayit = self._tahmin_haritasi(periyotlar).get(i)
        vals = {alan: max(float(deger or 0.0), 0.0)}
        if alan == 'ikmal_miktar':
            vals['ikmal_elle'] = True
        if kayit:
            kayit.write(vals)
        else:
            self.env['atlas.mps.tahmin'].create({'mps_id': self.id, 'tarih': periyotlar[i][0], **vals})
        return True

    def oneriye_don(self, donem_tarihi):
        """Elle girilen ikmali bırakıp hesaplanan öneriye döner."""
        self.ensure_one()
        periyotlar = self._periyotlar(self.company_id)
        i = self._donem_index(periyotlar, fields.Date.to_date(donem_tarihi))
        kayit = self._tahmin_haritasi(periyotlar).get(i) if i is not None else False
        if kayit:
            kayit.write({'ikmal_elle': False, 'ikmal_miktar': 0.0})
        return True

    # -------------------------------------------------------------------------
    # Sipariş
    # -------------------------------------------------------------------------

    def _rota(self):
        self.ensure_one()
        if self.tedarik == 'uretim':
            return self.warehouse_id.manufacture_pull_id.route_id
        return self.warehouse_id.buy_pull_id.route_id

    def siparis_ver(self, donem_tarihi=False):
        """Önerilen ikmali (varsayılan: ilk dönem) üretim emri / satınalma teklifi olarak oluşturur."""
        if not self.env.user.has_group('mrp.group_mrp_manager') and not self.env.su:
            raise UserError(self.env._('Siparişi yalnızca üretim yöneticileri verebilir.'))
        company = self.company_id[:1] or self.env.company
        periyotlar = self._periyotlar(company)
        i = self._donem_index(periyotlar, fields.Date.to_date(donem_tarihi)) if donem_tarihi else 0
        if i is None:
            raise UserError(self.env._('Dönem bulunamadı.'))
        hesap = self._hesapla(periyotlar)
        Rule = self.env['stock.rule']
        olusan = []
        for mps in self:
            donem = hesap[mps.id][i]
            miktar = donem['ikmal']
            if mps.uom_id.compare(miktar, 0.0) <= 0:
                continue
            rota = mps._rota()
            if not rota:
                raise UserError(self.env._('%(urun)s: %(depo)s deposunda %(tip)s rotası yok.', urun=mps.product_id.display_name,
                                           depo=mps.warehouse_id.name, tip=dict(mps._fields['tedarik'].selection)[mps.tedarik]))
            bas = periyotlar[i][0]
            planlanan = max(datetime.combine(bas, time(12)), fields.Datetime.now())
            values = {
                'date_planned': planlanan, 'date_deadline': planlanan, 'warehouse_id': mps.warehouse_id,
                'route_ids': rota, 'company_id': mps.company_id,
            }
            if mps.tedarik == 'satinalma' and not mps.product_id.seller_ids.filtered(
                    lambda s: s.company_id in (mps.company_id, self.env['res.company'])):
                raise UserError(self.env._('%s için tedarikçi tanımlı değil; ürünün Satınalma sekmesine tedarikçi ekleyin.',
                                           mps.product_id.display_name))
            if mps.tedarik == 'uretim':
                if not mps.bom_id:
                    raise UserError(self.env._('%s için ürün reçetesi seçilmedi.', mps.product_id.display_name))
                values['bom_id'] = mps.bom_id
            values.update(date_order=mps.product_id._get_dates_info(planlanan, mps.warehouse_id.lot_stock_id, route_ids=rota)['date_order'])
            Rule.run([Rule.Procurement(mps.product_id, miktar, mps.uom_id, mps.warehouse_id.lot_stock_id,
                                       mps.product_id.display_name, 'MPS', mps.company_id, values)])
            kayit = mps._tahmin_haritasi(periyotlar).get(i)
            if kayit and kayit.ikmal_elle:
                kayit.write({'ikmal_elle': False, 'ikmal_miktar': 0.0})
            olusan.append(f'{mps.product_id.display_name}: {miktar:g} {mps.uom_id.name}')
        if not olusan:
            return {'mesaj': self.env._('Sipariş edilecek öneri yok.'), 'sonuc': 'uyari'}
        return {'mesaj': self.env._('Sipariş oluşturuldu (%(donem)s): %(liste)s', donem=periyotlar[i][2], liste=', '.join(olusan)),
                'sonuc': 'ok'}

    @api.model
    def _cron_otomatik_ikmal(self):
        for company in self.env['res.company'].search([]):
            planlar = self.with_company(company).search([('company_id', '=', company.id), ('ikmal_tetik', '=', 'otomatik')])
            for mps in planlar:
                try:
                    with self.env.cr.savepoint():
                        mps.siparis_ver()
                except UserError:
                    continue

    def action_ekran(self):
        return {'type': 'ir.actions.client', 'tag': 'atlas_mps.ekran', 'name': self.env._('Ana Üretim Planı')}


class AtlasMpsTahmin(models.Model):
    _name = 'atlas.mps.tahmin'
    _description = 'MPS Dönem Tahmini'
    _order = 'tarih'

    mps_id = fields.Many2one('atlas.mps', string='Plan', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(related='mps_id.product_id', store=True, string='Ürün')
    warehouse_id = fields.Many2one(related='mps_id.warehouse_id', store=True, string='Depo')
    tarih = fields.Date(string='Dönem Başı', required=True)
    tahmini_talep = fields.Float(string='Tahmini Talep', digits='Product Unit')
    ikmal_miktar = fields.Float(string='Elle İkmal', digits='Product Unit')
    ikmal_elle = fields.Boolean(string='İkmal Elle Girildi')
