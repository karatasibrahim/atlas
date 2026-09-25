from odoo import api, fields, models
from odoo.exceptions import UserError

MAX_RANGE_DAYS = 400


class AtlasTcmbRateWizard(models.TransientModel):
    _name = 'atlas.tcmb.rate.wizard'
    _description = 'TCMB Geçmiş Kur Çekme'

    date_from = fields.Date(string='Başlangıç Tarihi', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Bitiş Tarihi', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company.root_id)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(self.env._('Başlangıç tarihi bitiş tarihinden sonra olamaz.'))
            if (wizard.date_to - wizard.date_from).days > MAX_RANGE_DAYS:
                raise UserError(self.env._('Tek seferde en fazla %s günlük kur çekilebilir.', MAX_RANGE_DAYS))

    def action_fetch(self):
        self.ensure_one()
        dates = self.env['res.currency']._atlas_tcmb_update_range(self.company_id, self.date_from, self.date_to)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._('%s günlük TCMB bülteni işlendi.', len(dates)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
