import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError

EBELGE_TIPLERI = [('efatura', 'e-Fatura'), ('earsiv', 'e-Arşiv'), ('kagit', 'Kâğıt / Matbu')]
SENARYOLAR = [('TEMELFATURA', 'Temel Fatura'), ('TICARIFATURA', 'Ticari Fatura'), ('IHRACAT', 'İhracat'),
              ('EARSIVFATURA', 'e-Arşiv Fatura')]
FATURA_TIPLERI = [('SATIS', 'Satış'), ('IADE', 'İade'), ('TEVKIFAT', 'Tevkifat'), ('ISTISNA', 'İstisna'),
                  ('IHRACKAYITLI', 'İhraç Kayıtlı')]
GIDEN = ('out_invoice', 'in_refund')  # GİB'e bizim düzenleyip gönderdiğimiz belgeler


class AtlasSeri(models.Model):
    _inherit = 'atlas.seri'

    ebelge_tipi = fields.Selection(EBELGE_TIPLERI, string='e-Belge Tipi',
                                   help='Bu seri yalnızca bu tipteki faturalarda otomatik seçilir. Boşsa tümünde.')

    @api.model
    def _atlas_ebelge_serileri_kur(self):
        """Giden fatura serisini e-Fatura olarak işaretler, yoksa e-Arşiv serisi açar (GİB 16 karakter)."""
        BelgeTuru = self.env['atlas.belge.turu']
        giden = BelgeTuru.search([('code', 'in', ('satis_fatura', 'alis_iade'))])
        for company in self.env['res.company'].search([]):
            seriler = self.search([('company_id', '=', company.id), ('belge_turu_ids', 'in', giden.ids)])
            if not seriler:
                continue
            seriler.filtered(lambda s: not s.ebelge_tipi and s.on_ek == 'ATL').ebelge_tipi = 'efatura'
            if not seriler.filtered(lambda s: s.ebelge_tipi == 'earsiv') and not self.with_context(active_test=False).search_count(
                    [('company_id', '=', company.id), ('on_ek', '=', 'ARS')]):
                self.create({'name': 'e-Arşiv Faturaları', 'company_id': company.id, 'on_ek': 'ARS', 'yil_ekle': True,
                             'hane': 9, 'ebelge_tipi': 'earsiv', 'belge_turu_ids': [(6, 0, giden.ids)], 'sequence': 15})


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_ebelge_aktif = fields.Boolean(string='e-Fatura / e-Arşiv Kullanılıyor')
    atlas_efatura_senaryo = fields.Selection([('TICARIFATURA', 'Ticari Fatura'), ('TEMELFATURA', 'Temel Fatura')],
                                             string='Varsayılan e-Fatura Senaryosu', default='TICARIFATURA')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_ebelge_aktif = fields.Boolean(related='company_id.atlas_ebelge_aktif', readonly=False)
    atlas_efatura_senaryo = fields.Selection(related='company_id.atlas_efatura_senaryo', readonly=False)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    atlas_efatura_mukellef = fields.Boolean(string='e-Fatura Mükellefi',
                                            help='GİB e-Fatura kayıtlı kullanıcısı. Entegratör bağlantısı kurulunca otomatik sorgulanacak.')
    atlas_efatura_etiket = fields.Char(string='e-Fatura Posta Kutusu (PK)', help='ör. urn:mail:defaultpk@firma.com.tr')
    atlas_efatura_senaryo = fields.Selection([('TICARIFATURA', 'Ticari Fatura'), ('TEMELFATURA', 'Temel Fatura')],
                                             string='e-Fatura Senaryosu', help='Boşsa şirket varsayılanı kullanılır.')
    atlas_efatura_kontrol = fields.Date(string='Mükellefiyet Kontrol Tarihi')


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_ebelge_tipi = fields.Selection(EBELGE_TIPLERI, string='e-Belge Tipi', compute='_compute_atlas_ebelge', store=True,
                                         readonly=False, precompute=True, copy=False)
    atlas_ebelge_senaryo = fields.Selection(SENARYOLAR, string='Senaryo', compute='_compute_atlas_ebelge', store=True,
                                            readonly=False, precompute=True, copy=False)
    atlas_fatura_tipi = fields.Selection(FATURA_TIPLERI, string='Fatura Tipi', compute='_compute_atlas_fatura_tipi', store=True,
                                         readonly=False, precompute=True, copy=False)
    atlas_ettn = fields.Char(string='ETTN', copy=False, readonly=True, index='btree_not_null',
                             help='GİB evrensel tekil tanımlama numarası (UUID).')

    def _atlas_ebelge_uygun(self):
        self.ensure_one()
        return self.move_type in GIDEN and self.company_id.atlas_ebelge_aktif

    def _atlas_ihracat_mi(self):
        return self.fiscal_position_id.atlas_gib_kod_id.tip == 'ihracat'

    @api.depends('move_type', 'partner_id', 'partner_id.atlas_efatura_mukellef', 'fiscal_position_id', 'company_id.atlas_ebelge_aktif')
    def _compute_atlas_ebelge(self):
        for move in self:
            if move.state != 'draft' and move.atlas_ebelge_tipi:
                continue
            if not move._atlas_ebelge_uygun():
                move.atlas_ebelge_tipi = 'kagit' if move.move_type in GIDEN else False
                move.atlas_ebelge_senaryo = False
                continue
            ticari = move.partner_id.commercial_partner_id
            if move._atlas_ihracat_mi():
                move.atlas_ebelge_tipi, move.atlas_ebelge_senaryo = 'efatura', 'IHRACAT'
            elif ticari.atlas_efatura_mukellef:
                move.atlas_ebelge_tipi = 'efatura'
                senaryo = ticari.atlas_efatura_senaryo or move.company_id.atlas_efatura_senaryo or 'TICARIFATURA'
                # İade faturası ticari senaryoda gönderilemez
                move.atlas_ebelge_senaryo = 'TEMELFATURA' if move.move_type == 'in_refund' else senaryo
            else:
                move.atlas_ebelge_tipi, move.atlas_ebelge_senaryo = 'earsiv', 'EARSIVFATURA'

    @api.depends('move_type', 'fiscal_position_id', 'invoice_line_ids.tax_ids')
    def _compute_atlas_fatura_tipi(self):
        for move in self:
            if move.move_type not in GIDEN:
                move.atlas_fatura_tipi = False
                continue
            if move.state != 'draft' and move.atlas_fatura_tipi:
                continue
            kod_tipleri = set(move.invoice_line_ids.tax_ids.atlas_gib_kod_id.mapped('tip'))
            kod_tipleri |= set(move.invoice_line_ids.tax_ids.children_tax_ids.atlas_gib_kod_id.mapped('tip'))
            fp_tip = move.fiscal_position_id.atlas_gib_kod_id.tip
            if move.move_type == 'in_refund':
                move.atlas_fatura_tipi = 'IADE'
            elif fp_tip == 'ihrac_kayitli' or 'ihrac_kayitli' in kod_tipleri:
                move.atlas_fatura_tipi = 'IHRACKAYITLI'
            elif 'tevkifat' in kod_tipleri:
                move.atlas_fatura_tipi = 'TEVKIFAT'
            elif fp_tip in ('istisna', 'ihracat') or kod_tipleri & {'istisna', 'ihracat'}:
                move.atlas_fatura_tipi = 'ISTISNA'
            else:
                move.atlas_fatura_tipi = 'SATIS'

    @api.depends('move_type', 'atlas_fis_turu', 'journal_id', 'company_id', 'atlas_ebelge_tipi')
    def _compute_atlas_seri_id(self):
        super()._compute_atlas_seri_id()
        Seri = self.env['atlas.seri']
        for move in self:
            if move.state != 'draft' or (move.name and move.name != '/') or not move.atlas_ebelge_tipi:
                continue
            seri = move.atlas_seri_id
            if seri and seri.ebelge_tipi in (False, move.atlas_ebelge_tipi):
                continue
            belge_turu = move._atlas_get_belge_turu()
            adaylar = Seri.search([('company_id', '=', move.company_id.id), ('belge_turu_ids.code', '=', belge_turu),
                                   ('ebelge_tipi', '=', move.atlas_ebelge_tipi),
                                   ('journal_id', 'in', (move.journal_id.id, False))])
            if adaylar:
                move.atlas_seri_id = adaylar.sorted(lambda s: (not s.varsayilan, not s.journal_id, s.sequence, s.id))[:1]

    def _post(self, soft=True):
        for move in self.filtered(lambda m: m.is_invoice() and m._atlas_ebelge_uygun()):
            move._atlas_ebelge_kontrol()
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.is_invoice() and m._atlas_ebelge_uygun() and not m.atlas_ettn):
            move.atlas_ettn = str(uuid.uuid4()).upper()
        return posted

    def _atlas_ebelge_kontrol(self):
        self.ensure_one()
        ticari = self.partner_id.commercial_partner_id
        eksik = []
        if self.atlas_ebelge_tipi == 'efatura':
            if not ticari.vat:
                eksik.append(self.env._('alıcı VKN/TCKN'))
            if self.atlas_ebelge_senaryo != 'IHRACAT' and not ticari.atlas_efatura_mukellef:
                eksik.append(self.env._('alıcı e-Fatura mükellefi değil (e-Arşiv seçin)'))
        if self.atlas_ebelge_tipi in ('efatura', 'earsiv') and self.atlas_seri_id and not self.atlas_seri_id.gib_uyumlu:
            eksik.append(self.env._('seri GİB biçiminde değil (3 harf + yıl + 9 hane)'))
        if self.atlas_ebelge_senaryo == 'IHRACAT' and not self._atlas_ihracat_mi():
            eksik.append(self.env._('ihracat senaryosu için İhracat mali koşulu'))
        if eksik:
            raise UserError(self.env._('%(fatura)s e-Belge kontrolü: %(eksik)s.', fatura=self.name or self.partner_id.name,
                                       eksik=', '.join(eksik)))
