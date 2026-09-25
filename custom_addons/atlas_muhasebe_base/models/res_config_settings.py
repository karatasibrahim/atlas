from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_tcmb_auto = fields.Boolean(related='company_id.atlas_tcmb_auto', readonly=False)
    atlas_tcmb_rate_type = fields.Selection(related='company_id.atlas_tcmb_rate_type', readonly=False)

    def atlas_action_tcmb_update(self):
        self.ensure_one()
        bulletin_date = self.env['res.currency']._atlas_tcmb_update_rates(self.company_id.root_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._('TCMB %s tarihli kurlar güncellendi.', bulletin_date.strftime('%d.%m.%Y')),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
