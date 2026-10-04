import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# İl kodu (01-81) + 1-3 harf + 2-5 rakam (ör. 34ABC123, 06A1234)
PLAKA_RE = re.compile(r'^(0[1-9]|[1-7][0-9]|8[01])[A-Z]{1,3}[0-9]{2,5}$')


def plaka_normalize(plaka):
    return re.sub(r'[\s\-]', '', (plaka or '').upper().replace('İ', 'I'))


class AtlasIrsaliyePlaka(models.Model):
    _name = 'atlas.irsaliye.plaka'
    _description = 'Araç / Dorse Plakası'
    _order = 'tip, name'

    name = fields.Char(string='Plaka', required=True, index=True)
    tip = fields.Selection([('arac', 'Araç (Çekici / Kamyon)'), ('dorse', 'Dorse / Römork')], string='Tip',
                           required=True, default='arac')
    tasiyici_id = fields.Many2one('res.partner', string='Taşıyıcı Firma', help='Boşsa şirketin kendi aracıdır.')
    sofor_id = fields.Many2one('atlas.irsaliye.sofor', string='Varsayılan Şoför')
    aciklama = fields.Char(string='Açıklama', help='Marka, model, kapasite...')
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _plaka_uniq = models.UniqueIndex('(name, company_id)', 'Bu plaka zaten kayıtlı.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = plaka_normalize(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('name'):
            vals['name'] = plaka_normalize(vals['name'])
        return super().write(vals)

    @api.constrains('name')
    def _check_plaka(self):
        for plaka in self:
            if not PLAKA_RE.match(plaka.name or ''):
                raise ValidationError(self.env._('Geçersiz plaka: %s (ör. 34ABC123).', plaka.name))

    @api.depends('name', 'tip')
    def _compute_display_name(self):
        for plaka in self:
            p = plaka.name or ''
            m = re.match(r'^(\d{2})([A-Z]+)(\d+)$', p)
            plaka.display_name = f'{m[1]} {m[2]} {m[3]}' if m else p


class AtlasIrsaliyeSofor(models.Model):
    _name = 'atlas.irsaliye.sofor'
    _description = 'Şoför'
    _order = 'ad, soyad'

    ad = fields.Char(string='Ad', required=True)
    soyad = fields.Char(string='Soyad', required=True)
    name = fields.Char(compute='_compute_name', store=True, string='Ad Soyad')
    tckn = fields.Char(string='TCKN', size=11, required=True)
    telefon = fields.Char(string='Telefon')
    tasiyici_id = fields.Many2one('res.partner', string='Taşıyıcı Firma', help='Boşsa şirketin kendi şoförüdür.')
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _tckn_uniq = models.UniqueIndex('(tckn, company_id)', 'Bu TCKN ile şoför zaten kayıtlı.')

    @api.depends('ad', 'soyad')
    def _compute_name(self):
        for sofor in self:
            sofor.name = f'{sofor.ad or ""} {sofor.soyad or ""}'.strip()

    @api.constrains('tckn')
    def _check_tckn(self):
        from stdnum.tr import tckimlik  # noqa: PLC0415 (modül yüklenirken veri dosyası okumasın)
        for sofor in self:
            if not tckimlik.is_valid(sofor.tckn or ''):
                raise ValidationError(self.env._('Geçersiz TCKN: %s', sofor.tckn))


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_eirsaliye = fields.Boolean(string='e-İrsaliye Kullanılıyor',
                                     help='Sevkiyat doğrulanırken e-İrsaliye için zorunlu sevk bilgileri kontrol edilir.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_eirsaliye = fields.Boolean(related='company_id.atlas_eirsaliye', readonly=False)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    atlas_irsaliye_tipi = fields.Selection([('SEVK', 'e-İrsaliye (SEVK)'), ('MATBUDAN', 'Matbu irsaliye (MATBUDAN)')],
                                           string='İrsaliye Tipi', default='SEVK', copy=False)
    atlas_matbu_no = fields.Char(string='Matbu İrsaliye No', copy=False)
    atlas_matbu_tarih = fields.Date(string='Matbu İrsaliye Tarihi', copy=False)
    atlas_tasiyici_id = fields.Many2one('res.partner', string='Taşıyıcı Firma', copy=False,
                                        help='Nakliye/kargo firması. Seçilirse plaka ve şoför isteğe bağlıdır.')
    atlas_arac_id = fields.Many2one('atlas.irsaliye.plaka', string='Araç', copy=False, domain="[('tip', '=', 'arac')]")
    atlas_dorse_ids = fields.Many2many('atlas.irsaliye.plaka', 'atlas_picking_dorse_rel', 'picking_id', 'plaka_id',
                                       string='Dorseler', copy=False, domain="[('tip', '=', 'dorse')]")
    atlas_sofor_ids = fields.Many2many('atlas.irsaliye.sofor', 'atlas_picking_sofor_rel', 'picking_id', 'sofor_id',
                                       string='Şoförler', copy=False)

    @api.onchange('atlas_arac_id')
    def _onchange_atlas_arac_id(self):
        arac = self.atlas_arac_id
        if arac:
            if arac.sofor_id and not self.atlas_sofor_ids:
                self.atlas_sofor_ids = arac.sofor_id
            if arac.tasiyici_id and not self.atlas_tasiyici_id:
                self.atlas_tasiyici_id = arac.tasiyici_id

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._atlas_sevk_metinleri()
        return pickings

    def write(self, vals):
        res = super().write(vals)
        if vals.keys() & {'atlas_arac_id', 'atlas_dorse_ids', 'atlas_sofor_ids'}:
            self._atlas_sevk_metinleri()
        return res

    def _atlas_sevk_metinleri(self):
        """Tablolardan seçilenleri irsaliye çıktısının kullandığı metin alanlarına yazar."""
        for picking in self.filtered(lambda p: p.atlas_arac_id or p.atlas_dorse_ids or p.atlas_sofor_ids):
            super(StockPicking, picking).write({
                'atlas_arac_plaka': picking.atlas_arac_id.display_name or False,
                'atlas_dorse_plaka': ', '.join(picking.atlas_dorse_ids.mapped('display_name')) or False,
                'atlas_sofor_adi': ', '.join(picking.atlas_sofor_ids.mapped('name')) or False,
                'atlas_sofor_tckn': picking.atlas_sofor_ids[:1].tckn or False,
            })

    def _atlas_eirsaliye_eksikler(self):
        self.ensure_one()
        eksik = []
        if self.atlas_irsaliye_tipi == 'MATBUDAN':
            if not self.atlas_matbu_no:
                eksik.append(self.env._('matbu irsaliye no'))
            if not self.atlas_matbu_tarih:
                eksik.append(self.env._('matbu irsaliye tarihi'))
            return eksik
        if not self.partner_id:
            eksik.append(self.env._('alıcı'))
        elif not self.partner_id.commercial_partner_id.vat:
            eksik.append(self.env._('alıcı VKN/TCKN'))
        if self.atlas_tasiyici_id:
            if not self.atlas_tasiyici_id.commercial_partner_id.vat:
                eksik.append(self.env._('taşıyıcı firma VKN'))
        else:
            if not self.atlas_arac_id:
                eksik.append(self.env._('araç plakası'))
            if not self.atlas_sofor_ids:
                eksik.append(self.env._('şoför'))
        return eksik

    def _pre_action_done_hook(self):
        for picking in self.filtered(lambda p: p.picking_type_code == 'outgoing' and p.company_id.atlas_eirsaliye):
            eksik = picking._atlas_eirsaliye_eksikler()
            if eksik:
                raise UserError(self.env._('%(belge)s e-İrsaliye için eksik sevk bilgisi: %(eksik)s. "Sevk Bilgileri" sekmesinden doldurun.',
                                           belge=picking.name, eksik=', '.join(eksik)))
            if not picking.atlas_fiili_sevk_tarihi:
                picking.atlas_fiili_sevk_tarihi = fields.Datetime.now()
        return super()._pre_action_done_hook()
