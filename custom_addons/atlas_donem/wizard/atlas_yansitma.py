from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.tools import YANSITMA_7A, account_balances, account_by_code, create_entry


class AtlasYansitmaWizard(models.TransientModel):
    """7/A gider yansıtma: yansıtılmamış bakiyeler aktarılır, karşılığı yansıtma hesaplarına yazılır.
    Üretim: 710/720/730 → 151 (711/721/731), faaliyet: 750/760/770/780 → 630/631/632/660 (751/761/771/781)."""
    _name = 'atlas.yansitma.wizard'
    _description = '7/A Gider Yansıtma'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Yansıtma Tarihi', required=True, default=fields.Date.context_today,
                       help='Bu tarihe kadar (yıl başından) oluşan yansıtılmamış giderler aktarılır.')
    ozet = fields.Html(string='Özet', compute='_compute_ozet')

    def _unreflected(self):
        """{(gider öneki, yansıtma öneki, hedef öneki): yansıtılmamış tutar}"""
        year_start = self.date.replace(month=1, day=1)
        balances = account_balances(self.env, self.company_id,
                                    [('date', '>=', year_start), ('date', '<=', self.date),
                                     ('move_id.atlas_fis_turu', '!=', 'kapanis')])
        totals = dict.fromkeys(YANSITMA_7A, 0.0)
        for account, balance, _amount_currency in balances:
            code = account.with_company(self.company_id).code or ''
            for group in YANSITMA_7A:
                if code.startswith(group[0]) or code.startswith(group[1]):
                    totals[group] += balance
        return totals

    @api.depends('date', 'company_id')
    def _compute_ozet(self):
        for wizard in self:
            if not wizard.date:
                wizard.ozet = False
                continue
            rows = ''.join(
                f'<tr><td>{gider} → {hedef} / {yansitma}</td><td class="text-end">{tutar:,.2f}</td></tr>'
                for (gider, yansitma, hedef), tutar in wizard._unreflected().items())
            wizard.ozet = f'<table class="table table-sm"><tr><th>Grup</th><th class="text-end">Yansıtılacak</th></tr>{rows}</table>'

    def action_yansit(self):
        self.ensure_one()
        move = self._create_move()
        if not move:
            raise UserError(self.env._('Yansıtılacak gider yok.'))
        return move._get_records_action()

    def _create_move(self, groups=None):
        """Yansıtma fişini oluşturur; groups verilirse yalnızca o (gider, yansıtma, hedef) grupları."""
        self.ensure_one()
        currency = self.company_id.currency_id
        lines = []
        label = f'7/A gider yansıtma {self.date:%d.%m.%Y}'
        for (gider, yansitma, hedef), amount in self._unreflected().items():
            if currency.is_zero(amount) or (groups is not None and (gider, yansitma, hedef) not in groups):
                continue
            lines.append({'account_id': account_by_code(self.env, self.company_id, hedef).id, 'balance': amount, 'name': label})
            lines.append({'account_id': account_by_code(self.env, self.company_id, yansitma).id, 'balance': -amount, 'name': label})
        return create_entry(self.env, self.company_id, self.date, label, lines)
