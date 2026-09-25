import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .account_journal import normalize_iban
from .atlas_banka_ekstre_sablon import normalize_text

IBAN_REGEX = re.compile(r'TR\d{2}[\s]?(?:\d{4}[\s]?){5}\d{2}', re.I)
VKN_REGEX = re.compile(r'(?<!\d)(\d{10,11})(?!\d)')
CARI_KODU_REGEX = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
BELGE_NO_REGEX = re.compile(r'[A-Z0-9][A-Z0-9/_-]{5,}[0-9]')
MIN_PARTNER_NAME_LENGTH = 5


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    atlas_import_hash = fields.Char(index='btree_not_null', readonly=True, copy=False)
    atlas_referans = fields.Char(string='Dekont No', readonly=True)
    atlas_ekstre_bakiye = fields.Monetary(string='Ekstre Bakiyesi', readonly=True, currency_field='currency_id')

    atlas_karsi_hesap_id = fields.Many2one(
        'account.account', string='Karşı Hesap', check_company=True,
        help='Cari yerine doğrudan bir hesaba (masraf, faiz, vergi...) eşleştirmek için.')
    atlas_fatura_id = fields.Many2one(
        'account.move', string='Fatura', check_company=True,
        domain="[('commercial_partner_id', '=', partner_id), ('state', '=', 'posted'),"
               " ('payment_state', 'in', ('not_paid', 'partial')), ('move_type', '!=', 'entry')]",
        help='Önce bu fatura kapatılır, kalan tutar diğer açık kalemlere (vade sırasıyla) dağıtılır.')
    atlas_bekleyen_line_id = fields.Many2one(
        'account.move.line', string='Bekleyen Kayıt', check_company=True,
        help='Önceden girilmiş tahsilat/ödeme veya virman kaydı; ekstreyle kapatılır.')
    atlas_oneri = fields.Char(string='Öneri', readonly=True)

    # -------------------------------------------------------------------------
    # Öneri
    # -------------------------------------------------------------------------

    def action_atlas_oner(self):
        for st_line in self.filtered(lambda l: not l.is_reconciled):
            st_line._atlas_oner()

    def _atlas_text(self):
        return ' '.join(filter(None, [self.payment_ref, self.atlas_referans, self.partner_name, self.account_number]))

    def _atlas_oner(self):
        """Ekstre satırı için karşı taraf önerir (en güçlüden zayıfa):
        kural > bekleyen ödeme/virman > açıklamadaki fatura no > IBAN > VKN/TCKN > cari kodu > cari adı,
        cari bulunduysa tutarı tutan açık fatura."""
        self.ensure_one()
        raw_text = self._atlas_text()
        text = normalize_text(raw_text)
        vals = {'atlas_oneri': False}

        rules = self.env['atlas.banka.kural'].search([('company_id', '=', self.company_id.id)])
        if rule := next((r for r in rules if r._match(self, text)), None):
            vals.update(atlas_karsi_hesap_id=rule.account_id.id, atlas_oneri=f'Kural: {rule.name}')
            if rule.partner_id:
                vals['partner_id'] = rule.partner_id.id
            self.write(vals)
            return

        if pending := self._atlas_find_pending_line():
            vals.update(atlas_bekleyen_line_id=pending.id, atlas_oneri=f'Bekleyen kayıt: {pending.move_id.name}')
            if pending.partner_id and not self.partner_id:
                vals['partner_id'] = pending.partner_id.commercial_partner_id.id
            self.write(vals)
            return

        partner, reason, invoice = self.partner_id.commercial_partner_id, 'Cari seçili', self.env['account.move']
        if invoice := self._atlas_find_invoice_in_text(raw_text):
            partner, reason = invoice.commercial_partner_id, f'Açıklamada fatura no: {invoice.name}'
        if not partner:
            partner, reason = self._atlas_find_partner(raw_text, text)
        if partner:
            vals.update(partner_id=partner.id, atlas_oneri=reason)
            if not invoice:
                invoice = self._atlas_find_invoice_by_amount(partner)
                if invoice:
                    vals['atlas_oneri'] = f'{reason}; tutarı tutan fatura: {invoice.name}'
            if invoice:
                vals['atlas_fatura_id'] = invoice.id
        self.write(vals)

    def _atlas_find_pending_line(self):
        """Bu banka hesabından girilmiş, ekstreyle kapanmayı bekleyen aynı tutarlı ödeme/virman satırı."""
        self.ensure_one()
        currency_field = 'amount_residual_currency' if self.journal_id.currency_id else 'amount_residual'
        domain = [
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('account_id.reconcile', '=', True),
            ('account_id.account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash')),
            ('company_id', '=', self.company_id.id),
            (currency_field, '=', self.amount),
            '|', ('payment_id.journal_id', '=', self.journal_id.id), ('atlas_banka_journal_id', '=', self.journal_id.id),
        ]
        already_used = self.search([('atlas_bekleyen_line_id', '!=', False), ('id', '!=', self.id),
                                    ('is_reconciled', '=', False)]).atlas_bekleyen_line_id
        candidates = self.env['account.move.line'].search(domain) - already_used
        if self.partner_id:
            candidates = candidates.sorted(lambda l: l.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id)
        return candidates.sorted(lambda l: abs((l.date - self.date).days))[:1]

    def _atlas_find_invoice_in_text(self, raw_text):
        tokens = set(BELGE_NO_REGEX.findall((raw_text or '').upper()))
        if not tokens:
            return self.env['account.move']
        return self.env['account.move'].search([
            ('name', 'in', list(tokens)),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ], limit=1)

    def _atlas_find_invoice_by_amount(self, partner):
        sign_types = ('out_invoice', 'in_refund') if self.amount > 0 else ('in_invoice', 'out_refund')
        return self.env['account.move'].search([
            ('commercial_partner_id', '=', partner.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', sign_types),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('amount_residual', '=', abs(self.amount)),
        ], order='invoice_date_due, id', limit=1)

    def _atlas_find_partner(self, raw_text, text):
        Partner = self.env['res.partner']
        upper = (raw_text or '').upper()
        ibans = {normalize_iban(m) for m in IBAN_REGEX.findall(upper)}
        if self.account_number:
            ibans.add(normalize_iban(self.account_number))
        if ibans:
            bank = self.env['res.partner.bank'].search([('sanitized_account_number', 'in', list(ibans))], limit=1)
            if bank:
                return bank.partner_id.commercial_partner_id, f'IBAN: {bank.account_number}'
        for number in VKN_REGEX.findall(upper):
            partner = Partner.search(['|', ('vat', '=', number), ('vat', '=', f'TR{number}'),
                                      ('parent_id', '=', False)], limit=1)
            if partner:
                return partner, f'VKN/TCKN: {number}'
        for code in CARI_KODU_REGEX.findall(upper):
            partner = Partner.search([('ref', '=', code), ('atlas_cari_tipi', '!=', False)], limit=1)
            if partner:
                return partner, f'Cari kodu: {code}'
        candidates = Partner.search([('atlas_cari_tipi', '!=', False), ('parent_id', '=', False)])
        best = max(
            (p for p in candidates if len(p.name or '') >= MIN_PARTNER_NAME_LENGTH and normalize_text(p.name) in text),
            key=lambda p: len(p.name), default=None,
        )
        if best:
            return best, f'Cari adı: {best.name}'
        return Partner, False

    # -------------------------------------------------------------------------
    # Eşleştirme
    # -------------------------------------------------------------------------

    @api.onchange('partner_id')
    def _onchange_atlas_partner(self):
        if self.atlas_fatura_id and self.atlas_fatura_id.commercial_partner_id != self.partner_id.commercial_partner_id:
            self.atlas_fatura_id = False

    def action_atlas_eslestir(self):
        for st_line in self.filtered(lambda l: not l.is_reconciled):
            st_line._atlas_eslestir()
        return True

    def action_atlas_geri_al(self):
        self.filtered('is_reconciled').action_undo_reconciliation()
        self.write({'atlas_bekleyen_line_id': False})
        return True

    def _atlas_eslestir(self):
        self.ensure_one()
        to_reconcile = self.env['account.move.line']
        partner = self.partner_id.commercial_partner_id

        if pending := self.atlas_bekleyen_line_id:
            if pending.reconciled:
                raise UserError(self.env._('%s kaydı zaten kapanmış.', pending.move_id.name))
            account, to_reconcile = pending.account_id, pending
            partner = partner or pending.partner_id.commercial_partner_id
        elif self.atlas_karsi_hesap_id:
            account = self.atlas_karsi_hesap_id
            if account.atlas_partner_id:
                partner = account.atlas_partner_id
        elif partner:
            account = self._atlas_partner_account(partner)
            to_reconcile = self._atlas_open_items(partner, account)
        else:
            raise UserError(self.env._('"%s" satırı için cari, karşı hesap veya bekleyen kayıt seçin.', self.payment_ref))

        if partner != self.partner_id:
            self.partner_id = partner
        self.with_context(force_delete=True, skip_readonly_check=True).write({
            'line_ids': [Command.clear()] + [
                Command.create(vals) for vals in self._prepare_move_line_default_vals(counterpart_account_id=account.id)],
        })
        if to_reconcile:
            _liquidity, _suspense, other_lines = self._seek_for_lines()
            (other_lines.filtered(lambda l: l.account_id == account) | to_reconcile).reconcile()

    def _atlas_partner_account(self, partner):
        """Giriş: carinin alacak (120) hesabı, çıkış: borç (320) hesabı; cari tipi gerekirse genişletilir."""
        partner._atlas_add_cari_tipi('alici' if self.amount > 0 else 'satici')
        partner = partner.with_company(self.company_id)
        receivable, payable = partner.property_account_receivable_id, partner.property_account_payable_id
        if self.amount > 0:
            return receivable if receivable.atlas_partner_id or not payable.atlas_partner_id else payable
        return payable if payable.atlas_partner_id or not receivable.atlas_partner_id else receivable

    def _atlas_open_items(self, partner, account):
        """Kapatılacak açık kalemler: seçili fatura önce, sonra vade sırasıyla, tutar dolana kadar."""
        sign = 1 if self.amount > 0 else -1  # girişte borç bakiyeli (fatura) kalemler kapanır
        lines = self.env['account.move.line'].search([
            ('account_id', '=', account.id),
            ('partner_id', 'child_of', partner.id),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '>' if sign > 0 else '<', 0),
        ])
        lines = lines.sorted(lambda l: (l.move_id != self.atlas_fatura_id, l.date_maturity or l.date, l.id))
        remaining = abs(self.amount)
        selected = self.env['account.move.line']
        for line in lines:
            if remaining <= 0:
                break
            selected |= line
            residual = abs(line.amount_residual_currency if line.currency_id == self.currency_id else line.amount_residual)
            remaining -= residual
        return selected
