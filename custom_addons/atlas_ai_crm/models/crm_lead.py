from odoo import models

SISTEM = "Kartvizit fotoğraflarını okuyan bir satış asistanısın. Yalnız kartta yazanı aktar. Yalnız 'kartvizit' aracını çağır."
ARAC = {'name': 'kartvizit', 'description': 'Kartvizitten okunan kişi', 'input_schema': {'type': 'object', 'properties': {
    'ad_soyad': {'type': 'string'}, 'unvan': {'type': 'string'}, 'sirket': {'type': 'string'}, 'eposta': {'type': 'string'},
    'telefon': {'type': 'string'}, 'web': {'type': 'string'}, 'adres': {'type': 'string'}, 'guven': {'type': 'number'}},
    'required': ['guven']}}


class CrmLead(models.Model):
    _name = 'crm.lead'
    _inherit = ['crm.lead', 'atlas.ai.okunabilir']

    def _atlas_ai_okuma(self):
        return SISTEM, ARAC

    def _atlas_ai_uygula(self, s):
        self.ensure_one()
        vals = {}
        for alan, anahtar in (('contact_name', 'ad_soyad'), ('function', 'unvan'), ('partner_name', 'sirket'), ('email_from', 'eposta'),
                              ('phone', 'telefon'), ('website', 'web'), ('street', 'adres')):
            if s.get(anahtar) and not self[alan]:
                vals[alan] = s[anahtar]
        if (not self.name or self.name in ('/', 'Yeni', 'New')) and (s.get('sirket') or s.get('ad_soyad')):
            vals['name'] = s.get('sirket') or s.get('ad_soyad')
        if vals:
            self.write(vals)
