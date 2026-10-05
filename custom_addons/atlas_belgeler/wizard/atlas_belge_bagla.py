from odoo import api, fields, models


class AtlasBelgeBagla(models.TransientModel):
    """Belgeyi herhangi bir kayda bağlar (araç, çalışan, proje, ürün, cari …)."""
    _name = 'atlas.belge.bagla'
    _description = 'Belgeyi Kayda Bağla'

    belge_ids = fields.Many2many('atlas.belge', string='Belgeler', required=True)
    kayit = fields.Reference(selection='_modeller', string='Kayıt', required=True)
    dosyayi_ekle = fields.Boolean(string='Dosyayı kaydın eklerine de koy', default=True)

    @api.model
    def _modeller(self):
        """Bağlanabilir modeller: belge kurallarının modelleri + köprü modüllerinin eklediği modeller."""
        adlar = set(self.env['atlas.belge.kural'].sudo().search([]).mapped('model')) | set(self._bagli_modeller())
        modeller = self.env['ir.model'].sudo().search([('model', 'in', list(adlar))])
        return sorted(((m.model, m.name) for m in modeller if m.model in self.env), key=lambda x: x[1])

    @api.model
    def _bagli_modeller(self):
        """Köprü modülleri genişletir."""
        return ['res.partner']

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'atlas.belge' and 'belge_ids' in fields_list:
            res['belge_ids'] = [(6, 0, self.env.context.get('active_ids') or [])]
        return res

    def action_bagla(self):
        self.ensure_one()
        for belge in self.belge_ids:
            if self.dosyayi_ekle:
                belge._kayda_ekle(self.kayit)
            else:
                belge.write({'res_model': self.kayit._name, 'res_id': self.kayit.id})
            if 'partner_id' in self.kayit._fields and self.kayit.partner_id and not belge.partner_id:
                belge.partner_id = self.kayit.partner_id
        return {'type': 'ir.actions.act_window_close'}
