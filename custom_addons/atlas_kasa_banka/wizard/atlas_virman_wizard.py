from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class AtlasVirmanWizard(models.TransientModel):
    """Kasa/banka hesapları arasında para transferi.

    Kasa ayağı doğrudan kasa hesabına yazılır. Banka ayağı transit hesaba (103) yazılır ve
    ilgili bankanın ekstresi içe aktarıldığında eşleştirme ekranında bu kayıtla kapatılır.
    """
    _name = 'atlas.virman.wizard'
    _description = 'Virman'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Tarih', required=True, default=fields.Date.context_today)
    kaynak_journal_id = fields.Many2one(
        'account.journal', string='Çıkan Hesap', required=True, check_company=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")
    hedef_journal_id = fields.Many2one(
        'account.journal', string='Giren Hesap', required=True, check_company=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id), ('id', '!=', kaynak_journal_id)]")
    kaynak_currency_id = fields.Many2one('res.currency', compute='_compute_currencies')
    hedef_currency_id = fields.Many2one('res.currency', compute='_compute_currencies')
    farkli_doviz = fields.Boolean(compute='_compute_currencies')
    amount = fields.Monetary(string='Tutar', required=True, currency_field='kaynak_currency_id')
    hedef_amount = fields.Monetary(
        string='Giren Tutar', currency_field='hedef_currency_id',
        compute='_compute_hedef_amount', store=True, readonly=False,
        help='Farklı para birimli hesaplar arasında (döviz alım/satım) giren hesaba geçen tutar.')
    aciklama = fields.Char(string='Açıklama')
    ref = fields.Char(string='Evrak No')

    @api.depends('kaynak_journal_id', 'hedef_journal_id')
    def _compute_currencies(self):
        for wizard in self:
            company_currency = wizard.company_id.currency_id
            wizard.kaynak_currency_id = wizard.kaynak_journal_id.currency_id or company_currency
            wizard.hedef_currency_id = wizard.hedef_journal_id.currency_id or company_currency
            wizard.farkli_doviz = wizard.kaynak_currency_id != wizard.hedef_currency_id

    @api.depends('amount', 'date', 'kaynak_currency_id', 'hedef_currency_id')
    def _compute_hedef_amount(self):
        for wizard in self:
            if wizard.kaynak_currency_id and wizard.hedef_currency_id:
                wizard.hedef_amount = wizard.kaynak_currency_id._convert(
                    wizard.amount, wizard.hedef_currency_id, wizard.company_id, wizard.date)

    def _leg_account(self, journal):
        if journal.type == 'cash':
            return journal.default_account_id
        transit = self.company_id.transfer_account_id
        if not transit:
            raise UserError(self.env._('Şirkette transit hesap (Transit Fonlar) tanımlı değil.'))
        return transit

    def action_create(self):
        self.ensure_one()
        if self.amount <= 0 or self.hedef_amount <= 0:
            raise UserError(self.env._('Virman tutarı sıfırdan büyük olmalıdır.'))
        company_currency = self.company_id.currency_id
        # TL karşılığı çıkan hesabın tutarından hesaplanır; iki ayak aynı TL tutarıyla dengelenir
        amount_tl = self.kaynak_currency_id._convert(self.amount, company_currency, self.company_id, self.date)
        label = self.aciklama or self.env._('Virman: %(kaynak)s → %(hedef)s',
                                           kaynak=self.kaynak_journal_id.name, hedef=self.hedef_journal_id.name)
        lines = []
        for journal, sign, amount, currency in (
            (self.hedef_journal_id, 1, self.hedef_amount, self.hedef_currency_id),
            (self.kaynak_journal_id, -1, self.amount, self.kaynak_currency_id),
        ):
            account = self._leg_account(journal)
            lines.append(Command.create({
                'name': label,
                'account_id': account.id,
                'currency_id': currency.id,
                'amount_currency': sign * amount,
                'balance': sign * amount_tl,
                'atlas_banka_journal_id': journal.id if journal.type == 'bank' else False,
            }))
        move = self.env['account.move'].with_context(default_atlas_fis_turu='virman').create({
            'move_type': 'entry',
            'atlas_fis_turu': 'virman',
            'date': self.date,
            'ref': self.ref,
            'company_id': self.company_id.id,
            'line_ids': lines,
        })
        move.action_post()
        return move._get_records_action()
