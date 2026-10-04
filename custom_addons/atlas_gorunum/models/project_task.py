from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    atlas_plan_baslangic = fields.Datetime(string='Planlanan Başlangıç', copy=False,
                                           help='Gantt görünümünde görevin başlangıcı; bitiş olarak son tarih kullanılır.')

    @api.constrains('atlas_plan_baslangic', 'date_deadline')
    def _check_atlas_plan(self):
        for task in self:
            if task.atlas_plan_baslangic and task.date_deadline and task.date_deadline < task.atlas_plan_baslangic:
                raise ValidationError(self.env._('Planlanan başlangıç son tarihten sonra olamaz.'))
