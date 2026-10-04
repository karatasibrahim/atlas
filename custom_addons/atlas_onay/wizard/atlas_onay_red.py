from odoo import fields, models


class AtlasOnayRed(models.TransientModel):
    _name = 'atlas.onay.red'
    _description = 'Onay Talebini Reddet'

    talep_id = fields.Many2one('atlas.onay.talep', required=True, ondelete='cascade')
    neden = fields.Text(string='Red Nedeni', required=True)

    def action_reddet(self):
        self.ensure_one()
        self.talep_id.action_reddet(self.neden)
        return {'type': 'ir.actions.act_window_close'}
