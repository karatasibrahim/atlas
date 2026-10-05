import logging
import re
import secrets
import socket
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

CIHAZ_TURLERI = [('terazi', 'Terazi'), ('yazici', 'Etiket Yazıcı (ZPL)'), ('sayac', 'Makine Sayacı'), ('sensor', 'Sensör')]
CEVRIMICI_SURE = timedelta(minutes=5)
VARSAYILAN_ZPL = """^XA
^CI28
^FO30,25^A0N,34,34^FD{urun}^FS
^FO30,70^A0N,26,26^FDKod: {kod}^FS
^FO30,105^A0N,44,44^FD{miktar} {birim}^FS
^FO30,160^A0N,22,22^FD{tarih}  {lot}^FS
^FO30,195^BY2^BCN,70,Y,N,N^FD{barkod}^FS
^PQ{adet}
^XZ"""


class AtlasIotCihaz(models.Model):
    _name = 'atlas.iot.cihaz'
    _description = 'IoT Cihazı'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'tur, name'

    name = fields.Char(string='Cihaz', required=True, tracking=True)
    active = fields.Boolean(default=True)
    tur = fields.Selection(CIHAZ_TURLERI, string='Tür', required=True, default='terazi')
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    konum = fields.Char(string='Konum', help='ör. Sevkiyat tartı noktası')
    # Terazi (tarayıcıdan Web Serial)
    baud = fields.Integer(string='Baud', default=9600)
    deger_deseni = fields.Char(string='Okuma Deseni', default=r'([-+]?\d+[.,]?\d*)\s*(kg|g)?',
                               help='Teraziden gelen satırdan ağırlığı yakalayan düzenli ifade (ilk grup sayı, ikinci grup birim).')
    istek_komutu = fields.Char(string='İstek Komutu', help='Terazi ağırlığı yalnız istenince gönderiyorsa (ör. W veya P). Boşsa sürekli okunur.')
    kararlilik = fields.Integer(string='Kararlı Okuma Sayısı', default=3,
                                help='Ağırlık bu kadar ardışık okumada değişmezse kabul edilir.')
    # Yazıcı
    ip = fields.Char(string='IP Adresi')
    port = fields.Integer(string='Port', default=9100)
    zpl_sablonu = fields.Text(string='ZPL Şablonu', default=VARSAYILAN_ZPL,
                              help='Yer tutucular: {urun} {kod} {barkod} {miktar} {birim} {lot} {tarih} {adet}')
    # Sayaç / sensör (HTTP ile veri gönderir)
    anahtar = fields.Char(string='Cihaz Anahtarı', copy=False, groups='mrp.group_mrp_manager,base.group_system',
                          default=lambda self: secrets.token_urlsafe(20))
    veri_url = fields.Char(string='Veri Adresi', compute='_compute_veri_url', compute_sudo=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='İş Merkezi')
    durus_nedeni_id = fields.Many2one('mrp.workcenter.productivity.loss', string='Otomatik Duruş Nedeni',
                                      help='Makine "durdu" bildirince iş merkezi bu nedenle duruşa alınır.')
    birim = fields.Char(string='Ölçü Birimi', help='Sensör için ör. °C, bar')
    alt_sinir = fields.Float(string='Alt Sınır')
    ust_sinir = fields.Float(string='Üst Sınır')
    sinir_aktif = fields.Boolean(string='Sınır Alarmı')
    sorumlu_id = fields.Many2one('res.users', string='Sorumlu', default=lambda self: self.env.user)
    # Durum
    son_deger = fields.Float(string='Son Değer', readonly=True, digits=(16, 3))
    son_gorulme = fields.Datetime(string='Son Veri', readonly=True)
    cevrimici = fields.Boolean(string='Çevrimiçi', compute='_compute_cevrimici')
    olcum_ids = fields.One2many('atlas.iot.olcum', 'cihaz_id', string='Ölçümler')
    sayac_toplam = fields.Float(string='Toplam Sayım', readonly=True)

    @api.depends('anahtar', 'tur')
    def _compute_veri_url(self):
        for c in self:
            c.veri_url = f'{c.get_base_url()}/iot/veri/{c.anahtar}' if c.anahtar and c.tur in ('sayac', 'sensor') else False

    @api.depends('son_gorulme')
    def _compute_cevrimici(self):
        simdi = fields.Datetime.now()
        for c in self:
            c.cevrimici = bool(c.son_gorulme) and simdi - c.son_gorulme < CEVRIMICI_SURE

    @api.constrains('deger_deseni')
    def _check_desen(self):
        for c in self.filtered('deger_deseni'):
            try:
                re.compile(c.deger_deseni)
            except re.error as hata:
                raise ValidationError(self.env._('Okuma deseni geçersiz: %s', hata)) from hata

    # -------------------------------------------------------------------------
    # Yazıcı
    # -------------------------------------------------------------------------

    def _zpl_gonder(self, zpl):
        self.ensure_one()
        if self.tur != 'yazici' or not self.ip:
            raise UserError(self.env._('%s bir ağ etiket yazıcısı değil veya IP adresi yok.', self.name))
        try:
            with socket.create_connection((self.ip, self.port or 9100), timeout=5) as baglanti:
                baglanti.sendall(zpl.encode('utf-8'))
        except OSError as hata:
            raise UserError(self.env._('%(yazici)s yazıcısına bağlanılamadı (%(ip)s:%(port)s): %(hata)s',
                                       yazici=self.name, ip=self.ip, port=self.port, hata=hata)) from hata
        self.son_gorulme = fields.Datetime.now()
        return True

    @staticmethod
    def _zpl_temizle(deger):
        # ZPL alan ayırıcıları metinde olmamalı
        return str(deger if deger not in (False, None) else '').replace('^', ' ').replace('~', ' ')

    def _zpl_olustur(self, urun, miktar=None, lot=None, adet=1):
        self.ensure_one()
        degerler = {
            'urun': urun.display_name, 'kod': urun.default_code or '', 'barkod': urun.barcode or urun.default_code or str(urun.id),
            'miktar': ('%g' % miktar).replace('.', ',') if miktar is not None else '', 'birim': urun.uom_id.name if miktar is not None else '',
            'lot': lot or '', 'tarih': fields.Date.context_today(self).strftime('%d.%m.%Y'), 'adet': max(int(adet or 1), 1),
        }
        zpl = self.zpl_sablonu or VARSAYILAN_ZPL
        for k, v in degerler.items():
            zpl = zpl.replace('{%s}' % k, self._zpl_temizle(v))
        return zpl

    def action_test_etiketi(self):
        self.ensure_one()
        self._zpl_gonder('^XA^CI28^FO40,40^A0N,40,40^FDAtlas test etiketi^FS^FO40,100^A0N,28,28^FD%s^FS^XZ' % self._zpl_temizle(self.name))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('Test etiketi gönderildi.')}}

    # -------------------------------------------------------------------------
    # Sayaç / sensör verisi
    # -------------------------------------------------------------------------

    def _veri_isle(self, veri):
        """Cihazdan gelen veri. Sayaç: {adet, hatali, durum: calisiyor|durdu, aciklama}. Sensör: {deger}."""
        self.ensure_one()
        simdi = fields.Datetime.now()
        sonuc = {}
        if self.tur == 'sayac':
            sonuc = self._sayac_isle(veri)
        elif self.tur == 'sensor':
            try:
                deger = float(str(veri.get('deger', veri.get('value'))).replace(',', '.'))
            except (TypeError, ValueError) as hata:
                raise UserError(self.env._('Geçersiz değer.')) from hata
            self.env['atlas.iot.olcum'].create({'cihaz_id': self.id, 'deger': deger})
            self.son_deger = deger
            sonuc = {'deger': deger, 'alarm': self._sinir_kontrol(deger)}
        else:
            raise UserError(self.env._('Bu cihaz türü veri göndermez.'))
        self.son_gorulme = simdi
        return sonuc

    def _sinir_kontrol(self, deger):
        self.ensure_one()
        if not self.sinir_aktif or self.alt_sinir <= deger <= self.ust_sinir:
            return False
        acik = self.activity_ids.filtered(lambda a: a.summary and a.summary.startswith('Sınır aşımı'))
        if not acik and self.sorumlu_id:
            self.activity_schedule('mail.mail_activity_data_warning', user_id=self.sorumlu_id.id,
                                   summary=self.env._('Sınır aşımı: %(deger)s %(birim)s', deger=deger, birim=self.birim or ''),
                                   note=self.env._('İzin verilen aralık %(alt)s – %(ust)s', alt=self.alt_sinir, ust=self.ust_sinir))
        self.message_post(body=self.env._('Sınır aşımı: %(deger)s %(birim)s (aralık %(alt)s – %(ust)s)', deger=deger,
                                          birim=self.birim or '', alt=self.alt_sinir, ust=self.ust_sinir))
        return True

    def _sayac_isle(self, veri):
        self.ensure_one()
        if not self.workcenter_id:
            raise UserError(self.env._('%s sayacına iş merkezi atanmamış.', self.name))
        Shopfloor = self.env['atlas.shopfloor']
        wc = self.workcenter_id
        sonuc = {'is_merkezi': wc.name}
        durum = (veri.get('durum') or veri.get('state') or '').lower()
        if durum in ('durdu', 'stopped', 'stop', 'down') and wc.working_state != 'blocked':
            neden = self.durus_nedeni_id or self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'availability')], limit=1)
            if neden:
                Shopfloor.durus_bildir(wc.id, neden.id, veri.get('aciklama') or self.env._('%s bildirdi', self.name))
                sonuc['durus'] = True
        elif durum in ('calisiyor', 'running', 'run', 'up') and wc.working_state == 'blocked':
            Shopfloor.durus_bitir(wc.id)
            sonuc['durus'] = False
        try:
            adet = float(veri.get('adet', veri.get('count', 0)) or 0)
            hatali = float(veri.get('hatali', veri.get('reject', 0)) or 0)
        except (TypeError, ValueError) as hata:
            raise UserError(self.env._('Geçersiz sayım.')) from hata
        if adet < 0 or hatali < 0:
            raise UserError(self.env._('Sayım negatif olamaz.'))
        if adet or hatali:
            # çalışan = süresi açık (durdurulmamış) iş emri
            wo = self.env['mrp.workorder'].search([('workcenter_id', '=', wc.id), ('state', '=', 'progress'),
                                                   ('time_ids', 'any', [('date_end', '=', False)])], order='date_start', limit=1)
            self.env['atlas.iot.olcum'].create({'cihaz_id': self.id, 'deger': adet, 'hatali': hatali, 'workorder_id': wo.id or False})
            if wo:
                # makine sayımı esastır: iş emrinin üretilen/hatalı miktarı bu iş emri için gelen sayımların toplamıdır
                olcumler = self.env['atlas.iot.olcum'].search([('workorder_id', '=', wo.id)])
                wo.write({'qty_producing': sum(olcumler.mapped('deger')), 'atlas_hatali_adet': sum(olcumler.mapped('hatali'))})
                sonuc.update({'is_emri': wo.display_name, 'uretilen': wo.qty_producing, 'hatali': wo.atlas_hatali_adet})
            else:
                sonuc['uyari'] = self.env._('Çalışan iş emri yok; sayım yalnızca kaydedildi.')
            self.sayac_toplam += adet
            self.son_deger = adet
        return sonuc

    def action_anahtar_yenile(self):
        for c in self:
            c.anahtar = secrets.token_urlsafe(20)
        return True


