from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


def vergi_hesapla(matrah, dilimler):
    """Kümülatif matrah için artan oranlı gelir vergisi. dilimler: [(üst sınır | None, oran %)] artan sırada."""
    vergi, alt = 0.0, 0.0
    for ust, oran in dilimler:
        if matrah <= alt:
            break
        dilim_ust = matrah if ust is None else min(matrah, ust)
        vergi += (dilim_ust - alt) * oran / 100.0
        if ust is None:
            break
        alt = ust
    return vergi


class AtlasBordroParametre(models.Model):
    _name = 'atlas.bordro.parametre'
    _description = 'Bordro Yıl Parametreleri'
    _order = 'yil desc, donem_bas desc'

    name = fields.Char(string='Ad', compute='_compute_name', store=True)
    yil = fields.Integer(string='Yıl', required=True)
    donem_bas = fields.Integer(string='Geçerli Olduğu İlk Ay', default=1, required=True,
                               help='Yıl içinde değişen değerler (ör. Temmuz\'da asgari ücret artışı) için 7 girin.')
    onaylandi = fields.Boolean(string='Değerler Kontrol Edildi', help='Kontrol edilmemiş parametrelerle bordro hesaplanmaz.')
    asgari_brut = fields.Float(string='Asgari Ücret (Brüt, Aylık)', digits=(16, 2), required=True)
    sgk_tavan_carpan = fields.Float(string='SGK Tavan Çarpanı', default=7.5, digits=(6, 2))
    sgk_isci = fields.Float(string='SGK İşçi Payı %', default=14.0, digits=(6, 3))
    issizlik_isci = fields.Float(string='İşsizlik İşçi Payı %', default=1.0, digits=(6, 3))
    sgk_isveren = fields.Float(string='SGK İşveren Payı %', default=20.75, digits=(6, 3))
    issizlik_isveren = fields.Float(string='İşsizlik İşveren Payı %', default=2.0, digits=(6, 3))
    tesvik_puan = fields.Float(string='Hazine Teşviki (Puan)', default=5.0, digits=(6, 3),
                               help='5510/81-ı prim teşviki; işveren payından düşülür.')
    sgdp_isci = fields.Float(string='SGDP İşçi %', default=7.5, digits=(6, 3))
    sgdp_isveren = fields.Float(string='SGDP İşveren %', default=24.75, digits=(6, 3))
    damga_binde = fields.Float(string='Damga Vergisi (Binde)', default=7.59, digits=(6, 3))
    yemek_istisna_gunluk = fields.Float(string='Yemek İstisnası (Günlük)', digits=(16, 2))
    engelli_1 = fields.Float(string='Engelli İndirimi 1. Derece', digits=(16, 2))
    engelli_2 = fields.Float(string='Engelli İndirimi 2. Derece', digits=(16, 2))
    engelli_3 = fields.Float(string='Engelli İndirimi 3. Derece', digits=(16, 2))
    kidem_tavan = fields.Float(string='Kıdem Tazminatı Tavanı', digits=(16, 2))
    dilim_ids = fields.One2many('atlas.bordro.vergi.dilim', 'parametre_id', string='Gelir Vergisi Dilimleri (Ücret)', copy=True)
    aciklama = fields.Text(string='Kaynak / Not')

    _yil_ay_uniq = models.Constraint('UNIQUE(yil, donem_bas)', 'Bu yıl ve ay için parametre zaten var.')

    @api.depends('yil', 'donem_bas')
    def _compute_name(self):
        for p in self:
            p.name = f'{p.yil}' + (f' / {p.donem_bas}. aydan itibaren' if p.donem_bas and p.donem_bas > 1 else '')

    @api.constrains('donem_bas')
    def _check_ay(self):
        for p in self:
            if not 1 <= p.donem_bas <= 12:
                raise ValidationError(self.env._('Ay 1-12 arasında olmalı.'))

    @api.model
    def _bul(self, yil, ay):
        p = self.search([('yil', '=', yil), ('donem_bas', '<=', ay)], order='donem_bas desc', limit=1)
        if not p:
            raise UserError(self.env._('%s yılı için bordro parametresi tanımlı değil (Bordro > Yapılandırma > Yıl Parametreleri).', yil))
        if not p.onaylandi:
            raise UserError(self.env._('%s bordro parametreleri henüz kontrol edilmedi. Resmî değerlerle karşılaştırıp '
                                       '"Değerler Kontrol Edildi" işaretleyin.', p.name))
        return p

    def _dilimler(self):
        self.ensure_one()
        satirlar = self.dilim_ids.sorted(lambda d: (d.ust_sinir == 0, d.ust_sinir))
        if not satirlar:
            raise UserError(self.env._('%s için gelir vergisi dilimi girilmemiş.', self.name))
        return [(d.ust_sinir or None, d.oran) for d in satirlar]

    def _vergi(self, kumulatif):
        return vergi_hesapla(kumulatif, self._dilimler())

    def _sgk_tavan(self):
        return self.asgari_brut * self.sgk_tavan_carpan

    def _asgari_gv_matrah(self):
        """Asgari ücretin aylık gelir vergisi matrahı (SGK işçi + işsizlik düşülmüş)."""
        return self.asgari_brut * (1 - (self.sgk_isci + self.issizlik_isci) / 100.0)

    def _engelli_indirimi(self, derece):
        return {1: self.engelli_1, 2: self.engelli_2, 3: self.engelli_3}.get(int(derece or 0), 0.0)

    @api.model
    def _atlas_kurulum(self):
        """İlk kurulumda: 2025 ikinci yarı ve 2026 taslağı, avans hesabı, ücretsiz izin türleri."""
        p25 = self.env.ref('atlas_bordro.parametre_2025', raise_if_not_found=False)
        if p25 and not self.search_count([('yil', '=', 2025), ('donem_bas', '=', 7)]):
            p25.copy({'donem_bas': 7, 'kidem_tavan': 53919.68,
                      'aciklama': self.env._('2025 ikinci yarı (kıdem tavanı değişti). Resmî değerlerle kontrol edin.')})
        if p25 and not self.search_count([('yil', '=', 2026)]):
            p25.copy({'yil': 2026, 'donem_bas': 1, 'onaylandi': False,
                      'aciklama': self.env._('TASLAK: 2025 değerlerinden kopyalandı. 2026 asgari ücret, vergi dilimleri, '
                                             'istisna ve tavanları resmî kaynaktan girip onaylayın.')})
        avans = self.env.ref('atlas_bordro.kalem_avans', raise_if_not_found=False)
        if avans and not avans.hesap_id:
            hesap = self.env['account.account'].search([('code', '=like', '196%')], order='code', limit=1)
            avans.hesap_id = hesap
        Tur = self.env['hr.work.entry.type'].sudo()
        for tur in Tur.search(['|', ('amount_rate', '=', 0), ('code', 'ilike', 'UNPAID')]):
            if tur.count_as == 'absence' or 'UNPAID' in (tur.code or '').upper():
                tur.write({'atlas_ucretsiz': True, 'atlas_eksik_gun_nedeni': tur.atlas_eksik_gun_nedeni or '21'})

    def action_kopyala_yeni_yil(self):
        self.ensure_one()
        yeni = self.copy({'yil': self.yil + 1, 'donem_bas': 1, 'onaylandi': False,
                          'aciklama': self.env._('%s değerlerinden kopyalandı — resmî değerlerle güncelleyin.', self.name)})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': yeni.id, 'view_mode': 'form'}


class AtlasBordroVergiDilim(models.Model):
    _name = 'atlas.bordro.vergi.dilim'
    _description = 'Gelir Vergisi Dilimi'
    _order = 'parametre_id, ust_sinir'

    parametre_id = fields.Many2one('atlas.bordro.parametre', required=True, ondelete='cascade')
    ust_sinir = fields.Float(string='Üst Sınır (Kümülatif Matrah)', digits=(16, 2), help='Son dilimde 0 bırakın (sınırsız).')
    oran = fields.Float(string='Oran %', digits=(6, 2), required=True)
