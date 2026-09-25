import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def normalize_iban(value):
    return re.sub(r'\s+', '', value or '').upper()


def is_valid_iban(value):
    """ISO 13616 mod-97 kontrolü."""
    number = normalize_iban(value)
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{10,30}', number):
        return False
    rearranged = number[4:] + number[:4]
    return int(''.join(str(int(char, 36)) for char in rearranged)) % 97 == 1


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    atlas_bakiye = fields.Monetary(
        string='Bakiye', compute='_compute_atlas_bakiye', currency_field='atlas_currency_id',
        help='Hesabın kendi para biriminde onaylı bakiye.')
    atlas_bakiye_tl = fields.Monetary(
        string='Bakiye (TL)', compute='_compute_atlas_bakiye', currency_field='atlas_company_currency_id',
        help='Şirket para birimindeki kayıtlı karşılık.')
    atlas_currency_id = fields.Many2one('res.currency', compute='_compute_atlas_bakiye')
    atlas_company_currency_id = fields.Many2one(related='company_id.currency_id', string='Şirket Para Birimi')

    def _compute_atlas_bakiye(self):
        liquidity = self.filtered(lambda j: j.type in ('bank', 'cash') and j.default_account_id)
        totals = {
            account.id: (balance, amount_currency)
            for account, balance, amount_currency in self.env['account.move.line']._read_group(
                [('account_id', 'in', liquidity.default_account_id.ids), ('parent_state', '=', 'posted')],
                ['account_id'], ['balance:sum', 'amount_currency:sum'],
            )
        } if liquidity else {}
        for journal in self:
            currency = journal.currency_id or journal.company_id.currency_id
            balance, amount_currency = totals.get(journal.default_account_id.id, (0.0, 0.0))
            journal.atlas_currency_id = currency
            journal.atlas_bakiye_tl = balance
            journal.atlas_bakiye = amount_currency if journal.currency_id and journal.currency_id != journal.company_id.currency_id else balance

    # -------------------------------------------------------------------------
    # IBAN
    # -------------------------------------------------------------------------

    @api.constrains('bank_account_id')
    def _check_atlas_iban(self):
        for journal in self.filtered(lambda j: j.type == 'bank' and j.bank_account_number):
            number = normalize_iban(journal.bank_account_number)
            if number.startswith('TR') and not (len(number) == 26 and is_valid_iban(number)):
                raise ValidationError(self.env._('Geçersiz IBAN: %s (TR ile başlayan 26 karakter olmalı).', journal.bank_account_number))

    @api.model
    def _atlas_bank_name_from_iban(self, number):
        number = normalize_iban(number)
        if number.startswith('TR') and len(number) >= 9:
            return self.env['atlas.banka'].search([('eft_kodu', '=', number[4:9])], limit=1).name
        return False

    @api.onchange('bank_account_number')
    def _onchange_atlas_iban_bank(self):
        if not self.bank_name and (bank_name := self._atlas_bank_name_from_iban(self.bank_account_number)):
            self.bank_name = bank_name

    # -------------------------------------------------------------------------
    # Kasa: tahsilat/ödeme doğrudan kasa hesabına
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        journals.filtered(lambda j: j.type == 'cash')._atlas_set_direct_cash_payments()
        for journal, vals in zip(journals, vals_list):
            # bank_name, banka hesabı kaydı IBAN'dan sonra oluştuğu için create sırasında kaybolabiliyor
            if journal.bank_account_id and not journal.bank_account_id.bank_name:
                bank_name = vals.get('bank_name') or self._atlas_bank_name_from_iban(journal.bank_account_number)
                if bank_name:
                    journal.bank_account_id.bank_name = bank_name
        return journals

    def _atlas_set_direct_cash_payments(self):
        """Kasadan yapılan tahsilat/ödemeler "bekleyen" hesap yerine doğrudan kasa hesabına yazılsın."""
        for journal in self.filtered('default_account_id'):
            method_lines = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
            method_lines.filtered(lambda l: not l.payment_account_id).payment_account_id = journal.default_account_id

    def action_atlas_hareketler(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kasa_banka.action_atlas_kasa_banka_hareket')
        action['domain'] = [('journal_id', '=', self.id)]
        action['display_name'] = self.env._('Hareketler: %s', self.display_name)
        return action

    def action_atlas_ekstre_yukle(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kasa_banka.action_atlas_banka_ekstre_import')
        action['context'] = {'default_journal_id': self.id}
        return action

    def action_atlas_eslestirme(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kasa_banka.action_atlas_banka_eslestirme')
        action['domain'] = [('journal_id', '=', self.id)]
        return action
