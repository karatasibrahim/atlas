from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from ..models.tools import account_by_code, create_entry


class AtlasKurDegerlemeWizard(models.TransientModel):
    """Dönem sonu kur değerlemesi (VUK 280).

    Dövizli hesapların (kasa, banka, kredi vb. döviz cinsinden tutulan hesaplar ve dövizli cari hareketler)
    döviz bakiyeleri değerleme günü kuruyla TL'ye çevrilir; kayıtlı TL bakiyesiyle fark 646/656'ya yazılır.
    Kur: değerleme gününe ait (o gün ya da öncesindeki en son) kur kaydı, ör. 31.12 TCMB döviz alış.
    """
    _name = 'atlas.kur.degerleme.wizard'
    _description = 'Kur Değerleme'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Değerleme Tarihi', required=True,
                       default=lambda self: fields.Date.context_today(self).replace(month=12, day=31))
    ters_kayit = fields.Boolean(
        string='Ertesi Gün Ters Kayıt', default=True,
        help='Değerleme farkı ertesi gün ters kayıtla kapatılır; cari açık kalemler bozulmaz ve '
             'tahsil/ödemede gerçekleşen kur farkı normal şekilde oluşur.')
    line_ids = fields.One2many('atlas.kur.degerleme.line', 'wizard_id', string='Değerleme Satırları')
    toplam_kar = fields.Monetary(string='Kur Kârı (646)', compute='_compute_toplam', currency_field='company_currency_id')
    toplam_zarar = fields.Monetary(string='Kur Zararı (656)', compute='_compute_toplam', currency_field='company_currency_id')
    company_currency_id = fields.Many2one(related='company_id.currency_id')

    @api.depends('line_ids.fark')
    def _compute_toplam(self):
        for wizard in self:
            wizard.toplam_kar = sum(f for f in wizard.line_ids.mapped('fark') if f > 0)
            wizard.toplam_zarar = -sum(f for f in wizard.line_ids.mapped('fark') if f < 0)

    def _rate(self, currency):
        """1 birim dövizin şirket para birimi karşılığı; değerleme günü dahil en son kur."""
        rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', currency.id),
            ('company_id', 'in', (self.company_id.root_id.id, False)),
            ('name', '<=', self.date),
        ], order='name desc', limit=1)
        if not rate:
            raise UserError(self.env._('%(currency)s için %(date)s tarihinde veya öncesinde kur yok.',
                                       currency=currency.name, date=self.date))
        return rate.inverse_company_rate, rate.name

    def action_hesapla(self):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        base = [('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'), ('date', '<=', self.date),
                ('currency_id', '!=', company_currency.id)]
        Line = self.env['account.move.line']
        groups = Line._read_group(
            base + ['|', ('account_id.currency_id', 'not in', (False, company_currency.id)),
                    ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable'))],
            ['account_id', 'partner_id', 'currency_id'], ['amount_currency:sum', 'balance:sum'])
        # Dövizli hesapta TL satırlar da (ör. değerleme farkları) bakiyeye dahildir
        tl_on_foreign = {
            (account, partner, currency): balance
            for account, partner, currency, balance in Line._read_group(
                [('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'), ('date', '<=', self.date),
                 ('currency_id', '=', company_currency.id), ('account_id.currency_id', 'not in', (False, company_currency.id))],
                ['account_id', 'partner_id', 'account_id.currency_id'], ['balance:sum'])
        }
        # Cari ayrımı yalnızca alacak/borç hesaplarında; kasa, banka ve diğer döviz hesapları hesap bazında değerlenir
        totals = {}
        for (account, partner, currency), (amount_currency, balance) in [
            ((a, p, c), (amc, bal)) for a, p, c, amc, bal in groups
        ] + [((a, p, c), (0.0, bal)) for (a, p, c), bal in tl_on_foreign.items()]:
            if account.account_type not in ('asset_receivable', 'liability_payable'):
                partner = partner.browse()
            key = (account, partner, currency)
            previous = totals.get(key, (0.0, 0.0))
            totals[key] = (previous[0] + amount_currency, previous[1] + balance)
        vals = []
        for (account, partner, currency), (amount_currency, balance) in totals.items():
            rate, rate_date = self._rate(currency)
            yeni = company_currency.round(amount_currency * rate)
            fark = company_currency.round(yeni - balance)
            if company_currency.is_zero(fark):
                continue
            vals.append(Command.create({
                'account_id': account.id, 'partner_id': partner.id, 'currency_id': currency.id,
                'doviz_bakiye': amount_currency, 'kur': rate, 'kur_tarihi': rate_date,
                'tl_bakiye': balance, 'yeni_tl': yeni, 'fark': fark,
            }))
        self.line_ids = [Command.clear()] + vals
        return self._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}

    def action_olustur(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._('Değerleme farkı yok. Önce "Hesapla" ile kontrol edin.'))
        gain = account_by_code(self.env, self.company_id, '646')
        loss = account_by_code(self.env, self.company_id, '656')
        label = f'Kur değerlemesi {self.date:%d.%m.%Y}'
        lines = []
        for line in self.line_ids:
            name = f'{label} - {line.currency_id.name} kur {line.kur:.4f}'
            lines.append({'account_id': line.account_id.id, 'partner_id': line.partner_id.id,
                          'currency_id': line.currency_id.id, 'amount_currency': 0.0, 'balance': line.fark, 'name': name})
        if self.toplam_kar:
            lines.append({'account_id': gain.id, 'balance': -self.toplam_kar, 'name': label})
        if self.toplam_zarar:
            lines.append({'account_id': loss.id, 'balance': self.toplam_zarar, 'name': label})
        move = create_entry(self.env, self.company_id, self.date, label, lines)
        moves = move
        if self.ters_kayit:
            moves |= move._reverse_moves([{'date': self.date + timedelta(days=1),
                                           'ref': f'{label} - ters kayıt'}], cancel=True)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Kur Değerleme Fişleri'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }


class AtlasKurDegerlemeLine(models.TransientModel):
    _name = 'atlas.kur.degerleme.line'
    _description = 'Kur Değerleme Satırı'

    wizard_id = fields.Many2one('atlas.kur.degerleme.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Hesap', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cari', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Döviz', readonly=True)
    company_currency_id = fields.Many2one(related='wizard_id.company_currency_id')
    doviz_bakiye = fields.Monetary(string='Döviz Bakiyesi', currency_field='currency_id', readonly=True)
    kur = fields.Float(string='Kur', digits=(12, 4), readonly=True)
    kur_tarihi = fields.Date(string='Kur Tarihi', readonly=True)
    tl_bakiye = fields.Monetary(string='Kayıtlı TL', currency_field='company_currency_id', readonly=True)
    yeni_tl = fields.Monetary(string='Değerlenmiş TL', currency_field='company_currency_id', readonly=True)
    fark = fields.Monetary(string='Fark', currency_field='company_currency_id', readonly=True)
