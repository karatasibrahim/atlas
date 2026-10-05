from odoo import api, fields, models

from ..services.ai import VARSAYILAN_MODEL
from .temel import ONEMLER

ON_EK = 'atlas_mevzuat.'


class AtlasMevzuatAyar(models.TransientModel):
    """Mevzuat Takip ayarları (ir.config_parameter içinde saklanır; yalnız sistem yöneticisi)."""
    _name = 'atlas.mevzuat.ayar'
    _description = 'Mevzuat Takip Ayarları'

    sorumlu_id = fields.Many2one('res.users', string='Mevzuat Sorumlusu', domain=[('share', '=', False)],
                                 help='Yeni değişikliklerin varsayılan sorumlusu; kaynak hatalarında aktivite alır.')
    ozet_alici_ids = fields.Many2many('res.users', string='Günlük Özet Alıcıları', domain=[('share', '=', False)])
    bildirim_onem = fields.Selection(ONEMLER, string='Aktivite Eşiği', default='yuksek',
                                     help='Bu ve üzerindeki önemde değişikliklerde modül sorumlularına aktivite atanır.')
    otomatik_gorev = fields.Boolean(string='Onayda Görev Aç', default=True)
    proje_id = fields.Many2one('project.project', string='Görev Projesi')
    ai_etkin = fields.Boolean(string='Yapay Zekâ Önerisi')
    ai_otomatik = fields.Boolean(string='Her Yeni Değişiklikte AI Önerisi İste')
    ai_anahtar = fields.Char(string='Anthropic API Anahtarı')
    ai_model = fields.Char(string='Model', default=VARSAYILAN_MODEL)

    _ALANLAR = {
        'sorumlu': ('sorumlu_id', 'res.users'), 'ozet_alicilar': ('ozet_alici_ids', 'res.users'), 'bildirim_onem': ('bildirim_onem', None),
        'otomatik_gorev': ('otomatik_gorev', None), 'proje': ('proje_id', 'project.project'), 'ai_etkin': ('ai_etkin', None),
        'ai_otomatik': ('ai_otomatik', None), 'ai_anahtar': ('ai_anahtar', None), 'ai_model': ('ai_model', None),
    }
    _VARSAYILAN = {'bildirim_onem': 'yuksek', 'otomatik_gorev': '1', 'ai_model': VARSAYILAN_MODEL}

    @api.model
    def _ayar(self, anahtar):
        alan, model = self._ALANLAR[anahtar]
        ham = self.env['ir.config_parameter'].sudo().get_str(ON_EK + anahtar, self._VARSAYILAN.get(anahtar, ''))
        if model:
            ids = [int(i) for i in (ham or '').split(',') if i.strip().isdigit()]
            return self.env[model].sudo().browse(ids).exists()
        if self._fields[alan].type == 'boolean':
            return ham in ('1', 'True', 'true')
        return ham or False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        for anahtar, (alan, model) in self._ALANLAR.items():
            if alan not in fields_list:
                continue
            deger = self._ayar(anahtar)
            if model and self._fields[alan].type == 'many2many':
                res[alan] = [(6, 0, deger.ids)]
            elif model:
                res[alan] = deger[:1].id or False
            else:
                res[alan] = deger
        return res

    def action_kaydet(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        degisen = []
        for anahtar, (alan, model) in self._ALANLAR.items():
            deger = self[alan]
            if model:
                ham = ','.join(str(i) for i in deger.ids)
            elif isinstance(deger, bool):
                ham = '1' if deger else '0'
            else:
                ham = deger or ''
            if (ICP.get_str(ON_EK + anahtar) or '') != ham:
                degisen.append(anahtar)
                ICP.set_str(ON_EK + anahtar, ham)
        if degisen:
            # API anahtarı günlüğe yazılmaz
            self.env['atlas.mevzuat.denetim'].kaydet(None, 'ayar', self.env._('Ayarlar değişti: %s', ', '.join(degisen)))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('Mevzuat Takip ayarları kaydedildi.'),
                           'next': {'type': 'ir.actions.act_window_close'}}}
