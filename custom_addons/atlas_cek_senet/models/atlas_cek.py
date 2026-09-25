from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .atlas_cek_islem import DURUM_SELECTION, EVRAK_TURU_SELECTION, ISLEM_SELECTION, ISLEMLER


class AtlasCek(models.Model):
    """Çek / senet evrakı. Durumu, onaylanmış bordrolardaki son işlemden hesaplanır."""
    _name = 'atlas.cek'
    _description = 'Çek / Senet'
    _inherit = ['mail.thread']
    _order = 'vade, id'
    _check_company_auto = True

    name = fields.Char(string='Portföy No', readonly=True, copy=False, default='/')
    evrak_turu = fields.Selection(EVRAK_TURU_SELECTION, string='Evrak Türü', required=True, readonly=True)
    seri_no = fields.Char(string='Çek / Senet No', required=True, tracking=True)
    vade = fields.Date(string='Vade', required=True, tracking=True)
    tutar = fields.Monetary(string='Tutar', required=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Para Birimi', required=True,
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Cari', readonly=True, tracking=True,
                                 help='Müşteri evrakında alındığı, firma evrakında verildiği cari.')
    banka_id = fields.Many2one('atlas.banka', string='Banka')
    sube = fields.Char(string='Şube')
    hesap_no = fields.Char(string='Hesap No / IBAN')
    kesideci = fields.Char(string='Keşideci / Borçlu', help='Çeki düzenleyen veya senedin borçlusu.')
    kesideci_vkn = fields.Char(string='Keşideci VKN/TCKN')
    kesideci_yeri = fields.Char(string='Keşide Yeri')
    aciklama = fields.Char(string='Açıklama')

    bordro_line_ids = fields.One2many('atlas.cek.bordro.line', 'cek_id', string='Hareketler', readonly=True)
    durum = fields.Selection(DURUM_SELECTION, string='Durum', compute='_compute_durum', store=True, tracking=True, index=True)
    konum_journal_id = fields.Many2one('account.journal', string='Bulunduğu Banka', compute='_compute_durum', store=True)
    ciro_partner_id = fields.Many2one('res.partner', string='Ciro Edilen Cari', compute='_compute_durum', store=True)
    son_islem_tarihi = fields.Date(string='Son İşlem', compute='_compute_durum', store=True)
    taraf = fields.Selection([('musteri', 'Müşteri'), ('firma', 'Firma')], compute='_compute_taraf', store=True)
    kalan_gun = fields.Integer(string='Vadeye Kalan Gün', compute='_compute_kalan_gun')

    _seri_no_unique = models.UniqueIndex(
        '(company_id, evrak_turu, banka_id, seri_no) WHERE (durum IS DISTINCT FROM \'iptal\')',
        'Aynı bankaya ait bu numarada başka bir evrak var.',
    )

    @api.depends('evrak_turu')
    def _compute_taraf(self):
        for cek in self:
            cek.taraf = (cek.evrak_turu or '').split('_')[0] or False

    @api.depends('bordro_line_ids.bordro_id.state', 'bordro_line_ids.bordro_id.date')
    def _compute_durum(self):
        for cek in self:
            lines = cek.bordro_line_ids.filtered(lambda l: l.bordro_id.state == 'posted')
            last = lines.sorted(lambda l: (l.bordro_id.date, l.bordro_id.id))[-1:]
            if not last:
                cek.durum = 'iptal' if cek.bordro_line_ids else False
                cek.konum_journal_id = cek.ciro_partner_id = cek.son_islem_tarihi = False
                continue
            bordro = last.bordro_id
            cek.durum = ISLEMLER[bordro.islem][4]
            cek.konum_journal_id = bordro.journal_id if cek.durum in ('tahsilde', 'teminatta') else False
            cek.ciro_partner_id = bordro.partner_id if cek.durum == 'ciro' else False
            cek.son_islem_tarihi = bordro.date

    def _compute_kalan_gun(self):
        today = fields.Date.context_today(self)
        for cek in self:
            cek.kalan_gun = (cek.vade - today).days if cek.vade else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.cek') or '/'
        return super().create(vals_list)

    @api.depends('name', 'seri_no', 'tutar')
    def _compute_display_name(self):
        for cek in self:
            cek.display_name = f'{cek.name} / {cek.seri_no or ""}'

    def _account(self, durum=None):
        self.ensure_one()
        return self.company_id._atlas_cek_account(self.evrak_turu, durum or self.durum)

    def _atlas_new_bordro(self, islem):
        """Seçili evraklarla yeni bordro formu açar."""
        evrak_turleri = set(self.mapped('evrak_turu'))
        if len(evrak_turleri) != 1 or len(self.currency_id) != 1:
            raise UserError(self.env._('Bordroya aynı türde ve aynı para biriminde evraklar seçilmelidir.'))
        evrak_tipi = self[0].evrak_turu.split('_')[1]
        partner = self.partner_id if islem in ('karsiliksiz', 'musteriye_iade', 'firma_iade') and len(self.partner_id) == 1 else False
        return {
            'type': 'ir.actions.act_window',
            'name': dict(ISLEM_SELECTION)[islem],
            'res_model': 'atlas.cek.bordro',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_islem': islem,
                'default_evrak_tipi': evrak_tipi,
                'default_currency_id': self.currency_id.id,
                'default_partner_id': partner and partner.id,
                'default_line_ids': [Command.create({'cek_id': cek.id}) for cek in self],
            },
        }

    def action_ciro(self):
        return self._atlas_new_bordro('ciro')

    def action_tahsile_ver(self):
        return self._atlas_new_bordro('tahsile_ver')

    def action_teminata_ver(self):
        return self._atlas_new_bordro('teminata_ver')

    def action_tahsil(self):
        return self._atlas_new_bordro('tahsil')

    def action_karsiliksiz(self):
        return self._atlas_new_bordro('karsiliksiz')

    def action_musteriye_iade(self):
        return self._atlas_new_bordro('musteriye_iade')

    def action_firma_odeme(self):
        return self._atlas_new_bordro('firma_odeme')

    def action_open_bordrolar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Bordrolar: %s', self.display_name),
            'res_model': 'atlas.cek.bordro',
            'view_mode': 'list,form',
            'domain': [('line_ids.cek_id', '=', self.id)],
        }
