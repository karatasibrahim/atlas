from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .tools import account_by_code, create_entry


class AtlasSabitKiymet(models.Model):
    """Sabit kıymet (maddi / maddi olmayan duran varlık) ve VUK amortisman planı.

    - Normal: her yıl bedel / faydalı ömür
    - Azalan bakiyeler: net değer x (2 / ömür, en fazla %50); son yıl kalan net değerin tamamı
    - Kıst (binek otomobil): ilk yıl edinme ayından yıl sonuna kadar olan aylar oranında; kalan kısım ömrün
      bitiminden sonraki yıla eklenir
    - Kayıt yıllık ya da aylık (yıllık tutar, yılın kalan aylarına eşit dağıtılır) yapılabilir.
    """
    _name = 'atlas.sabit.kiymet'
    _description = 'Sabit Kıymet'
    _inherit = ['mail.thread']
    _order = 'edinme_tarihi desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Sabit Kıymet', required=True, tracking=True)
    kod = fields.Char(string='Sicil No', readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([('draft', 'Taslak'), ('active', 'Aktif'), ('closed', 'Satıldı / Hurda')],
                             default='draft', required=True, readonly=True, tracking=True)

    account_id = fields.Many2one('account.account', string='Varlık Hesabı', required=True, check_company=True,
                                 help='ör. 253 Tesis Makine, 254 Taşıtlar, 255 Demirbaşlar, 260 Haklar')
    birikmis_account_id = fields.Many2one('account.account', string='Birikmiş Amortisman Hesabı', required=True, check_company=True,
                                          help='Maddi: 257, maddi olmayan: 268')
    gider_account_id = fields.Many2one('account.account', string='Amortisman Gider Hesabı', required=True, check_company=True,
                                       help='ör. 770 Genel Yönetim, 730 Genel Üretim, 760 Pazarlama')
    analytic_distribution = fields.Json(string='Analitik Dağılım')

    edinme_tarihi = fields.Date(string='Edinme Tarihi', required=True, tracking=True)
    bedel = fields.Monetary(string='Maliyet Bedeli', required=True, tracking=True)
    faydali_omur = fields.Integer(string='Faydalı Ömür (Yıl)', required=True, default=5, tracking=True)
    yontem = fields.Selection([('normal', 'Normal'), ('azalan', 'Azalan Bakiyeler')], string='Yöntem',
                              required=True, default='normal', tracking=True)
    kist = fields.Boolean(string='Kıst Amortisman', help='Binek otomobillerde zorunlu: ilk yıl ay oranında ayrılır.')
    periyot = fields.Selection([('aylik', 'Aylık'), ('yillik', 'Yıllık')], string='Kayıt Periyodu', required=True, default='yillik')
    partner_id = fields.Many2one('res.partner', string='Satıcı')
    move_line_id = fields.Many2one('account.move.line', string='Alış Faturası Satırı', check_company=True)
    aciklama = fields.Text(string='Açıklama')

    line_ids = fields.One2many('atlas.amortisman.line', 'kiymet_id', string='Amortisman Planı', readonly=True)
    birikmis = fields.Monetary(string='Birikmiş Amortisman', compute='_compute_degerler')
    net_deger = fields.Monetary(string='Net Defter Değeri', compute='_compute_degerler')
    oran = fields.Float(string='Oran (%)', compute='_compute_degerler', digits=(5, 2))

    satis_tarihi = fields.Date(string='Satış / Hurda Tarihi', readonly=True)
    satis_move_id = fields.Many2one('account.move', string='Çıkış Fişi', readonly=True)

    @api.depends('line_ids.kaydedilen', 'bedel', 'faydali_omur', 'yontem')
    def _compute_degerler(self):
        for kiymet in self:
            kiymet.birikmis = sum(kiymet.line_ids.mapped('kaydedilen'))
            kiymet.net_deger = kiymet.bedel - kiymet.birikmis
            omur = kiymet.faydali_omur or 1
            kiymet.oran = 100.0 * (min(2.0 / omur, 0.5) if kiymet.yontem == 'azalan' else 1.0 / omur)

    @api.constrains('bedel', 'faydali_omur')
    def _check_values(self):
        for kiymet in self:
            if kiymet.bedel <= 0 or kiymet.faydali_omur < 1:
                raise UserError(self.env._('Bedel sıfırdan büyük, faydalı ömür en az 1 yıl olmalıdır.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('kod', '/') == '/':
                vals['kod'] = self.env['ir.sequence'].next_by_code('atlas.sabit.kiymet') or '/'
        return super().create(vals_list)

    @api.onchange('company_id')
    def _onchange_default_accounts(self):
        for field_name, code in (('birikmis_account_id', '257'), ('gider_account_id', '770')):
            if not self[field_name]:
                try:
                    self[field_name] = account_by_code(self.env, self.company_id or self.env.company, code)
                except UserError:
                    pass

    # -------------------------------------------------------------------------
    # Plan
    # -------------------------------------------------------------------------

    def _plan(self):
        """[(yıl, tutar, başlangıç ayı)] VUK amortisman planı."""
        self.ensure_one()
        currency = self.currency_id
        omur, bedel = self.faydali_omur, self.bedel
        first_year, month = self.edinme_tarihi.year, self.edinme_tarihi.month
        kist_orani = (13 - month) / 12.0 if self.kist else 1.0
        plan, kalan = [], bedel
        for index in range(omur):
            year = first_year + index
            if index == omur - 1 and not self.kist:
                amount = kalan
            elif self.yontem == 'azalan':
                amount = kalan * min(2.0 / omur, 0.5)
            else:
                amount = bedel / omur
            if index == 0:
                amount *= kist_orani
            amount = currency.round(min(amount, kalan))
            plan.append((year, amount, month if index == 0 else 1))
            kalan -= amount
        if not currency.is_zero(kalan):
            if self.kist:
                plan.append((first_year + omur, currency.round(kalan), 1))
            else:
                year, amount, start = plan[-1]
                plan[-1] = (year, currency.round(amount + kalan), start)
        return plan

    def action_plan_olustur(self):
        for kiymet in self:
            if kiymet.line_ids.filtered('kaydedilen'):
                raise UserError(self.env._('%s için amortisman kaydı yapılmış; plan yeniden oluşturulamaz.', kiymet.display_name))
            birikmis = 0.0
            lines = []
            for year, amount, start_month in kiymet._plan():
                birikmis += amount
                lines.append(Command.create({'yil': year, 'tutar': amount, 'baslangic_ayi': start_month,
                                             'birikmis_plan': birikmis, 'net_plan': kiymet.bedel - birikmis}))
            kiymet.line_ids = [Command.clear()] + lines
        return True

    def action_aktif(self):
        for kiymet in self.filtered(lambda k: k.state == 'draft'):
            if not kiymet.line_ids:
                kiymet.action_plan_olustur()
            kiymet.state = 'active'
        return True

    def action_taslak(self):
        for kiymet in self.filtered(lambda k: k.state == 'active'):
            if kiymet.line_ids.filtered('kaydedilen'):
                raise UserError(self.env._('Amortisman kaydı yapılmış kıymet taslağa alınamaz.'))
            kiymet.state = 'draft'
        return True

    # -------------------------------------------------------------------------
    # Amortisman kaydı
    # -------------------------------------------------------------------------

    def _amortisman_tutari(self, date):
        """Verilen ay sonuna kadar ayrılması gereken ile kaydedilen arasındaki fark."""
        self.ensure_one()
        line = self.line_ids.filtered(lambda l: l.yil == date.year)
        if not line or self.state != 'active' or (self.satis_tarihi and self.satis_tarihi.year <= date.year):
            return line, 0.0
        if self.periyot == 'yillik':
            if date.month != 12:
                return line, 0.0
            hedef = line.tutar
        else:
            aylar = 12 - line.baslangic_ayi + 1
            gecen = max(0, min(aylar, date.month - line.baslangic_ayi + 1))
            hedef = self.currency_id.round(line.tutar * gecen / aylar) if gecen < aylar else line.tutar
        return line, self.currency_id.round(hedef - line.kaydedilen)

    # -------------------------------------------------------------------------
    # Satış / hurda
    # -------------------------------------------------------------------------

    def action_satis(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Satış / Hurdaya Çıkış'),
            'res_model': 'atlas.sabit.kiymet.satis.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_kiymet_id': self.id},
        }


class AtlasAmortismanLine(models.Model):
    _name = 'atlas.amortisman.line'
    _description = 'Amortisman Planı Satırı'
    _order = 'kiymet_id, yil'

    kiymet_id = fields.Many2one('atlas.sabit.kiymet', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='kiymet_id.currency_id')
    yil = fields.Integer(string='Yıl', required=True)
    baslangic_ayi = fields.Integer(string='Başlangıç Ayı', default=1)
    tutar = fields.Monetary(string='Yıllık Amortisman')
    birikmis_plan = fields.Monetary(string='Birikmiş (Plan)')
    net_plan = fields.Monetary(string='Net Değer (Plan)')
    aml_ids = fields.One2many('account.move.line', 'atlas_amortisman_line_id', string='Gider Satırları', readonly=True)
    kaydedilen = fields.Monetary(string='Kaydedilen', compute='_compute_kaydedilen', store=True,
                                 help='Onaylı amortisman fişlerindeki tutar; fiş iptal edilirse düşer.')
    move_ids = fields.Many2many('account.move', string='Fişler', compute='_compute_move_ids')
    durum = fields.Selection([('plan', 'Planlandı'), ('kismi', 'Kısmen Kaydedildi'), ('tamam', 'Kaydedildi')],
                             compute='_compute_durum')

    @api.depends('aml_ids.parent_state', 'aml_ids.balance')
    def _compute_kaydedilen(self):
        for line in self:
            posted = line.aml_ids.filtered(lambda l: l.parent_state == 'posted')
            line.kaydedilen = sum(posted.mapped('balance'))

    @api.depends('aml_ids.parent_state')
    def _compute_move_ids(self):
        for line in self:
            line.move_ids = line.aml_ids.filtered(lambda l: l.parent_state == 'posted').move_id

    @api.depends('kaydedilen', 'tutar')
    def _compute_durum(self):
        for line in self:
            if line.currency_id.is_zero(line.kaydedilen):
                line.durum = 'plan'
            elif line.currency_id.compare_amounts(line.kaydedilen, line.tutar) >= 0:
                line.durum = 'tamam'
            else:
                line.durum = 'kismi'


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    atlas_amortisman_line_id = fields.Many2one('atlas.amortisman.line', string='Amortisman Planı', index='btree_not_null',
                                               readonly=True, copy=False, ondelete='restrict')


class AtlasSabitKiymetSatisWizard(models.TransientModel):
    """Sabit kıymet satışı / hurdaya çıkarılması.

    Borç: birikmiş amortisman + satış bedeli (cari veya kasa/banka hesabı), alacak: varlık bedeli;
    fark 679 (satış kârı) veya 689 (satış zararı). KDV'li satış faturası ayrıca kesilir ve karşı hesap olarak
    ilgili cari seçilir. VUK: satış yılında amortisman ayrılmaz.
    """
    _name = 'atlas.sabit.kiymet.satis.wizard'
    _description = 'Sabit Kıymet Satış / Hurda'

    kiymet_id = fields.Many2one('atlas.sabit.kiymet', required=True)
    currency_id = fields.Many2one(related='kiymet_id.currency_id')
    date = fields.Date(string='Tarih', required=True, default=fields.Date.context_today)
    tur = fields.Selection([('satis', 'Satış'), ('hurda', 'Hurdaya Çıkış')], required=True, default='satis')
    satis_bedeli = fields.Monetary(string='Satış Bedeli (KDV hariç)')
    partner_id = fields.Many2one('res.partner', string='Alıcı Cari')
    karsi_account_id = fields.Many2one('account.account', string='Karşı Hesap',
                                       help='Cari seçilmezse satış bedelinin yazılacağı hesap (ör. kasa/banka).')

    def action_onayla(self):
        self.ensure_one()
        kiymet = self.kiymet_id
        if kiymet.state != 'active':
            raise UserError(self.env._('Yalnızca aktif sabit kıymet çıkarılabilir.'))
        current_year = kiymet.line_ids.filtered(lambda l: l.yil == self.date.year and l.kaydedilen)
        if current_year:
            raise UserError(self.env._('%s yılında amortisman kaydı var; VUK\'a göre satış yılında amortisman ayrılmaz. Önce o kayıtları iptal edin.', self.date.year))
        company = kiymet.company_id
        label = f'{kiymet.kod} {kiymet.name} - {"satış" if self.tur == "satis" else "hurdaya çıkış"}'
        lines = [
            {'account_id': kiymet.birikmis_account_id.id, 'balance': kiymet.birikmis, 'name': label},
            {'account_id': kiymet.account_id.id, 'balance': -kiymet.bedel, 'name': label},
        ]
        bedel = self.satis_bedeli if self.tur == 'satis' else 0.0
        if bedel:
            if self.partner_id:
                partner = self.partner_id.commercial_partner_id
                partner._atlas_add_cari_tipi('alici')
                account = partner.with_company(company).property_account_receivable_id
                lines.append({'account_id': account.id, 'partner_id': partner.id, 'balance': bedel, 'name': label})
            elif self.karsi_account_id:
                lines.append({'account_id': self.karsi_account_id.id, 'balance': bedel, 'name': label})
            else:
                raise UserError(self.env._('Satış bedeli için cari veya karşı hesap seçin.'))
        fark = bedel - kiymet.net_deger
        if not company.currency_id.is_zero(fark):
            account = account_by_code(self.env, company, '679' if fark > 0 else '689')
            lines.append({'account_id': account.id, 'balance': -fark, 'name': label})
        move = create_entry(self.env, company, self.date, label, lines)
        kiymet.write({'state': 'closed', 'satis_tarihi': self.date, 'satis_move_id': move.id})
        return move._get_records_action()
