from odoo import api, fields, models

from ..services.istemci import VARSAYILAN_MODEL

ON_EK = 'atlas_ai.'


class AtlasAiAyar(models.TransientModel):
    _name = 'atlas.ai.ayar'
    _description = 'Yapay Zekâ Ayarları'

    etkin = fields.Boolean(string='Yapay Zekâ Etkin')
    anahtar = fields.Char(string='Anthropic API Anahtarı')
    model = fields.Char(string='Model', default=VARSAYILAN_MODEL)
    otomatik_oku = fields.Boolean(string='Belgeden Oluşan Kayıtları Otomatik Oku', default=True,
                                  help='Belgeler uygulamasından fatura/masraf/aday oluşturulunca dosya kuyruğa alınıp okunur.')

    _ALANLAR = ('etkin', 'anahtar', 'model', 'otomatik_oku')
    _VARSAYILAN = {'model': VARSAYILAN_MODEL, 'otomatik_oku': '1'}

    @api.model
    def _ayar(self, ad):
        ham = self.env['ir.config_parameter'].sudo().get_str(ON_EK + ad, self._VARSAYILAN.get(ad, ''))
        if self._fields[ad].type == 'boolean':
            return ham in ('1', 'True', 'true')
        return ham or False

    @api.model
    def hazir(self):
        return bool(self._ayar('etkin') and self._ayar('anahtar'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        for ad in self._ALANLAR:
            if ad in fields_list:
                res[ad] = self._ayar(ad)
        return res

    def action_kaydet(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        for ad in self._ALANLAR:
            deger = self[ad]
            ICP.set_str(ON_EK + ad, ('1' if deger else '0') if isinstance(deger, bool) else (deger or ''))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('Yapay zekâ ayarları kaydedildi.'),
                           'next': {'type': 'ir.actions.act_window_close'}}}
