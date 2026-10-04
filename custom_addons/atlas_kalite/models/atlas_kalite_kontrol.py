from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

DURUMLAR = [('bekliyor', 'Bekliyor'), ('gecti', 'Geçti'), ('kaldi', 'Kaldı')]


class AtlasKaliteKontrol(models.Model):
    """Kalite kontrolü: bir kontrol noktasının belirli bir belge / ürün / lot için uygulanması."""
    _name = 'atlas.kalite.kontrol'
    _description = 'Kalite Kontrolü'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Kontrol No', required=True, copy=False, readonly=True, default='/', index='trigram')
    nokta_id = fields.Many2one('atlas.kalite.nokta', string='Kontrol Noktası', required=True, index=True,
                               ondelete='restrict', tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    asama = fields.Selection(related='nokta_id.asama', store=True, string='Aşama')
    test_tipi = fields.Selection(related='nokta_id.test_tipi', store=True, string='Test Tipi')
    olcum_yeri = fields.Selection(related='nokta_id.olcum_yeri', string='Kontrol Yeri')
    talimat = fields.Html(related='nokta_id.talimat')
    dokuman = fields.Binary(related='nokta_id.dokuman')
    dokuman_adi = fields.Char(related='nokta_id.dokuman_adi')
    basarisiz_mesaj = fields.Html(related='nokta_id.basarisiz_mesaj')
    engelleyici = fields.Boolean(related='nokta_id.engelleyici')
    ekip_id = fields.Many2one('atlas.kalite.ekip', string='Kalite Ekibi', compute='_compute_ekip', store=True, readonly=False)
    user_id = fields.Many2one('res.users', string='Sorumlu', compute='_compute_ekip', store=True, readonly=False)

    # Kapsam
    product_id = fields.Many2one('product.product', string='Ürün', index=True)
    lot_id = fields.Many2one('stock.lot', string='Lot / Seri', index=True)
    lot_name = fields.Char(string='Lot / Seri No')
    picking_id = fields.Many2one('stock.picking', string='Transfer', index=True, ondelete='cascade')
    production_id = fields.Many2one('mrp.production', string='Üretim Emri', index=True, ondelete='cascade')
    workorder_id = fields.Many2one('mrp.workorder', string='İş Emri', index=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Cari', compute='_compute_partner', store=True)
    workcenter_id = fields.Many2one('mrp.workcenter', related='workorder_id.workcenter_id', store=True, string='İş Merkezi')
    belge = fields.Char(string='Belge', compute='_compute_belge')

    # Sonuç
    durum = fields.Selection(DURUMLAR, string='Durum', required=True, default='bekliyor', index=True, tracking=True)
    kontrol_eden_id = fields.Many2one('res.users', string='Kontrol Eden', readonly=True, tracking=True)
    kontrol_tarihi = fields.Datetime(string='Kontrol Tarihi', readonly=True)
    notlar = fields.Text(string='Notlar')
    olcum = fields.Float(string='Ölçülen Değer', digits=(16, 4), tracking=True)
    olcum_girildi = fields.Boolean(string='Ölçüm Girildi')
    norm = fields.Float(related='nokta_id.norm')
    alt_sinir = fields.Float(related='nokta_id.alt_sinir')
    ust_sinir = fields.Float(related='nokta_id.ust_sinir')
    olcu_birimi = fields.Char(related='nokta_id.olcu_birimi')
    tolerans_disi = fields.Boolean(string='Tolerans Dışı', compute='_compute_tolerans_disi', store=True)
    foto = fields.Image(string='Fotoğraf', max_width=1920, max_height=1920, attachment=True)
    madde_ids = fields.One2many('atlas.kalite.kontrol.madde', 'kontrol_id', string='Kontrol Maddeleri')
    test_edilen = fields.Float(string='Test Edilen Miktar')
    hatali = fields.Float(string='Hatalı Miktar')
    hata_orani = fields.Float(string='Hata Oranı (%)', compute='_compute_hata_orani', store=True, aggregator='avg')
    kabul_orani = fields.Float(related='nokta_id.kabul_orani')

    uyari_ids = fields.One2many('atlas.kalite.uyari', 'kontrol_id', string='Uygunsuzluklar')
    uyari_sayisi = fields.Integer(compute='_compute_uyari_sayisi', string='Uygunsuzluk Sayısı')
    atlas_qr = fields.Char(string='QR İçeriği', compute='_compute_atlas_qr')

    _name_company_uniq = models.UniqueIndex('(name, company_id)')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('atlas.kalite.kontrol') or '/'
        kontroller = super().create(vals_list)
        for kontrol in kontroller.filtered(lambda k: k.test_tipi == 'kontrol_listesi' and not k.madde_ids):
            kontrol.madde_ids = [Command.create({'name': m.name, 'sequence': m.sequence}) for m in kontrol.nokta_id.madde_ids]
        for kontrol in kontroller.filtered(lambda k: k.test_tipi == 'sayim' and not k.test_edilen):
            kontrol.test_edilen = kontrol.nokta_id.numune_miktar
        return kontroller

    @api.depends('nokta_id')
    def _compute_ekip(self):
        for kontrol in self:
            kontrol.ekip_id = kontrol.nokta_id.ekip_id
            kontrol.user_id = kontrol.nokta_id.user_id

    @api.depends('picking_id.partner_id')
    def _compute_partner(self):
        for kontrol in self:
            kontrol.partner_id = kontrol.picking_id.partner_id.commercial_partner_id

    @api.depends('picking_id', 'production_id', 'workorder_id')
    def _compute_belge(self):
        for kontrol in self:
            if kontrol.workorder_id:
                kontrol.belge = f'{kontrol.production_id.name} / {kontrol.workorder_id.name}'
            else:
                kontrol.belge = (kontrol.picking_id or kontrol.production_id).name or ''

    @api.depends('olcum', 'olcum_girildi', 'nokta_id.alt_sinir', 'nokta_id.ust_sinir', 'test_tipi')
    def _compute_tolerans_disi(self):
        for kontrol in self:
            kontrol.tolerans_disi = kontrol.test_tipi == 'olcum' and kontrol.olcum_girildi and not (
                kontrol.nokta_id.alt_sinir <= kontrol.olcum <= kontrol.nokta_id.ust_sinir)

    @api.depends('test_edilen', 'hatali')
    def _compute_hata_orani(self):
        for kontrol in self:
            kontrol.hata_orani = 100.0 * kontrol.hatali / kontrol.test_edilen if kontrol.test_edilen else 0.0

    def _compute_uyari_sayisi(self):
        for kontrol in self:
            kontrol.uyari_sayisi = len(kontrol.uyari_ids)

    def _compute_atlas_qr(self):
        for kontrol in self:
            kontrol.atlas_qr = f'ATL:QC:{kontrol.name}'

    @api.onchange('olcum')
    def _onchange_olcum(self):
        self.olcum_girildi = True

    # -------------------------------------------------------------------------
    # Sonuçlandırma
    # -------------------------------------------------------------------------

    def _kontrol_acik(self):
        for kontrol in self:
            if kontrol.durum != 'bekliyor':
                raise UserError(self.env._('%s zaten sonuçlandırıldı.', kontrol.name))
            if (kontrol.picking_id.state == 'done' or kontrol.production_id.state == 'done'
                    or kontrol.workorder_id.state == 'done'):
                raise UserError(self.env._('%s: belge tamamlanmış; kontrol değiştirilemez.', kontrol.name))

    def _sonuclandir(self, durum):
        self.write({'durum': durum, 'kontrol_eden_id': self.env.uid, 'kontrol_tarihi': fields.Datetime.now()})
        kalanlar = self.filtered(lambda k: k.durum == 'kaldi' and k.nokta_id.otomatik_uyari and not k.uyari_ids)
        for kontrol in kalanlar:
            kontrol._uyari_olustur()
        return True

    def action_gecti(self):
        self._kontrol_acik()
        for kontrol in self:
            if kontrol.test_tipi in ('olcum', 'kontrol_listesi', 'sayim'):
                raise UserError(self.env._('%s: bu test tipinde sonuç girilen değerlere göre hesaplanır; "Değerlendir"i kullanın.', kontrol.name))
            if kontrol.test_tipi == 'foto' and not kontrol.foto:
                raise UserError(self.env._('%s: önce fotoğraf ekleyin.', kontrol.name))
        return self._sonuclandir('gecti')

    def action_kaldi(self):
        self._kontrol_acik()
        if any(k.test_tipi == 'talimat' for k in self):
            raise UserError(self.env._('Talimat tipi kontrol yalnızca onaylanabilir.'))
        return self._sonuclandir('kaldi')

    def action_degerlendir(self):
        """Ölçüm, kontrol listesi ve numune sayımında girilen değerlere göre geçti/kaldı."""
        self._kontrol_acik()
        for kontrol in self:
            if kontrol.test_tipi == 'olcum':
                if not kontrol.olcum_girildi:
                    raise UserError(self.env._('%s: ölçülen değeri girin.', kontrol.name))
                sonuc = 'kaldi' if kontrol.tolerans_disi else 'gecti'
            elif kontrol.test_tipi == 'kontrol_listesi':
                if any(not m.sonuc for m in kontrol.madde_ids):
                    raise UserError(self.env._('%s: tüm maddeleri işaretleyin.', kontrol.name))
                sonuc = 'kaldi' if any(m.sonuc == 'uygun_degil' for m in kontrol.madde_ids) else 'gecti'
            elif kontrol.test_tipi == 'sayim':
                if kontrol.test_edilen <= 0 or kontrol.hatali < 0 or kontrol.hatali > kontrol.test_edilen:
                    raise UserError(self.env._('%s: test edilen ve hatalı miktarları kontrol edin.', kontrol.name))
                sonuc = 'kaldi' if kontrol.hata_orani > kontrol.nokta_id.kabul_orani + 1e-9 else 'gecti'
            else:
                raise UserError(self.env._('%s: Geçti / Kaldı butonlarını kullanın.', kontrol.name))
            kontrol._sonuclandir(sonuc)
        return True

    def action_olcum_kaydet(self, olcum):
        self.ensure_one()
        self._kontrol_acik()
        self.write({'olcum': olcum, 'olcum_girildi': True})
        return self.action_degerlendir()

    def action_sifirla(self):
        """Sonucu geri al (belge tamamlanmadıysa)."""
        for kontrol in self:
            if (kontrol.picking_id.state == 'done' or kontrol.production_id.state == 'done'
                    or kontrol.workorder_id.state == 'done'):
                raise UserError(self.env._('%s: belge tamamlanmış; sonuç geri alınamaz.', kontrol.name))
        self.write({'durum': 'bekliyor', 'kontrol_eden_id': False, 'kontrol_tarihi': False})
        return True

    # -------------------------------------------------------------------------
    # Uygunsuzluk
    # -------------------------------------------------------------------------

    def _uyari_vals(self):
        self.ensure_one()
        baslik = self.nokta_id.name
        if self.product_id:
            baslik += f' - {self.product_id.display_name}'
        aciklama = self.notlar or ''
        if self.test_tipi == 'olcum':
            aciklama = self.env._('Ölçülen %(olcum)s %(birim)s, kabul aralığı %(alt)s - %(ust)s. ',
                                  olcum=f'{self.olcum:g}', birim=self.olcu_birimi or '', alt=f'{self.alt_sinir:g}',
                                  ust=f'{self.ust_sinir:g}') + aciklama
        elif self.test_tipi == 'sayim':
            aciklama = self.env._('%(hatali)s / %(test)s hatalı (%%%(oran)s). ', hatali=f'{self.hatali:g}',
                                  test=f'{self.test_edilen:g}', oran=f'{self.hata_orani:.1f}') + aciklama
        elif self.test_tipi == 'kontrol_listesi':
            uygunsuz = self.madde_ids.filtered(lambda m: m.sonuc == 'uygun_degil').mapped('name')
            if uygunsuz:
                aciklama = self.env._('Uygun olmayan maddeler: %s. ', ', '.join(uygunsuz)) + aciklama
        return {
            'baslik': baslik,
            'aciklama': aciklama,
            'kontrol_id': self.id,
            'nokta_id': self.nokta_id.id,
            'product_id': self.product_id.id,
            'lot_id': self.lot_id.id,
            'lot_name': self.lot_name,
            'picking_id': self.picking_id.id,
            'production_id': self.production_id.id,
            'workorder_id': self.workorder_id.id,
            'workcenter_id': self.workcenter_id.id,
            'partner_id': self.partner_id.id,
            'ekip_id': self.ekip_id.id,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'foto': self.foto,
        }

    def _uyari_olustur(self):
        return self.env['atlas.kalite.uyari'].create([k._uyari_vals() for k in self])

    def action_uyari_olustur(self):
        self.ensure_one()
        uyari = self._uyari_olustur()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.kalite.uyari', 'res_id': uyari.id,
                'view_mode': 'form', 'target': 'current'}

    def action_uyarilar(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_uyari')
        action['domain'] = [('kontrol_id', '=', self.id)]
        action['context'] = {'default_kontrol_id': self.id}
        return action

    def action_yazdir(self):
        return self.env.ref('atlas_kalite.action_report_kalite_kontrol').report_action(self)

    # -------------------------------------------------------------------------
    # Belgelerden kontrol üretimi
    # -------------------------------------------------------------------------

    @api.model
    def _uret(self, noktalar, belge_vals, mevcut, hedefler, anahtar):
        """Kontrol noktalarından eksik kontrolleri oluşturur (tekrar çağrılabilir).

        :param belge_vals: kontrolün bağlanacağı belge alanları (picking_id / production_id / workorder_id)
        :param mevcut: belgenin mevcut kontrolleri
        :param hedefler: [(product, lot, lot_name)] belgedeki ürün ve (varsa) lot/seriler
        :param anahtar: rastgele seçimin sabit kalması için belge anahtarı
        """
        vals_list = []
        for nokta in noktalar:
            uygun = [h for h in hedefler if nokta._urun_uygun(h[0])]
            if not uygun:
                continue
            urunler = list(dict.fromkeys(h[0] for h in uygun))
            if nokta.olcum_yeri == 'islem':
                anahtarlar = [(urunler[0] if len(urunler) == 1 else self.env['product.product'], False, False)]
            elif nokta.olcum_yeri == 'urun':
                anahtarlar = [(p, False, False) for p in urunler]
            else:
                anahtarlar = []
                for product in urunler:
                    if product.tracking in ('lot', 'serial'):
                        # Lot/seri henüz belli değilse kontrol doğrulama anında oluşturulur
                        anahtarlar += list(dict.fromkeys(
                            (product, lot, lot_name) for p, lot, lot_name in uygun if p == product and lot_name))
                    else:
                        anahtarlar.append((product, False, False))
            for product, lot, lot_name in anahtarlar:
                var = mevcut.filtered(lambda k: k.nokta_id == nokta and (
                    nokta.olcum_yeri == 'islem' or (k.product_id == product and (k.lot_name or False) == (lot_name or False))))
                if var or any(v['nokta_id'] == nokta.id and v['product_id'] == product.id and v['lot_name'] == lot_name
                              for v in vals_list):
                    continue
                if not nokta._secildi(f'{anahtar}:{product.id}:{lot_name or ""}'):
                    continue
                vals_list.append({
                    **belge_vals,
                    'nokta_id': nokta.id,
                    'product_id': product.id,
                    'lot_id': lot.id if lot else False,
                    'lot_name': lot_name or False,
                })
        return self.create(vals_list)

    def _engelleyenler(self):
        """Belgenin tamamlanmasını engelleyen kontroller."""
        return self.filtered(lambda k: (k.durum == 'bekliyor' and k.nokta_id.engelleyici)
                             or (k.durum == 'kaldi' and k.nokta_id.kaldi_engeller))

    def _engel_kontrol(self, belge_adi):
        engel = self._engelleyenler()
        if engel:
            satirlar = '\n'.join(f'- {k.name}: {k.nokta_id.name}{" / " + k.product_id.display_name if k.product_id else ""}'
                                 f'{" / " + k.lot_name if k.lot_name else ""} ({dict(DURUMLAR)[k.durum]})' for k in engel)
            raise UserError(self.env._('%(belge)s için tamamlanmamış / başarısız kalite kontrolleri var:\n%(liste)s',
                                       belge=belge_adi, liste=satirlar))


class AtlasKaliteKontrolMadde(models.Model):
    _name = 'atlas.kalite.kontrol.madde'
    _description = 'Kalite Kontrolü Maddesi'
    _order = 'sequence, id'

    kontrol_id = fields.Many2one('atlas.kalite.kontrol', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Madde', required=True)
    sonuc = fields.Selection([('uygun', 'Uygun'), ('uygun_degil', 'Uygun Değil')], string='Sonuç')
    notlar = fields.Char(string='Not')