class AtlasIotOlcum(models.Model):
    _name = 'atlas.iot.olcum'
    _description = 'IoT Ölçümü'
    _order = 'zaman desc, id desc'

    cihaz_id = fields.Many2one('atlas.iot.cihaz', string='Cihaz', required=True, ondelete='cascade', index=True)
    zaman = fields.Datetime(string='Zaman', default=fields.Datetime.now, required=True, index=True)
    deger = fields.Float(string='Değer', digits=(16, 3))
    hatali = fields.Float(string='Hatalı')
    workorder_id = fields.Many2one('mrp.workorder', string='İş Emri', ondelete='set null')

    @api.autovacuum
    def _gc_eski_olcumler(self):
        """Sensör ölçümleri 180 günden eski olanlar temizlenir."""
        sinir = fields.Datetime.now() - timedelta(days=180)
        self.search([('zaman', '<', sinir), ('cihaz_id.tur', '=', 'sensor')], limit=50000).unlink()


class AtlasIotTartim(models.Model):
    _name = 'atlas.iot.tartim'
    _description = 'Tartım'
    _order = 'id desc'

    name = fields.Char(string='No', required=True, copy=False, readonly=True, default='/')
    terazi_id = fields.Many2one('atlas.iot.cihaz', string='Terazi', domain=[('tur', '=', 'terazi')])
    yazici_id = fields.Many2one('atlas.iot.cihaz', string='Etiket Yazıcı', domain=[('tur', '=', 'yazici')])
    product_id = fields.Many2one('product.product', string='Ürün', required=True)
    agirlik = fields.Float(string='Ağırlık', digits='Product Unit', required=True)
    dara = fields.Float(string='Dara', digits='Product Unit')
    net = fields.Float(string='Net', compute='_compute_net', store=True, digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Birim')
    lot_id = fields.Many2one('stock.lot', string='Lot/Seri', domain="[('product_id', '=', product_id)]")
    picking_id = fields.Many2one('stock.picking', string='Transfer')
    etiket_adedi = fields.Integer(string='Etiket Adedi', default=1)
    yazdirildi = fields.Boolean(string='Etiket Basıldı', readonly=True)
    user_id = fields.Many2one('res.users', string='Tartan', default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('agirlik', 'dara')
    def _compute_net(self):
        for t in self:
            t.net = t.agirlik - t.dara

    @api.constrains('agirlik', 'dara')
    def _check_agirlik(self):
        for t in self:
            if t.agirlik <= 0 or t.dara < 0 or t.dara >= t.agirlik:
                raise ValidationError(self.env._('Ağırlık pozitif ve daradan büyük olmalı.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.iot.tartim') or '/'
        kayitlar = super().create(vals_list)
        for t in kayitlar.filtered('terazi_id'):
            t.terazi_id.sudo().write({'son_deger': t.agirlik, 'son_gorulme': fields.Datetime.now()})
        return kayitlar

    def action_etiket_bas(self):
        for t in self:
            yazici = t.yazici_id or self.env['atlas.iot.cihaz'].search([('tur', '=', 'yazici'), ('company_id', 'in', (t.company_id.id, False))], limit=1)
            if not yazici:
                raise UserError(self.env._('Tanımlı etiket yazıcısı yok.'))
            yazici._zpl_gonder(yazici._zpl_olustur(t.product_id, t.net, t.lot_id.name, t.etiket_adedi))
            t.write({'yazdirildi': True, 'yazici_id': yazici.id})
        return True


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_atlas_etiket_yazdir(self):
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.iot.etiket', 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Etiket Yazdır'), 'context': {'default_product_ids': self.ids}}


class AtlasIotEtiket(models.TransientModel):
    _name = 'atlas.iot.etiket'
    _description = 'Ürün Etiketi Yazdır'

    product_ids = fields.Many2many('product.product', string='Ürünler', required=True)
    yazici_id = fields.Many2one('atlas.iot.cihaz', string='Yazıcı', required=True, domain=[('tur', '=', 'yazici')],
                                default=lambda self: self.env['atlas.iot.cihaz'].search([('tur', '=', 'yazici')], limit=1))
    adet = fields.Integer(string='Her Üründen Adet', default=1, required=True)

    def action_yazdir(self):
        self.ensure_one()
        if self.adet < 1:
            raise UserError(self.env._('Adet en az 1 olmalı.'))
        zpl = ''.join(self.yazici_id._zpl_olustur(p, adet=self.adet) for p in self.product_ids)
        self.yazici_id._zpl_gonder(zpl)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('%s ürün etiketi yazıcıya gönderildi.', len(self.product_ids)),
                           'next': {'type': 'ir.actions.act_window_close'}}}
