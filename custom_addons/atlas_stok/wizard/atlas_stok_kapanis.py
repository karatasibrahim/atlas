from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.atlas_donem.models.tools import YANSITMA_7A, create_entry


class AtlasStokKapanisWizard(models.TransientModel):
    """Aralıklı envanter dönem sonu stok kapanışı.

    Stok değeri (seçili maliyet yöntemiyle) ile stok hesaplarının muhasebe bakiyesi karşılaştırılır; fark
    stok değişim hesabına yazılır (150 → 710, 151/152 → 620, 153 → 621). Üretim yapılıyorsa önce hammadde
    tüketimi kapatılır, üretim giderleri (710/720/730) 7/A ile 151'e yansıtılır ve mamul/yarı mamul tekrar kapatılır.
    """
    _name = 'atlas.stok.kapanis.wizard'
    _description = 'Dönem Sonu Stok Kapanışı'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Kapanış Tarihi', required=True, default=fields.Date.context_today)
    uretim_yansitma = fields.Boolean(
        string='Üretim Giderlerini Yansıt (7/A)', default=True,
        help='710/720/730 üretim giderleri 711/721/731 üzerinden 151 Yarı Mamuller hesabına aktarılır; '
             'böylece mamul maliyeti ve 620 Satılan Mamuller Maliyeti doğru hesaplanır.')

    def _close(self):
        company = self.company_id
        try:
            action = company.with_context(allowed_company_ids=company.ids).action_close_stock_valuation(
                at_date=self.date, auto_post=True, raise_error_if_closed=True)
        except UserError:
            return self.env['account.move']  # kapatılacak fark yok
        return self.env['account.move'].browse(action.get('res_id') or []) if isinstance(action, dict) else self.env['account.move']

    def _transfer_completed_production(self):
        """151'de biriken üretim maliyetinin, eldeki yarı mamul stok değerini aşan kısmını (tamamlanan üretim) 152'ye aktarır."""
        company = self.company_id
        yari = self.env.ref('atlas_stok.categ_yari_mamul', raise_if_not_found=False)
        mamul = self.env.ref('atlas_stok.categ_mamul', raise_if_not_found=False)
        if not (yari and mamul):
            return self.env['account.move']
        account_151 = yari.with_company(company).property_stock_valuation_account_id
        account_152 = mamul.with_company(company).property_stock_valuation_account_id
        balance = sum(self.env['account.move.line'].search([
            ('account_id', '=', account_151.id), ('company_id', '=', company.id),
            ('parent_state', '=', 'posted'), ('date', '<=', self.date)]).mapped('balance'))
        value = company.get_inventory_value(self.date).get(account_151, 0.0)
        amount = company.currency_id.round(balance - value)
        if company.currency_id.is_zero(amount):
            return self.env['account.move']
        label = f'Tamamlanan üretimin mamullere aktarılması {self.date:%d.%m.%Y}'
        return create_entry(self.env, company, self.date, label, [
            {'account_id': account_152.id, 'balance': amount, 'name': label},
            {'account_id': account_151.id, 'balance': -amount, 'name': label},
        ])

    def action_kapat(self):
        self.ensure_one()
        if self.company_id.inventory_valuation != 'periodic':
            raise UserError(self.env._('Stok kapanışı yalnızca aralıklı envanter yönteminde yapılır.'))
        moves = self._close()
        if self.uretim_yansitma:
            wizard = self.env['atlas.yansitma.wizard'].create({'company_id': self.company_id.id, 'date': self.date})
            production = {group for group in YANSITMA_7A if group[2] == '151'}
            amounts = {group: amount for group, amount in wizard._unreflected().items() if group in production}
            if any(not self.company_id.currency_id.is_zero(amount) for amount in amounts.values()):
                moves |= wizard._create_move(groups=production)
            moves |= self._transfer_completed_production()
            moves |= self._close()
        if not moves:
            raise UserError(self.env._('Stok değeri muhasebe kayıtlarıyla uyumlu; kapanış kaydı gerekmedi.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Stok Kapanış Fişleri'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
