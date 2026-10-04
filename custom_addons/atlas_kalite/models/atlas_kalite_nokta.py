import random
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

ASAMALAR = [
    ('giris', 'Giriş Kontrolü (Mal Kabul)'),
    ('ara', 'Üretim Ara Kontrolü (İş Emri)'),
    ('final', 'Final Kontrolü (Üretim Emri)'),
    ('sevkiyat', 'Sevkiyat Öncesi Kontrol'),
]
TEST_TIPLERI = [
    ('talimat', 'Talimat'),
    ('gecti_kaldi', 'Geçti / Kaldı'),
    ('olcum', 'Ölçüm'),
    ('kontrol_listesi', 'Kontrol Listesi'),
    ('foto', 'Fotoğraf'),
    ('sayim', 'Numune Sayımı'),
]
OLCUM_YERLERI = [
    ('islem', 'Belge başına bir kez'),
    ('urun', 'Her ürün için'),
    ('lot', 'Her lot / seri için'),
]
SIKLIKLAR = [
    ('tumu', 'Her seferinde'),
    ('rastgele', 'Rastgele (%)'),
    ('periyodik', 'Periyodik'),
    ('istege_bagli', 'İsteğe bağlı (elle)'),
]


class AtlasKaliteNokta(models.Model):
    """Kontrol noktası: hangi belgede, hangi ürün için, ne sıklıkla, hangi testin yapılacağı."""
    _name = 'atlas.kalite.nokta'
    _description = 'Kalite Kontrol Noktası'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(string='Kontrol Noktası', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    asama = fields.Selection(ASAMALAR, string='Kontrol Aşaması', required=True, default='giris', tracking=True)

    # Uygulama kapsamı (boş = tümü)
    product_ids = fields.Many2many('product.product', string='Ürünler')
    category_ids = fields.Many2many('product.category', string='Ürün Kategorileri')
    picking_type_ids = fields.Many2many('stock.picking.type', string='Operasyon Türleri',
                                        help='Boşsa aşamaya uyan tüm operasyon türlerinde uygulanır.')
    operation_ids = fields.Many2many('mrp.routing.workcenter', string='Rota Operasyonları',
                                     help='Ara kontrolde yalnızca bu operasyonlara ait iş emirleri. Boşsa tümü.')
    workcenter_ids = fields.Many2many('mrp.workcenter', string='İş Merkezleri',
                                      help='Ara kontrolde yalnızca bu iş merkezlerindeki iş emirleri. Boşsa tümü.')
    partner_ids = fields.Many2many('res.partner', string='Cariler',
                                   help='Giriş/sevkiyat kontrolünü yalnızca bu tedarikçi/müşterilerin belgelerinde uygula.')

    # Test
    test_tipi = fields.Selection(TEST_TIPLERI, string='Test Tipi', required=True, default='gecti_kaldi', tracking=True)
    olcum_yeri = fields.Selection(OLCUM_YERLERI, string='Kontrol Yeri', required=True, default='urun')
    talimat = fields.Html(string='Talimat')
    dokuman = fields.Binary(string='Doküman', attachment=True)
    dokuman_adi = fields.Char(string='Doküman Adı')
    basarisiz_mesaj = fields.Html(string='Başarısızlıkta Yapılacaklar')
    # Ölçüm
    norm = fields.Float(string='Nominal Değer', digits=(16, 4))
    alt_sinir = fields.Float(string='Alt Sınır', digits=(16, 4))
    ust_sinir = fields.Float(string='Üst Sınır', digits=(16, 4))
    olcu_birimi = fields.Char(string='Ölçü Birimi', help='ör. mm, kg, °C')
    # Kontrol listesi
    madde_ids = fields.One2many('atlas.kalite.nokta.madde', 'nokta_id', string='Kontrol Maddeleri', copy=True)
    # Numune sayımı
    numune_miktar = fields.Float(string='Numune Miktarı', default=1.0)
    kabul_orani = fields.Float(string='Kabul Edilebilir Hata (%)', default=0.0,
                               help='Hatalı / test edilen oranı bu değeri aşarsa kontrol başarısız olur.')

    # Sıklık
    siklik = fields.Selection(SIKLIKLAR, string='Sıklık', required=True, default='tumu')
    yuzde = fields.Float(string='Kontrol Oranı (%)', default=10.0)
    periyot_sayi = fields.Integer(string='Her', default=1)
    periyot_birim = fields.Selection([('gun', 'Gün'), ('hafta', 'Hafta'), ('ay', 'Ay')], string='Periyot', default='hafta')

    # Sorumluluk ve davranış
    ekip_id = fields.Many2one('atlas.kalite.ekip', string='Kalite Ekibi')
    user_id = fields.Many2one('res.users', string='Sorumlu')
    engelleyici = fields.Boolean(string='Bekleyen Kontrol Engeller', default=True,
                                 help='Kontrol yapılmadan belge doğrulanamaz / iş emri bitirilemez.')
    kaldi_engeller = fields.Boolean(string='Başarısızlıkta Durdur',
                                    help='Kontrol başarısızsa belge doğrulanamaz (karantina, iade vb. karar verilene kadar).')
    otomatik_uyari = fields.Boolean(string='Başarısızlıkta Uygunsuzluk Aç', default=True)
    kontrol_ids = fields.One2many('atlas.kalite.kontrol', 'nokta_id', string='Kontroller')
    kontrol_sayisi = fields.Integer(compute='_compute_kontrol_sayisi', string='Kontrol Sayısı')
    basari_orani = fields.Float(compute='_compute_kontrol_sayisi', string='Başarı Oranı (%)')

    _olcum_sinir = models.Constraint('CHECK(alt_sinir <= ust_sinir)', 'Alt sınır üst sınırdan büyük olamaz.')

    def _compute_kontrol_sayisi(self):
        data = self.env['atlas.kalite.kontrol']._read_group(
            [('nokta_id', 'in', self.ids), ('durum', '!=', 'bekliyor')], ['nokta_id', 'durum'], ['__count'])
        sayac = {}
        for nokta, durum, count in data:
            sayac.setdefault(nokta.id, {})[durum] = count
        for nokta in self:
            s = sayac.get(nokta.id, {})
            toplam = sum(s.values())
            nokta.kontrol_sayisi = toplam
            nokta.basari_orani = 100.0 * s.get('gecti', 0) / toplam if toplam else 0.0

    @api.onchange('norm')
    def _onchange_norm(self):
        if self.test_tipi == 'olcum' and not self.alt_sinir and not self.ust_sinir:
            self.alt_sinir = self.ust_sinir = self.norm

    # -------------------------------------------------------------------------
    # Eşleştirme
    # -------------------------------------------------------------------------

    @api.model
    def _noktalar(self, asama, company, **filtre):
        """Aşama ve belgeye uyan otomatik kontrol noktaları."""
        noktalar = self.search([('asama', '=', asama), ('siklik', '!=', 'istege_bagli'),
                                ('company_id', 'in', (False, company.id))])
        picking_type = filtre.get('picking_type')
        if picking_type:
            noktalar = noktalar.filtered(lambda n: not n.picking_type_ids or picking_type in n.picking_type_ids)
        partner = filtre.get('partner')
        if 'partner' in filtre:
            commercial = partner.commercial_partner_id if partner else partner
            noktalar = noktalar.filtered(lambda n: not n.partner_ids or (commercial and commercial in n.partner_ids.commercial_partner_id))
        workorder = filtre.get('workorder')
        if workorder:
            noktalar = noktalar.filtered(
                lambda n: (not n.operation_ids or workorder.operation_id in n.operation_ids)
                and (not n.workcenter_ids or workorder.workcenter_id in n.workcenter_ids))
        return noktalar

    def _urun_uygun(self, product):
        self.ensure_one()
        if not self.product_ids and not self.category_ids:
            return True
        if product in self.product_ids:
            return True
        path = product.categ_id.parent_path or ''
        return any(path.startswith(c.parent_path) for c in self.category_ids)

    def _secildi(self, anahtar):
        """Sıklık kuralı: bu (belge, ürün, lot) için kontrol yapılacak mı?

        Rastgele seçim anahtara göre sabittir; aynı belge tekrar işlendiğinde karar değişmez."""
        self.ensure_one()
        if self.siklik == 'tumu':
            return True
        if self.siklik == 'rastgele':
            return random.Random(f'{self.id}:{anahtar}').random() * 100.0 < self.yuzde
        if self.siklik == 'periyodik':
            sayi = max(self.periyot_sayi, 1)
            delta = {'gun': timedelta(days=sayi), 'hafta': timedelta(weeks=sayi), 'ay': relativedelta(months=sayi)}[self.periyot_birim or 'hafta']
            return not self.env['atlas.kalite.kontrol'].search_count(
                [('nokta_id', '=', self.id), ('create_date', '>=', fields.Datetime.now() - delta)], limit=1)
        return False

    def action_kontroller(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kalite.action_atlas_kalite_kontrol')
        action['domain'] = [('nokta_id', '=', self.id)]
        action['context'] = {'default_nokta_id': self.id}
        return action


class AtlasKaliteNoktaMadde(models.Model):
    _name = 'atlas.kalite.nokta.madde'
    _description = 'Kontrol Listesi Maddesi'
    _order = 'sequence, id'

    nokta_id = fields.Many2one('atlas.kalite.nokta', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Madde', required=True)
