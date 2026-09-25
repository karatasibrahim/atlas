from contextlib import contextmanager

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL

from .atlas_belge_turu import FIS_TURU_SELECTION, MOVE_TYPE_BELGE

KASA_FIS_TURLERI = ('tahsil', 'tediye')


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_fis_turu = fields.Selection(
        FIS_TURU_SELECTION, string='Fiş Türü', index=True, tracking=True,
        help='Yalnızca muhasebe fişleri (yevmiye kayıtları) için.')
    atlas_belge_turu = fields.Char(compute='_compute_atlas_belge_turu')
    atlas_seri_id = fields.Many2one(
        'atlas.seri', string='Seri', index='btree_not_null', tracking=True,
        compute='_compute_atlas_seri_id', store=True, readonly=False, precompute=True,
        check_company=True, ondelete='restrict',
        domain="[('company_id', '=', company_id), ('belge_turu_ids.code', '=', atlas_belge_turu),"
               " ('journal_id', 'in', (journal_id, False))]",
        help='Belge numarası bu serinin ön eki ve sayacıyla onayda verilir.')
    atlas_kasa_account_id = fields.Many2one(
        'account.account', string='Kasa Hesabı', compute='_compute_atlas_kasa_account_id')

    _atlas_seri_unique_name = models.UniqueIndex(
        "(atlas_seri_id, name) WHERE (atlas_seri_id IS NOT NULL AND state = 'posted' AND name != '/')",
        "Bu seride aynı numaralı başka bir belge var.",
    )

    # -------------------------------------------------------------------------
    # Hesaplamalar
    # -------------------------------------------------------------------------

    @api.depends('move_type', 'atlas_fis_turu')
    def _compute_atlas_belge_turu(self):
        for move in self:
            move.atlas_belge_turu = move._atlas_get_belge_turu()

    def _atlas_get_belge_turu(self):
        self.ensure_one()
        if self.move_type == 'entry':
            return self.atlas_fis_turu or False
        return MOVE_TYPE_BELGE.get(self.move_type, False)

    @api.depends('move_type', 'atlas_fis_turu', 'journal_id', 'company_id')
    def _compute_atlas_seri_id(self):
        Seri = self.env['atlas.seri']
        for move in self:
            if move.state != 'draft' or (move.name and move.name != '/'):
                continue
            belge_turu = move._atlas_get_belge_turu()
            seri = move.atlas_seri_id
            if seri and belge_turu in seri.belge_turu_ids.mapped('code') and seri.company_id == move.company_id \
                    and seri.journal_id in (move.journal_id, Seri.journal_id):
                continue
            move.atlas_seri_id = belge_turu and Seri._get_default(belge_turu, move.company_id, move.journal_id)

    @api.depends('atlas_fis_turu', 'journal_id')
    def _compute_atlas_kasa_account_id(self):
        for move in self:
            is_kasa = move.atlas_fis_turu in KASA_FIS_TURLERI and move.journal_id.type == 'cash'
            move.atlas_kasa_account_id = move.journal_id.default_account_id if is_kasa else False

    @api.depends('date', 'journal_id', 'move_type', 'name', 'posted_before', 'sequence_number', 'sequence_prefix',
                 'state', 'atlas_seri_id')
    def _compute_name_placeholder(self):
        seri_moves = self.filtered(lambda m: m.atlas_seri_id and (not m.name or m.name == '/') and m.date)
        for move in seri_moves:
            format_string, values = move.atlas_seri_id._get_next_sequence_format(move.date)
            move.name_placeholder = format_string.format(seq=values['seq'] + 1)
        super(AccountMove, self - seri_moves)._compute_name_placeholder()

    # -------------------------------------------------------------------------
    # Yevmiye seçimi
    # -------------------------------------------------------------------------

    def _get_valid_journal_types(self):
        if self.move_type == 'entry' and self.atlas_fis_turu in KASA_FIS_TURLERI:
            return ['cash']
        return super()._get_valid_journal_types()

    def _search_default_journal(self):
        belge_turu = self._atlas_get_belge_turu()
        if belge_turu:
            seri = self.env['atlas.seri']._get_default(belge_turu, self.company_id or self.env.company)
            if seri.journal_id and seri.journal_id.type in self._get_valid_journal_types():
                return seri.journal_id
        return super()._search_default_journal()

    @api.onchange('atlas_fis_turu')
    def _onchange_atlas_fis_turu(self):
        if self.journal_id.type not in self._get_valid_journal_types():
            self.journal_id = self._search_default_journal()

    @api.onchange('atlas_seri_id')
    def _onchange_atlas_seri_id(self):
        if self.atlas_seri_id.journal_id:
            self.journal_id = self.atlas_seri_id.journal_id

    # -------------------------------------------------------------------------
    # Numaralandırma
    # -------------------------------------------------------------------------

    def _get_next_sequence_format(self):
        if self.atlas_seri_id:
            return self.atlas_seri_id._get_next_sequence_format(self.date)
        return super()._get_next_sequence_format()

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        # Serili belgeler Odoo'nun yevmiye bazlı sayacına karışmasın
        if self.atlas_seri_id:
            return super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
        return super(AccountMove, self.with_context(atlas_exclude_seri=True))._get_last_sequence(
            relaxed=relaxed, with_prefix=with_prefix)

    def _get_last_sequence_domain(self, relaxed=False):
        condition = super()._get_last_sequence_domain(relaxed)
        if self.atlas_seri_id:
            return SQL("%s AND atlas_seri_id = %s", condition, self.atlas_seri_id.id)
        if self.env.context.get('atlas_exclude_seri'):
            return SQL("%s AND atlas_seri_id IS NULL", condition)
        return condition

    @api.model
    def _search(self, domain, *args, **kwargs):
        # Serisiz belgenin "önceki numara" araması (_get_last_sequence_domain içindeki search) serili belgeleri görmesin
        if self.env.context.get('atlas_exclude_seri'):
            domain = Domain.AND([domain, [('atlas_seri_id', '=', False)]])
        return super()._search(domain, *args, **kwargs)

    # -------------------------------------------------------------------------
    # Tahsil / Tediye: kasa karşılık satırı
    # -------------------------------------------------------------------------

    def _get_sync_stack(self, container):
        stack, update_containers = super()._get_sync_stack(container)
        kasa_container = {}

        def update_all_containers():
            result = update_containers()
            kasa_container['records'] = container['records'].filtered(
                lambda m: m.move_type == 'entry' and m.atlas_fis_turu in KASA_FIS_TURLERI)
            return result

        update_all_containers()
        stack.append((25, self._atlas_sync_kasa_lines(kasa_container)))
        return stack, update_all_containers

    @contextmanager
    def _atlas_sync_kasa_lines(self, container):
        yield
        for move in container['records']:
            if move.state == 'posted' or not move.atlas_kasa_account_id:
                continue
            kasa_lines = move.line_ids.filtered('atlas_kasa_line')
            other_lines = move.line_ids - kasa_lines
            balance = -sum(other_lines.mapped('balance'))
            if not other_lines or move.company_currency_id.is_zero(balance):
                kasa_lines.unlink()
                continue
            vals = {'account_id': move.atlas_kasa_account_id.id, 'balance': balance, 'amount_currency': balance}
            if kasa_lines:
                kasa_lines[1:].unlink()
                kasa_lines[0].write(vals)
            else:
                self.env['account.move.line'].create({
                    **vals,
                    'move_id': move.id,
                    'name': dict(FIS_TURU_SELECTION)[move.atlas_fis_turu] + ' - Kasa',
                    'atlas_kasa_line': True,
                    'currency_id': move.company_currency_id.id,
                })

    # -------------------------------------------------------------------------
    # Onay
    # -------------------------------------------------------------------------

    def _post(self, soft=True):
        for move in self.filtered(lambda m: m.move_type == 'entry'):
            move._atlas_check_fis()
        return super()._post(soft=soft)

    def _atlas_check_fis(self):
        self.ensure_one()
        if self.atlas_fis_turu in KASA_FIS_TURLERI:
            if not self.atlas_kasa_account_id:
                raise UserError(self.env._('Tahsil/Tediye fişi bir kasa yevmiyesinde olmalıdır: %s', self.display_name))
            kasa_balance = sum(self.line_ids.filtered(lambda l: l.account_id == self.atlas_kasa_account_id).mapped('balance'))
            if self.atlas_fis_turu == 'tahsil' and kasa_balance <= 0:
                raise UserError(self.env._('Tahsil fişinde kasa borçlanmalıdır (kasaya para girişi).'))
            if self.atlas_fis_turu == 'tediye' and kasa_balance >= 0:
                raise UserError(self.env._('Tediye fişinde kasa alacaklanmalıdır (kasadan para çıkışı).'))
        self.line_ids._atlas_check_cari_partner()
