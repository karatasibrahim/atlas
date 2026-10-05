import re

from odoo import fields, models
from odoo.exceptions import UserError


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    state = fields.Selection(selection_add=[('atlas_ai', 'Yapay Zekâyla Alan Doldur')], ondelete={'atlas_ai': 'cascade'})
    atlas_ai_istem = fields.Text(string='Yapay Zekâ Talimatı',
                                 help='Kayıt alanları {alan_adi} biçiminde kullanılabilir, ör. "{name} ürününün {description} '
                                      'açıklamasına göre kategorisini seç".')
    atlas_ai_alan_id = fields.Many2one('ir.model.fields', string='Doldurulacak Alan', ondelete='cascade',
                                       domain="[('model_id', '=', model_id), ('store', '=', True), ('readonly', '=', False), "
                                              "('ttype', 'in', ['char', 'text', 'html', 'integer', 'float', 'monetary', 'boolean', "
                                              "'date', 'selection', 'many2one', 'many2many'])]")

    def _atlas_ai_istem_olustur(self, kayit):
        def degistir(m):
            ad = m.group(1)
            if ad not in kayit._fields:
                return m.group(0)
            deger = kayit[ad]
            if isinstance(deger, models.BaseModel):
                return ', '.join(deger.mapped('display_name'))
            return '' if deger is False else str(deger)
        return re.sub(r'\{([a-z_][a-z0-9_]*)\}', degistir, self.atlas_ai_istem or '')

    def _run_action_atlas_ai_multi(self, eval_context=None):
        if not self.atlas_ai_alan_id or not self.atlas_ai_istem:
            raise UserError(self.env._('Yapay zekâ eyleminde talimat ve doldurulacak alan gerekli.'))
        kayitlar = eval_context.get('records') or eval_context.get('record')
        if kayitlar:
            self.env['atlas.ai.istek'].kuyruga_al(kayitlar, 'eylem', eylem=self)
        return False
