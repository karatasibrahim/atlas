import calendar

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.tools import create_entry


class AtlasAmortismanWizard(models.TransientModel):
    """Seçilen ay sonuna kadar ayrılması gereken amortismanları tek fişle kaydeder.
    Aylık kıymetler her ay, yıllık kıymetler yalnızca Aralık ayı sonunda kaydedilir."""
    _name = 'atlas.amortisman.wizard'
    _description = 'Amortisman Kaydı'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Dönem Sonu', required=True, default=lambda self: self._default_date())
    kiymet_ids = fields.Many2many('atlas.sabit.kiymet', string='Sabit Kıymetler',
                                 help='Boşsa tüm aktif sabit kıymetler.')
    ozet = fields.Html(compute='_compute_ozet')

    @api.model
    def _default_date(self):
        today = fields.Date.context_today(self)
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])

    @api.onchange('date')
    def _onchange_date(self):
        if self.date:
            self.date = self.date.replace(day=calendar.monthrange(self.date.year, self.date.month)[1])

    def _items(self):
        kiymetler = self.kiymet_ids or self.env['atlas.sabit.kiymet'].search(
            [('company_id', '=', self.company_id.id), ('state', '=', 'active')])
        result = []
        for kiymet in kiymetler.filtered(lambda k: k.state == 'active'):
            line, amount = kiymet._amortisman_tutari(self.date)
            if line and not kiymet.currency_id.is_zero(amount):
                result.append((kiymet, line, amount))
        return result

    @api.depends('date', 'kiymet_ids', 'company_id')
    def _compute_ozet(self):
        for wizard in self:
            if not wizard.date:
                wizard.ozet = False
                continue
            items = wizard._items()
            rows = ''.join(f'<tr><td>{k.kod} {k.name}</td><td class="text-end">{a:,.2f}</td></tr>' for k, _l, a in items)
            total = sum(a for _k, _l, a in items)
            wizard.ozet = (f'<table class="table table-sm"><tr><th>Sabit Kıymet</th><th class="text-end">Amortisman</th></tr>'
                           f'{rows}<tr><th>Toplam</th><th class="text-end">{total:,.2f}</th></tr></table>')

    def action_kaydet(self):
        self.ensure_one()
        items = self._items()
        if not items:
            raise UserError(self.env._('Bu dönem için ayrılacak amortisman yok.'))
        label = f'Amortisman {self.date:%m/%Y}'
        lines = []
        for kiymet, plan_line, amount in items:
            name = f'{label} - {kiymet.kod} {kiymet.name}'
            lines.append({'account_id': kiymet.gider_account_id.id, 'balance': amount, 'name': name,
                          'analytic_distribution': kiymet.analytic_distribution,
                          'atlas_amortisman_line_id': plan_line.id})
            lines.append({'account_id': kiymet.birikmis_account_id.id, 'balance': -amount, 'name': name})
        move = create_entry(self.env, self.company_id, self.date, label, lines)
        return move._get_records_action()
