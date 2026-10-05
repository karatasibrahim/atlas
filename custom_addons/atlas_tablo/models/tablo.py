import json

from odoo import api, fields, models
from odoo.exceptions import AccessError


class AtlasTablo(models.Model):
    _name = 'atlas.tablo'
    _inherit = ['spreadsheet.mixin', 'mail.thread']
    _description = 'Hesap Tablosu'
    _order = 'write_date desc, id desc'

    name = fields.Char(string='Ad', required=True, default=lambda self: self.env._('Adsız tablo'), tracking=True)
    klasor_id = fields.Many2one('atlas.belge.klasor', string='Klasör', index=True)
    user_id = fields.Many2one('res.users', string='Sahibi', default=lambda self: self.env.user)
    paylasilan_ids = fields.Many2many('res.users', string='Düzenleyebilenler',
                                      help='Boşsa şirketteki herkes açabilir; doluysa yalnız sahibi ve bu kullanıcılar düzenler.')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    aciklama = fields.Text(string='Açıklama')
    active = fields.Boolean(default=True)

    def _yazabilir_mi(self):
        self.ensure_one()
        return not self.paylasilan_ids or self.env.user in (self.user_id | self.paylasilan_ids) or self.env.is_admin()

    def atlas_tablo_ac(self):
        self.ensure_one()
        veri = self.spreadsheet_data or json.dumps(self._empty_spreadsheet_data())
        return {'id': self.id, 'ad': self.name, 'veri': json.loads(veri), 'salt_okunur': not self._yazabilir_mi()}

    def atlas_tablo_kaydet(self, veri, ad=None):
        self.ensure_one()
        if not self._yazabilir_mi():
            raise AccessError(self.env._('Bu tabloyu düzenleme yetkiniz yok.'))
        degerler = {'spreadsheet_data': json.dumps(veri) if not isinstance(veri, str) else veri}
        if ad:
            degerler['name'] = ad
        self.write(degerler)
        return True

    @api.model
    def atlas_tablo_yeni(self, ad, veri=None, klasor_id=False):
        tablo = self.create({'name': ad or self.env._('Adsız tablo'), 'klasor_id': klasor_id,
                             'spreadsheet_data': json.dumps(veri) if veri else False})
        return tablo.id

    def action_ac(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'atlas_tablo.duzenle', 'name': self.name, 'params': {'tablo_id': self.id}}

    @api.model
    def action_yeni(self):
        return self.create({}).action_ac()
