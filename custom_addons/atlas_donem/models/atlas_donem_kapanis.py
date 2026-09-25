from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .tools import YANSITMA_7A, account_balances, account_by_code, create_entry

BILANCO_SINIFLARI = ('1', '2', '3', '4', '5')
GELIR_TABLOSU_KAPANIS = ('690', '691', '692')


class AtlasDonemKapanis(models.Model):
    """Mali yıl kapanışı ve yeni yıl açılışı.

    Sırasıyla: 7 grubu kapanışı, 6 grubunun 690'a devri, 690/691 → 692, 692 → 590/591,
    bilanço hesaplarının kapanış fişi (yıl sonu) ve açılış fişi (yeni yılın ilk günü).
    Kapanış ve açılış fişlerindeki cari/mutabakatlı satırlar birbiriyle eşleştirilir; açık faturalar etkilenmez.
    """
    _name = 'atlas.donem.kapanis'
    _description = 'Dönem Kapanışı'
    _order = 'yil desc'
    _inherit = ['mail.thread']

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    yil = fields.Integer(string='Mali Yıl', required=True, default=lambda self: fields.Date.context_today(self).year - 1)
    date_end = fields.Date(string='Kapanış Tarihi', compute='_compute_dates', store=True)
    date_acilis = fields.Date(string='Açılış Tarihi', compute='_compute_dates', store=True)
    state = fields.Selection([('draft', 'Taslak'), ('done', 'Kapatıldı'), ('cancel', 'Geri Alındı')],
                             default='draft', required=True, readonly=True, tracking=True)
    kilitle = fields.Boolean(string='Kapanıştan Sonra Yılı Kilitle', default=True)
    move_ids = fields.Many2many('account.move', string='Kapanış / Açılış Fişleri', readonly=True, copy=False)
    net_sonuc = fields.Monetary(string='Dönem Net Kârı / Zararı', readonly=True, currency_field='currency_id',
                                help='Pozitif: kâr (590), negatif: zarar (591).')
    currency_id = fields.Many2one(related='company_id.currency_id')

    _yil_unique = models.UniqueIndex("(company_id, yil) WHERE state = 'done'", 'Bu yıl zaten kapatılmış.')

    @api.depends('yil')
    def _compute_name(self):
        for record in self:
            record.name = f'{record.yil} Dönem Kapanışı'

    @api.depends('yil', 'company_id')
    def _compute_dates(self):
        for record in self:
            if not record.yil:
                record.date_end = record.date_acilis = False
                continue
            month, day = int(record.company_id.fiscalyear_last_month or 12), record.company_id.fiscalyear_last_day or 31
            record.date_end = date(record.yil, month, day)
            record.date_acilis = record.date_end + timedelta(days=1)

    # -------------------------------------------------------------------------
    # Kapanış
    # -------------------------------------------------------------------------

    def _code(self, account):
        return account.with_company(self.company_id).code or ''

    def _balances(self, groupby=('account_id',)):
        return account_balances(self.env, self.company_id, [('date', '<=', self.date_end)], groupby)

    def _check_ready(self):
        drafts = self.env['account.move'].search_count([
            ('company_id', '=', self.company_id.id), ('state', '=', 'draft'),
            ('date', '>=', self.date_end.replace(month=1, day=1)), ('date', '<=', self.date_end)])
        if drafts:
            raise UserError(self.env._('Dönemde %s taslak fiş var; önce onaylayın veya silin.', drafts))
        if self.search_count([('company_id', '=', self.company_id.id), ('yil', '=', self.yil),
                              ('state', '=', 'done'), ('id', '!=', self.id)]):
            raise UserError(self.env._('%s yılı zaten kapatılmış.', self.yil))
        currency = self.company_id.currency_id
        unreflected = defaultdict(float)
        for account, balance, _amount_currency in self._balances():
            code = self._code(account)
            for group in YANSITMA_7A:
                if code.startswith(group[0]) or code.startswith(group[1]):
                    unreflected[group[0]] += balance
        pending = [code for code, amount in unreflected.items() if not currency.is_zero(amount)]
        if pending:
            raise UserError(self.env._('Yansıtılmamış 7/A giderleri var (%s). Önce "7/A Gider Yansıtma" yapın.', ', '.join(pending)))

    def action_kapat(self):
        self.ensure_one()
        if self.state == 'done':
            return True
        self._check_ready()
        currency = self.company_id.currency_id
        date_end = self.date_end
        moves = self.env['account.move']
        acc = lambda code: account_by_code(self.env, self.company_id, code)  # noqa: E731

        # 1) 7 grubu kapanışı (yansıtılmış gider hesapları ile yansıtma hesapları karşılıklı kapanır)
        lines = [{'account_id': a.id, 'balance': -b, 'name': '7 grubu hesaplarının kapatılması'}
                 for a, b, _c in self._balances() if self._code(a)[:1] == '7' and not currency.is_zero(b)]
        if lines and not currency.is_zero(sum(l['balance'] for l in lines)):
            raise UserError(self.env._('7 grubu hesapları dengede değil (üretim maliyet hesapları yansıtılmamış olabilir).'))
        moves |= create_entry(self.env, self.company_id, date_end, '7 grubu kapanışı', lines, fis_turu='kapanis')

        # 2) Gelir tablosu hesapları → 690
        lines, total = [], 0.0
        for account, balance, _c in self._balances():
            code = self._code(account)
            if code[:1] == '6' and code[:3] not in GELIR_TABLOSU_KAPANIS and not currency.is_zero(balance):
                lines.append({'account_id': account.id, 'balance': -balance, 'name': 'Gelir tablosu hesaplarının 690\'a devri'})
                total += balance
        if lines:
            lines.append({'account_id': acc('690').id, 'balance': total, 'name': 'Dönem kârı veya zararı'})
        moves |= create_entry(self.env, self.company_id, date_end, 'Gelir tablosu hesaplarının kapatılması', lines, fis_turu='kapanis')

        # 3) 690 + 691 → 692
        by_prefix = defaultdict(float)
        for account, balance, _c in self._balances():
            by_prefix[self._code(account)[:3]] += balance
        lines = []
        for prefix in ('690', '691'):
            if not currency.is_zero(by_prefix[prefix]):
                lines.append({'account_id': acc(prefix).id, 'balance': -by_prefix[prefix], 'name': f'{prefix} hesabının 692\'ye devri'})
        net = by_prefix['690'] + by_prefix['691']
        if lines:
            lines.append({'account_id': acc('692').id, 'balance': net, 'name': 'Dönem net kârı veya zararı'})
        moves |= create_entry(self.env, self.company_id, date_end, 'Dönem net kârının tespiti', lines, fis_turu='kapanis')

        # 4) 692 → 590 (kâr) / 591 (zarar)
        net_692 = net + by_prefix['692']
        if not currency.is_zero(net_692):
            target = acc('590') if net_692 < 0 else acc('591')
            lines = [{'account_id': acc('692').id, 'balance': -net_692, 'name': 'Dönem net kârı/zararının bilançoya aktarılması'},
                     {'account_id': target.id, 'balance': net_692, 'name': 'Dönem net kârı/zararı'}]
            moves |= create_entry(self.env, self.company_id, date_end, 'Dönem net kârı / zararı', lines, fis_turu='kapanis')

        # 5) Bilanço kapanış ve 6) açılış fişleri (hesap + cari + döviz bazında)
        kapanis_lines, acilis_lines = [], []
        for account, partner, line_currency, balance, amount_currency in self._balances(('account_id', 'partner_id', 'currency_id')):
            if self._code(account)[:1] not in BILANCO_SINIFLARI:
                continue
            foreign = line_currency != currency
            if currency.is_zero(balance) and (not foreign or line_currency.is_zero(amount_currency)):
                continue
            common = {'account_id': account.id, 'partner_id': partner.id, 'currency_id': line_currency.id}
            kapanis_lines.append({**common, 'balance': -balance, 'amount_currency': -amount_currency if foreign else -balance,
                                  'name': 'Kapanış'})
            acilis_lines.append({**common, 'balance': balance, 'amount_currency': amount_currency if foreign else balance,
                                 'name': 'Açılış'})
        kapanis = create_entry(self.env, self.company_id, date_end, f'{self.yil} Kapanış Fişi', kapanis_lines, fis_turu='kapanis')
        acilis = create_entry(self.env, self.company_id, self.date_acilis, f'{self.yil + 1} Açılış Fişi', acilis_lines, fis_turu='acilis')
        moves |= kapanis | acilis
        self._reconcile_pairs(kapanis, acilis)

        self.write({'state': 'done', 'move_ids': [fields.Command.set(moves.ids)], 'net_sonuc': -net_692})
        if self.kilitle:
            self.company_id.sudo().fiscalyear_lock_date = date_end
        return True

    @staticmethod
    def _reconcile_pairs(kapanis, acilis):
        """Kapanış ve açılış fişindeki aynı hesap/cari/döviz satırlarını eşleştirir."""
        def key(line):
            return line.account_id, line.partner_id, line.currency_id

        acilis_by_key = {key(line): line for line in acilis.line_ids if line.account_id.reconcile}
        for line in kapanis.line_ids.filtered(lambda l: l.account_id.reconcile):
            pair = acilis_by_key.get(key(line))
            if pair:
                (line | pair).reconcile()

    def action_geri_al(self):
        for record in self.filtered(lambda r: r.state == 'done'):
            company = record.company_id.sudo()
            if company.fiscalyear_lock_date and company.fiscalyear_lock_date >= record.date_end:
                company.fiscalyear_lock_date = False
            record.move_ids.line_ids.remove_move_reconcile()
            posted = record.move_ids.filtered(lambda m: m.state == 'posted')
            posted.button_draft()
            record.move_ids.button_cancel()
            record.state = 'cancel'
        return True

    def action_open_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
        }
