from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

BASARI_TIPLERI = [('satis_tutar', 'Satış tutarı'), ('fatura_tutar', 'Faturalanan tutar'),
                  ('satis_miktar', 'Satılan miktar'), ('fatura_miktar', 'Faturalanan miktar')]
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


class AtlasKomisyonPlan(models.Model):
    """Komisyon planı (Enterprise sale.commission.plan eşleniği)."""
    _name = 'atlas.komisyon.plan'
    _description = 'Komisyon Planı'
    _inherit = ['mail.thread']
    _order = 'bas desc, id desc'

    name = fields.Char(string='Plan Adı', required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Para Birimi')
    bas = fields.Date(string='Başlangıç', required=True, default=lambda self: fields.Date.today().replace(month=1, day=1))
    bit = fields.Date(string='Bitiş', required=True, default=lambda self: fields.Date.today().replace(month=12, day=31))
    periyot = fields.Selection([('ay', 'Aylık'), ('ceyrek', 'Çeyreklik'), ('yil', 'Yıllık')], string='Dönem', default='ay', required=True)
    tur = fields.Selection([('basari', 'Başarı bazlı'), ('hedef', 'Hedef bazlı')], string='Plan Türü', default='basari', required=True,
                           help='Başarı bazlı: her satış/fatura satırından oranla komisyon.\n'
                                'Hedef bazlı: dönem hedefine göre gerçekleşme oranı, kademelerle komisyon tutarı.')
    kullanici_tipi = fields.Selection([('kisi', 'Satış temsilcisi'), ('ekip', 'Satış ekibi')], string='Kime', default='kisi', required=True)
    durum = fields.Selection([('taslak', 'Taslak'), ('onayli', 'Onaylı'), ('kapali', 'Kapalı'), ('iptal', 'İptal')], string='Durum',
                             default='taslak', required=True, tracking=True, copy=False)
    hedef_komisyon = fields.Monetary(string='Hedefte Komisyon', currency_field='currency_id',
                                     help='Hedefin %100 gerçekleşmesinde ödenecek komisyon (kademe yoksa doğrusal)')
    basari_ids = fields.One2many('atlas.komisyon.plan.basari', 'plan_id', string='Başarı Kuralları', copy=True)
    hedef_ids = fields.One2many('atlas.komisyon.plan.hedef', 'plan_id', string='Hedefler', copy=True)
    kademe_ids = fields.One2many('atlas.komisyon.plan.kademe', 'plan_id', string='Kademeler', copy=True)
    uye_ids = fields.One2many('atlas.komisyon.plan.uye', 'plan_id', string='Temsilciler / Ekipler', copy=True)
    sonuc_ids = fields.One2many('atlas.komisyon.sonuc', 'plan_id', string='Sonuçlar')
    toplam_komisyon = fields.Monetary(string='Toplam Komisyon', compute='_compute_toplam', currency_field='currency_id')
    son_hesap = fields.Datetime(string='Son Hesaplama', readonly=True, copy=False)

    @api.constrains('bas', 'bit')
    def _check_tarih(self):
        for p in self:
            if p.bas > p.bit:
                raise ValidationError(self.env._('Plan başlangıcı bitişten sonra olamaz.'))

    @api.depends('sonuc_ids.komisyon')
    def _compute_toplam(self):
        for p in self:
            p.toplam_komisyon = sum(p.sonuc_ids.mapped('komisyon'))

    # ------------------------------------------------------------------ dönemler
    def _donemler(self):
        """[(başlangıç, bitiş, ad)] — plan aralığını dönemlere böler (takvim ayı/çeyreği/yılı ile hizalı)."""
        self.ensure_one()
        adim = {'ay': 1, 'ceyrek': 3, 'yil': 12}[self.periyot]
        bas = self.bas.replace(day=1)
        if self.periyot == 'ceyrek':
            bas = bas.replace(month=(bas.month - 1) // 3 * 3 + 1)
        elif self.periyot == 'yil':
            bas = bas.replace(month=1)
        sonuc = []
        while bas <= self.bit:
            bit = bas + relativedelta(months=adim, days=-1)
            if self.periyot == 'ay':
                ad = f'{AYLAR[bas.month - 1]} {bas.year}'
            elif self.periyot == 'ceyrek':
                ad = f'{bas.year} Ç{(bas.month - 1) // 3 + 1}'
            else:
                ad = str(bas.year)
            sonuc.append((max(bas, self.bas), min(bit, self.bit), ad))
            bas += relativedelta(months=adim)
        return sonuc

    def action_hedefleri_olustur(self):
        for p in self:
            mevcut = {(h.bas, h.bit) for h in p.hedef_ids}
            p.hedef_ids = [Command.create({'bas': b, 'bit': e, 'name': ad, 'tutar': 0.0}) for b, e, ad in p._donemler() if (b, e) not in mevcut]
        return True

    def action_kademe_varsayilan(self):
        for p in self:
            tutar = p.hedef_komisyon or 0.0
            p.kademe_ids = [Command.clear()] + [Command.create({'oran': o, 'tutar': tutar * k}) for o, k in ((0.5, 0.0), (1.0, 1.0), (1.5, 1.8))]
        return True

    # ------------------------------------------------------------------ durum
    def action_onayla(self):
        for p in self:
            if not p.uye_ids:
                raise UserError(self.env._('Plana en az bir temsilci ya da ekip ekleyin.'))
            if not p.basari_ids:
                raise UserError(self.env._('Plana en az bir başarı kuralı ekleyin (neyin sayılacağı).'))
            if p.tur == 'hedef':
                if not p.hedef_ids:
                    p.action_hedefleri_olustur()
                if not p.kademe_ids and not p.hedef_komisyon:
                    raise UserError(self.env._('Hedef bazlı planda kademe ya da hedefte komisyon tutarı girin.'))
            p.durum = 'onayli'
        self._hesapla()
        return True

    def action_taslak(self):
        self.write({'durum': 'taslak'})
        self.sonuc_ids.unlink()
        return True

    def action_kapat(self):
        self._hesapla()
        self.write({'durum': 'kapali'})
        return True

    def action_iptal(self):
        self.write({'durum': 'iptal'})
        self.sonuc_ids.unlink()
        return True

    def action_hesapla(self):
        self._hesapla()
        return self.action_sonuclar()

    def action_sonuclar(self):
        eylem = self.env['ir.actions.act_window']._for_xml_id('atlas_komisyon.action_atlas_komisyon_sonuc')
        eylem['domain'] = [('plan_id', 'in', self.ids)]
        eylem['context'] = {'search_default_g_kisi': 1}
        return eylem

    @api.model
    def _cron_hesapla(self):
        self.search([('durum', '=', 'onayli')])._hesapla()

    # ------------------------------------------------------------------ hesaplama
    def _hesapla(self):
        Sonuc = self.env['atlas.komisyon.sonuc'].sudo()
        for p in self.filtered(lambda p: p.durum in ('onayli', 'kapali')):
            p.sudo().sonuc_ids.unlink()
            hedefler = {(h.bas, h.bit): h.tutar for h in p.hedef_ids}
            for d_bas, d_bit, d_ad in p._donemler():
                for uye in p.uye_ids:
                    bas, bit = max(d_bas, uye.bas or d_bas), min(d_bit, uye.bit or d_bit)
                    if bas > bit:
                        continue
                    satirlar = p._kaynak_satirlari(uye, bas, bit)
                    basari = sum(s['katki'] for s in satirlar)
                    hedef = hedefler.get((d_bas, d_bit), 0.0) if p.tur == 'hedef' else 0.0
                    gerceklesme = basari / hedef if hedef else 0.0
                    komisyon = basari if p.tur == 'basari' else p._kademe_komisyon(gerceklesme)
                    Sonuc.create({
                        'plan_id': p.id, 'user_id': uye.user_id.id, 'team_id': uye.team_id.id, 'donem_bas': d_bas, 'donem_bit': d_bit,
                        'donem_adi': d_ad, 'basari': basari, 'hedef': hedef, 'gerceklesme': gerceklesme * 100, 'komisyon': komisyon,
                        'satir_ids': [Command.create(s) for s in satirlar],
                    })
            p.sudo().son_hesap = fields.Datetime.now()

    def _kademe_komisyon(self, oran):
        """Gerçekleşme oranına göre kademeler arasında doğrusal komisyon; ilk kademenin altı 0, son kademenin üstü sabit."""
        self.ensure_one()
        kademeler = sorted(((k.oran, k.tutar) for k in self.kademe_ids), key=lambda x: x[0])
        if not kademeler:
            kademeler = [(0.0, 0.0), (1.0, self.hedef_komisyon)]
        if oran < kademeler[0][0]:
            return 0.0
        for (o1, t1), (o2, t2) in zip(kademeler, kademeler[1:]):
            if o1 <= oran <= o2:
                return t1 + (t2 - t1) * (oran - o1) / (o2 - o1) if o2 > o1 else t2
        return kademeler[-1][1]

    def _kural_uyar(self, kural, urun):
        if kural.urun_id and kural.urun_id != urun:
            return False
        if kural.kategori_id and not (urun.categ_id and urun.categ_id.parent_path and
                                      urun.categ_id.parent_path.startswith(kural.kategori_id.parent_path)):
            return False
        return True

    def _kaynak_satirlari(self, uye, bas, bit):
        """Bir üyenin dönemdeki başarı satırları (rapor ayrıntısı): satış, fatura ve düzeltme."""
        self.ensure_one()
        sirket = self.company_id
        para = sirket.currency_id
        satirlar = []
        kurallar = self.basari_ids
        satis_kurallari = kurallar.filtered(lambda k: k.tip in ('satis_tutar', 'satis_miktar'))
        fatura_kurallari = kurallar.filtered(lambda k: k.tip in ('fatura_tutar', 'fatura_miktar'))
        sahip = ('user_id', '=', uye.user_id.id) if self.kullanici_tipi == 'kisi' else ('team_id', '=', uye.team_id.id)
        if satis_kurallari:
            SOL = self.env['sale.order.line'].sudo()
            alan = [('order_id.state', '=', 'sale'), ('order_id.company_id', '=', sirket.id), ('display_type', '=', False),
                    ('order_id.' + sahip[0], sahip[1], sahip[2]),
                    ('order_id.date_order', '>=', fields.Datetime.to_datetime(bas)),
                    ('order_id.date_order', '<', fields.Datetime.to_datetime(bit) + relativedelta(days=1))]
            for s in SOL.search(alan):
                siparis = s.order_id
                tutar = siparis.currency_id._convert(s.price_subtotal, para, sirket, siparis.date_order.date())
                for k in satis_kurallari:
                    if not self._kural_uyar(k, s.product_id):
                        continue
                    taban = tutar if k.tip == 'satis_tutar' else s.product_uom_qty
                    katki = taban * (k.oran / 100.0 if k.tip == 'satis_tutar' else k.oran)
                    satirlar.append({'kaynak': 'satis', 'belge': siparis.name, 'res_model': 'sale.order', 'res_id': siparis.id,
                                     'tarih': siparis.date_order.date(), 'urun_id': s.product_id.id, 'miktar': s.product_uom_qty,
                                     'tutar': tutar, 'kural_id': k.id, 'oran': k.oran, 'katki': katki})
        if fatura_kurallari:
            AML = self.env['account.move.line'].sudo()
            sahip_alan = 'invoice_user_id' if self.kullanici_tipi == 'kisi' else 'team_id'
            # temsilcisi boş bırakılmış iadeler, iade edilen faturanın temsilcisine sayılır
            alan = [('move_id.state', '=', 'posted'), ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
                    ('move_id.company_id', '=', sirket.id), ('display_type', '=', 'product'),
                    '|', ('move_id.' + sahip_alan, '=', sahip[2]),
                    '&', ('move_id.' + sahip_alan, '=', False), ('move_id.reversed_entry_id.' + sahip_alan, '=', sahip[2]),
                    ('move_id.invoice_date', '>=', bas), ('move_id.invoice_date', '<=', bit)]
            for s in AML.search(alan):
                fatura = s.move_id
                isaret = -1 if fatura.move_type == 'out_refund' else 1
                tutar = -s.balance
                miktar = s.quantity * isaret
                for k in fatura_kurallari:
                    if not self._kural_uyar(k, s.product_id):
                        continue
                    taban = tutar if k.tip == 'fatura_tutar' else miktar
                    katki = taban * (k.oran / 100.0 if k.tip == 'fatura_tutar' else k.oran)
                    satirlar.append({'kaynak': 'fatura', 'belge': fatura.name, 'res_model': 'account.move', 'res_id': fatura.id,
                                     'tarih': fatura.invoice_date, 'urun_id': s.product_id.id, 'miktar': miktar, 'tutar': tutar,
                                     'kural_id': k.id, 'oran': k.oran, 'katki': katki})
        duzeltmeler = self.env['atlas.komisyon.duzeltme'].sudo().search([
            ('plan_id', '=', self.id), ('tarih', '>=', bas), ('tarih', '<=', bit),
            ('user_id', '=', uye.user_id.id) if self.kullanici_tipi == 'kisi' else ('team_id', '=', uye.team_id.id)])
        for d in duzeltmeler:
            satirlar.append({'kaynak': 'duzeltme', 'belge': d.name, 'res_model': 'atlas.komisyon.duzeltme', 'res_id': d.id,
                             'tarih': d.tarih, 'tutar': d.tutar, 'oran': 100.0, 'katki': d.tutar})
        return satirlar


class AtlasKomisyonPlanBasari(models.Model):
    _name = 'atlas.komisyon.plan.basari'
    _description = 'Komisyon Başarı Kuralı'

    plan_id = fields.Many2one('atlas.komisyon.plan', string='Plan', required=True, ondelete='cascade', index=True)
    tip = fields.Selection(BASARI_TIPLERI, string='Neye Göre', required=True, default='satis_tutar')
    urun_id = fields.Many2one('product.product', string='Ürün')
    kategori_id = fields.Many2one('product.category', string='Ürün Kategorisi')
    oran = fields.Float(string='Oran', default=5.0, digits=(16, 4),
                        help='Tutar bazlı kurallarda yüzde (%), miktar bazlı kurallarda birim başına tutar')


class AtlasKomisyonPlanHedef(models.Model):
    _name = 'atlas.komisyon.plan.hedef'
    _description = 'Komisyon Dönem Hedefi'
    _order = 'bas'

    plan_id = fields.Many2one('atlas.komisyon.plan', string='Plan', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Dönem')
    bas = fields.Date(string='Başlangıç', required=True)
    bit = fields.Date(string='Bitiş', required=True)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    tutar = fields.Monetary(string='Hedef', currency_field='currency_id')


class AtlasKomisyonPlanKademe(models.Model):
    _name = 'atlas.komisyon.plan.kademe'
    _description = 'Komisyon Kademesi'
    _order = 'oran'

    plan_id = fields.Many2one('atlas.komisyon.plan', string='Plan', required=True, ondelete='cascade', index=True)
    oran = fields.Float(string='Gerçekleşme', required=True, help='Hedefin oranı: 1,0 = %100')
    currency_id = fields.Many2one(related='plan_id.currency_id')
    tutar = fields.Monetary(string='Komisyon', currency_field='currency_id')


class AtlasKomisyonPlanUye(models.Model):
    _name = 'atlas.komisyon.plan.uye'
    _description = 'Komisyon Planı Üyesi'

    plan_id = fields.Many2one('atlas.komisyon.plan', string='Plan', required=True, ondelete='cascade', index=True)
    kullanici_tipi = fields.Selection(related='plan_id.kullanici_tipi')
    user_id = fields.Many2one('res.users', string='Satış Temsilcisi', domain=[('share', '=', False)])
    team_id = fields.Many2one('crm.team', string='Satış Ekibi')
    bas = fields.Date(string='Başlangıç', help='Boşsa plan başlangıcı')
    bit = fields.Date(string='Bitiş', help='Boşsa plan bitişi')

    @api.constrains('user_id', 'team_id', 'plan_id')
    def _check_uye(self):
        for u in self:
            if u.plan_id.kullanici_tipi == 'kisi' and not u.user_id:
                raise ValidationError(self.env._('Satış temsilcisi seçin.'))
            if u.plan_id.kullanici_tipi == 'ekip' and not u.team_id:
                raise ValidationError(self.env._('Satış ekibi seçin.'))


class AtlasKomisyonDuzeltme(models.Model):
    """Elle başarı düzeltmesi (prim, kesinti, önceki dönem farkı)."""
    _name = 'atlas.komisyon.duzeltme'
    _description = 'Komisyon Düzeltmesi'
    _inherit = ['mail.thread']
    _order = 'tarih desc, id desc'

    name = fields.Char(string='Açıklama', required=True)
    plan_id = fields.Many2one('atlas.komisyon.plan', string='Plan', required=True, domain=[('durum', 'in', ('taslak', 'onayli'))])
    kullanici_tipi = fields.Selection(related='plan_id.kullanici_tipi')
    user_id = fields.Many2one('res.users', string='Satış Temsilcisi')
    team_id = fields.Many2one('crm.team', string='Satış Ekibi')
    tarih = fields.Date(string='Tarih', required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    tutar = fields.Monetary(string='Tutar', currency_field='currency_id', required=True, tracking=True,
                            help='Başarıya eklenir (eksi değer düşer)')
