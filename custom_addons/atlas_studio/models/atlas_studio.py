import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import UserError

TR_HARF = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')


def teknik_ad(metin, onek='x_atlas_'):
    """'Teslim Şekli' -> 'x_atlas_teslim_sekli'"""
    metin = (metin or '').translate(TR_HARF)
    metin = unicodedata.normalize('NFKD', metin).encode('ascii', 'ignore').decode().lower()
    metin = re.sub(r'[^a-z0-9]+', '_', metin).strip('_')
    return f'{onek}{metin}'[:55] if metin else ''


class AtlasStudioDegisiklik(models.Model):
    _name = 'atlas.studio.degisiklik'
    _description = 'Studio Özelleştirmesi'
    _order = 'id desc'

    name = fields.Char(string='Özelleştirme', required=True)
    tur = fields.Selection([('alan', 'Alan'), ('model', 'Model / Uygulama')], string='Tür', required=True)
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade')
    alan_id = fields.Many2one('ir.model.fields', string='Alan', ondelete='cascade')
    view_ids = fields.Many2many('ir.ui.view', string='Görünümler')
    menu_ids = fields.Many2many('ir.ui.menu', string='Menüler')
    action_id = fields.Many2one('ir.actions.act_window', string='Eylem', ondelete='set null')
    access_ids = fields.Many2many('ir.access', string='Erişim Hakları')

    def action_geri_al(self):
        """Özelleştirmeyi ve onunla oluşturulan kayıtları kaldırır (veriler de silinir)."""
        for kayit in self:
            kayit.view_ids.unlink()
            kayit.menu_ids.unlink()
            kayit.action_id.unlink()
            kayit.access_ids.unlink()
            if kayit.tur == 'alan' and kayit.alan_id:
                if kayit.alan_id.state != 'manual':
                    raise UserError(self.env._('Yalnızca özel alanlar kaldırılabilir.'))
                kayit.alan_id.unlink()
            elif kayit.tur == 'model' and kayit.model_id:
                if kayit.model_id.state != 'manual':
                    raise UserError(self.env._('Yalnızca özel modeller kaldırılabilir.'))
                kayit.model_id.unlink()
        self.unlink()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_ac(self):
        self.ensure_one()
        if self.action_id:
            return {'type': 'ir.actions.act_window', 'name': self.action_id.name, 'res_model': self.action_id.res_model,
                    'view_mode': self.action_id.view_mode}
        return {'type': 'ir.actions.act_window', 'res_model': self.model_id.model, 'view_mode': 'list,form'}


class IrModel(models.Model):
    _inherit = 'ir.model'

    @api.model
    def _atlas_studio_view(self, model, tur):
        """Modelin birincil (kalıtım olmayan) görünümü."""
        return self.env['ir.ui.view'].search([('model', '=', model), ('type', '=', tur), ('mode', '=', 'primary'),
                                              ('inherit_id', '=', False)], order='priority, id', limit=1)
