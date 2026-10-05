from markupsafe import Markup, escape

from odoo import models
from odoo.fields import Command

SISTEM = ("Özgeçmişleri (CV) okuyan bir işe alım asistanısın. Yalnız belgede yazanı aktar; uydurma. "
          "Özet en fazla 4 cümle, Türkçe. Yalnız 'aday' aracını çağır.")
ARAC = {'name': 'aday', 'description': 'Özgeçmişten okunan aday bilgisi', 'input_schema': {'type': 'object', 'properties': {
    'ad_soyad': {'type': 'string'}, 'eposta': {'type': 'string'}, 'telefon': {'type': 'string'}, 'linkedin': {'type': 'string'},
    'deneyim_yili': {'type': 'number'}, 'son_pozisyon': {'type': 'string'}, 'egitim': {'type': 'string'},
    'beceriler': {'type': 'array', 'items': {'type': 'string'}, 'description': 'En fazla 10 temel beceri'},
    'ozet': {'type': 'string'}, 'guven': {'type': 'number'}}, 'required': ['ad_soyad', 'guven']}}


class HrApplicant(models.Model):
    _name = 'hr.applicant'
    _inherit = ['hr.applicant', 'atlas.ai.okunabilir']

    def _atlas_ai_okuma(self):
        return SISTEM, ARAC

    def _atlas_ai_uygula(self, s):
        self.ensure_one()
        vals = {}
        if s.get('ad_soyad'):
            vals['partner_name'] = s['ad_soyad']
        for alan, anahtar in (('email_from', 'eposta'), ('partner_phone', 'telefon'), ('linkedin_profile', 'linkedin')):
            if s.get(anahtar) and not self[alan]:
                vals[alan] = s[anahtar]
        Etiket = self.env['hr.applicant.category']
        etiketler = Etiket
        for b in (s.get('beceriler') or [])[:10]:
            etiketler |= Etiket.search([('name', '=ilike', b)], limit=1) or Etiket.create({'name': b[:60]})
        if etiketler:
            vals['categ_ids'] = [Command.link(e.id) for e in etiketler]
        satirlar = [f'<b>{escape(k)}:</b> {escape(v)}' for k, v in (('Son pozisyon', s.get('son_pozisyon')), ('Deneyim', s.get('deneyim_yili') and f"{s['deneyim_yili']} yıl"),
                                                                      ('Eğitim', s.get('egitim')), ('Özet', s.get('ozet'))) if v]
        if satirlar:
            vals['applicant_notes'] = Markup('<p>') + Markup('<br/>').join(Markup(x) for x in satirlar) + Markup('</p>') + (self.applicant_notes or '')
        self.write(vals)
