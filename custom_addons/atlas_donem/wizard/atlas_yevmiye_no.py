from odoo import fields, models
from odoo.exceptions import UserError


class AtlasYevmiyeNoWizard(models.TransientModel):
    """Mali yıl içindeki onaylı fişlere kesin yevmiye madde numarası verir (açılış 1'den başlar)."""
    _name = 'atlas.yevmiye.no.wizard'
    _description = 'Yevmiye Madde Numaralandırma'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    yil = fields.Integer(string='Yıl', required=True, default=lambda self: fields.Date.context_today(self).year)
    kilitle = fields.Boolean(string='Yılı Kilitle', help='Yıl sonuna kadar muhasebe kilit tarihi konur; geçmişe kayıt girilemez.')

    def action_numarala(self):
        self.ensure_one()
        Move = self.env['account.move']
        date_from, date_to = fields.Date.to_date(f'{self.yil}-01-01'), fields.Date.to_date(f'{self.yil}-12-31')
        base = [('company_id', '=', self.company_id.id), ('date', '>=', date_from), ('date', '<=', date_to)]
        drafts = Move.search_count(base + [('state', '=', 'draft')])
        if drafts:
            raise UserError(self.env._('%(yil)s yılında %(adet)s taslak fiş var; önce onaylayın veya silin.', yil=self.yil, adet=drafts))
        order = {'acilis': 0, 'kapanis': 2}
        moves = Move.search(base + [('state', '=', 'posted')]).sorted(
            lambda m: (m.date, order.get(m.atlas_fis_turu, 1), m.name, m.id))
        for number, move in enumerate(moves, start=1):
            if move.atlas_yevmiye_no != number:
                move.atlas_yevmiye_no = number
        if self.kilitle:
            self.company_id.sudo().fiscalyear_lock_date = date_to
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': self.env._('%(yil)s yılı: %(adet)s yevmiye maddesi numaralandı.', yil=self.yil, adet=len(moves)),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
