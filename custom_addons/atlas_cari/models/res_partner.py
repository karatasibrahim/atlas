import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

# Cari tipi -> açılacak muhasebe alt hesaplarının ana hesap kodları (ilki cari kodunu belirler)
CARI_TIPI_PREFIXES = {
    'alici': ('120',),
    'satici': ('320',),
    'alici_satici': ('120', '320'),
}
PREFIX_ACCOUNT = {
    '120': ('asset_receivable', 'property_account_receivable_id'),
    '320': ('liability_payable', 'property_account_payable_id'),
}
CARI_KODU_REGEX = re.compile(r'^(\d{3})-(\d{2})-(\d{4})$')
DEFAULT_GRUP_CODE = '00'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    atlas_cari_tipi = fields.Selection(
        [
            ('alici', 'Alıcı'),
            ('satici', 'Satıcı'),
            ('alici_satici', 'Alıcı + Satıcı'),
        ],
        string='Cari Tipi',
        tracking=True,
        help='Alıcı: 120 alt hesabı, Satıcı: 320 alt hesabı, Alıcı + Satıcı: her ikisi açılır.',
    )
    atlas_cari_grup_id = fields.Many2one('atlas.cari.grup', string='Cari Grubu', tracking=True)
    atlas_bolge_id = fields.Many2one('atlas.cari.bolge', string='Bölge')
    atlas_ozel_kod1_id = fields.Many2one('atlas.cari.ozel.kod', string='Özel Kod 1', domain=[('sira', '=', '1')])
    atlas_ozel_kod2_id = fields.Many2one('atlas.cari.ozel.kod', string='Özel Kod 2', domain=[('sira', '=', '2')])
    atlas_account_ids = fields.One2many('account.account', 'atlas_partner_id', string='Cari Muhasebe Hesapları')

    atlas_company_currency_id = fields.Many2one('res.currency', compute='_compute_atlas_bakiye')
    atlas_borc = fields.Monetary(string='Borç', compute='_compute_atlas_bakiye', currency_field='atlas_company_currency_id')
    atlas_alacak = fields.Monetary(string='Alacak', compute='_compute_atlas_bakiye', currency_field='atlas_company_currency_id')
    atlas_bakiye = fields.Monetary(string='Bakiye', compute='_compute_atlas_bakiye', currency_field='atlas_company_currency_id',
                                   help='Pozitif: cari borçlu (bize borcu var), negatif: cari alacaklı.')

    # -------------------------------------------------------------------------
    # Hesaplamalar
    # -------------------------------------------------------------------------

    def _compute_atlas_bakiye(self):
        company = self.env.company
        self.atlas_company_currency_id = company.currency_id
        commercial = self.commercial_partner_id
        totals = {
            partner.id: (debit, credit)
            for partner, debit, credit in self.env['atlas.cari.hareket']._read_group(
                [('partner_id', 'in', commercial.ids), ('company_id', '=', company.id)],
                ['partner_id'],
                ['debit:sum', 'credit:sum'],
            )
        }
        for partner in self:
            debit, credit = totals.get(partner.commercial_partner_id.id, (0.0, 0.0))
            partner.atlas_borc = debit
            partner.atlas_alacak = credit
            partner.atlas_bakiye = debit - credit

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + [
            'atlas_cari_tipi', 'atlas_cari_grup_id', 'atlas_bolge_id', 'atlas_ozel_kod1_id', 'atlas_ozel_kod2_id',
        ]

    # -------------------------------------------------------------------------
    # Kısıtlar
    # -------------------------------------------------------------------------

    @api.constrains('ref', 'atlas_cari_tipi')
    def _check_atlas_cari_kodu(self):
        for partner in self.filtered(lambda p: p.atlas_cari_tipi and p.ref and p._atlas_is_cari()):
            match = CARI_KODU_REGEX.match(partner.ref)
            if not match:
                raise ValidationError(self.env._(
                    'Cari kodu 120-00-0001 biçiminde olmalıdır: %s', partner.ref))
            if match.group(1) != CARI_TIPI_PREFIXES[partner.atlas_cari_tipi][0]:
                raise ValidationError(self.env._(
                    '%(tipi)s tipindeki cari için kod %(prefix)s ile başlamalıdır: %(ref)s',
                    tipi=dict(self._fields['atlas_cari_tipi'].selection)[partner.atlas_cari_tipi],
                    prefix=CARI_TIPI_PREFIXES[partner.atlas_cari_tipi][0],
                    ref=partner.ref,
                ))
            duplicate = self.with_context(active_test=False).search([
                ('id', '!=', partner.id),
                ('ref', '=', partner.ref),
                ('atlas_cari_tipi', '!=', False),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._(
                    '%(ref)s cari kodu zaten "%(name)s" carisinde kullanılıyor.',
                    ref=partner.ref, name=duplicate.display_name))

    @api.constrains('vat', 'country_id')
    def _check_atlas_vkn_tckn(self):
        from stdnum.tr import tckimlik, vkn  # noqa: PLC0415

        for partner in self.filtered(lambda p: p.vat and p.country_id.code == 'TR'):
            number = partner.vat.upper().removeprefix('TR').strip()
            if len(number) == 10 and vkn.is_valid(number):
                continue
            if len(number) == 11 and tckimlik.is_valid(number):
                continue
            raise ValidationError(self.env._(
                'Geçersiz VKN/TCKN: %s. VKN 10 haneli, TCKN 11 haneli olmalı ve kontrol hanesi doğru olmalıdır.',
                partner.vat))

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._atlas_ensure_cari()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if vals.keys() & {'atlas_cari_tipi', 'atlas_cari_grup_id', 'parent_id', 'is_company', 'company_id'}:
            self._atlas_ensure_cari()
        if 'name' in vals:
            for partner in self.filtered('atlas_account_ids'):
                partner.atlas_account_ids.sudo().name = partner.name
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_atlas_cari_accounts(self):
        """Hareketsiz carinin alt hesapları cariyle birlikte silinir; hareketi olan cari silinemez."""
        accounts = self.sudo().atlas_account_ids
        if not accounts:
            return
        used = self.env['account.move.line'].sudo().search([('account_id', 'in', accounts.ids)], limit=1)
        if used:
            raise UserError(self.env._(
                '"%s" carisinin muhasebe hareketleri var; silinemez. Bunun yerine arşivleyin.',
                used.account_id.atlas_partner_id.display_name))
        for field_name in ('property_account_receivable_id', 'property_account_payable_id'):
            for company in accounts.company_ids:
                partners = self.sudo().with_company(company).filtered(lambda p: p[field_name] in accounts)
                if partners:
                    partners[field_name] = False
        accounts.atlas_partner_id = False
        accounts.unlink()

    # -------------------------------------------------------------------------
    # Cari kodu ve alt hesaplar
    # -------------------------------------------------------------------------

    def _atlas_is_cari(self):
        self.ensure_one()
        return self.commercial_partner_id == self

    def _atlas_cari_companies(self):
        """Carinin muhasebe hesabının açılacağı ana şirketler."""
        self.ensure_one()
        if self.company_id:
            return self.company_id.root_id
        return self.env['res.company'].sudo().search([('parent_id', '=', False), ('chart_template', '!=', False)])

    def _atlas_next_code(self, prefix, grup_code, companies):
        """PPP-GG-NNNN biçiminde sıradaki boş kodu döndürür (hesap planı ve cari kodları taranır)."""
        pattern = f'{prefix}-{grup_code}-%'
        Account = self.env['account.account'].sudo().with_context(active_test=False)
        codes = []
        for company in companies:
            codes += Account.with_company(company).search([('code', '=like', pattern)]).mapped('code')
        codes += self.sudo().with_context(active_test=False).search([('ref', '=like', pattern)]).mapped('ref')
        numbers = [int(m.group(3)) for code in codes if (m := CARI_KODU_REGEX.match(code or ''))]
        return f'{prefix}-{grup_code}-{max(numbers, default=0) + 1:04d}'

    def _atlas_ensure_cari(self):
        """Cari tipi seçilmiş ticari carilere cari kodu verir ve 120/320 alt hesaplarını açar.

        Mevcut hesaplar silinmez; tip genişletilirse (Alıcı -> Alıcı + Satıcı) eksik hesap açılır.
        """
        for partner in self.filtered(lambda p: p.atlas_cari_tipi and p._atlas_is_cari()):
            companies = partner._atlas_cari_companies()
            if not companies:
                continue
            prefixes = CARI_TIPI_PREFIXES[partner.atlas_cari_tipi]
            grup_code = partner.atlas_cari_grup_id.code or DEFAULT_GRUP_CODE
            if not partner.ref:
                partner.ref = partner._atlas_next_code(prefixes[0], grup_code, companies)

            for prefix in prefixes:
                account = partner.sudo().atlas_account_ids.with_company(companies[0]).filtered(
                    lambda a: a.code and a.code.startswith(f'{prefix}-'))[:1]
                if not account:
                    code = partner.ref if partner.ref.startswith(f'{prefix}-') else \
                        partner._atlas_next_code(prefix, grup_code, companies)
                    account = partner._atlas_create_account(prefix, code, companies)
                partner._atlas_link_account(prefix, account, companies)

    def _atlas_create_account(self, prefix, code, companies):
        self.ensure_one()
        account_type, _property = PREFIX_ACCOUNT[prefix]
        account = self.env['account.account'].sudo().with_company(companies[0]).create({
            'name': self.name,
            'code': code,
            'account_type': account_type,
            'reconcile': True,
            'company_ids': [Command.set(companies.ids)],
            'atlas_partner_id': self.id,
        })
        for company in companies[1:]:
            account.with_company(company).code = code
        return account

    def _atlas_link_account(self, prefix, account, companies):
        """Hesabı carinin ilgili şirketlerdeki varsayılan alacak/borç hesabı yapar."""
        self.ensure_one()
        _account_type, property_field = PREFIX_ACCOUNT[prefix]
        for company in companies:
            partner = self.sudo().with_company(company)
            if company not in account.company_ids:
                code = account.with_company(companies[0]).code
                account.sudo().company_ids = [Command.link(company.id)]
                account.sudo().with_company(company).code = code
            if partner[property_field] != account:
                partner[property_field] = account

    def _atlas_add_cari_tipi(self, needed):
        """Cariyi gerekli tipe genişletir (ör. satıcıya satış faturası kesilince Alıcı + Satıcı yapar)."""
        self.ensure_one()
        current = self.atlas_cari_tipi
        if current in (needed, 'alici_satici'):
            return False
        self.sudo().atlas_cari_tipi = needed if not current else 'alici_satici'
        return True

    def action_atlas_ensure_cari_accounts(self):
        """Seçili carilerin eksik alt hesaplarını (yeni eklenen şirketler dahil) tamamlar."""
        self._atlas_ensure_cari()

    # -------------------------------------------------------------------------
    # Eylemler
    # -------------------------------------------------------------------------

    def action_atlas_cari_hareket(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_cari.action_atlas_cari_hareket')
        action['domain'] = [('partner_id', '=', self.commercial_partner_id.id)]
        action['display_name'] = self.env._('Cari Hareketleri: %s', self.commercial_partner_id.display_name)
        return action

    def action_atlas_cari_ekstre(self):
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_cari.action_atlas_cari_ekstre_wizard')
        action['context'] = {'default_partner_ids': self.commercial_partner_id.ids}
        return action
