import os

from odoo import api, models
from odoo.fields import Command

SISTEM = ("Bir şirketin belge arşivini düzenleyen asistansın. Belgeyi inceleyip listedeki en uygun klasörü ve etiketleri seç, "
          "içeriği anlatan kısa bir dosya adı (uzantısız, en fazla 60 karakter) ve 1-2 cümlelik Türkçe özet yaz. "
          "Yalnız 'siniflandir' aracını çağır.")


class AtlasBelge(models.Model):
    _name = 'atlas.belge'
    _inherit = ['atlas.belge', 'atlas.ai.okunabilir']

    def _atlas_ai_dosya(self):
        self.ensure_one()
        if not self.dosya:
            from odoo.exceptions import UserError
            raise UserError(self.env._('Belgenin dosyası yok.'))
        return self.dosya.content, self.mimetype or 'application/octet-stream', self.dosya_adi or self.name

    def _atlas_ai_okuma(self):
        klasorler = self.env['atlas.belge.klasor'].search([])
        etiketler = self.env['atlas.belge.etiket'].search([])
        return SISTEM, {'name': 'siniflandir', 'description': 'Belgenin sınıflandırması', 'input_schema': {'type': 'object', 'properties': {
            'klasor': {'type': 'string', 'enum': klasorler.mapped('complete_name')},
            'etiketler': {'type': 'array', 'items': {'type': 'string', 'enum': etiketler.mapped('name') or ['-']}},
            'ad': {'type': 'string'}, 'ozet': {'type': 'string'},
            'cari_vkn': {'type': 'string', 'description': 'Belgedeki karşı tarafın VKN/TCKN numarası (varsa)'},
            'guven': {'type': 'number'}}, 'required': ['klasor', 'guven']}}

    def _atlas_ai_uygula(self, s):
        self.ensure_one()
        vals = {}
        klasor = self.env['atlas.belge.klasor'].search([('complete_name', '=', s.get('klasor'))], limit=1)
        if klasor:
            vals['klasor_id'] = klasor.id
        etiketler = self.env['atlas.belge.etiket'].search([('name', 'in', s.get('etiketler') or [])])
        if etiketler:
            vals['etiket_ids'] = [Command.link(e.id) for e in etiketler]
        if s.get('ad'):
            uzanti = os.path.splitext(self.dosya_adi or self.name or '')[1]
            vals['name'] = s['ad'].strip()[:60] + uzanti
        if s.get('ozet') and not self.aciklama:
            vals['aciklama'] = s['ozet']
        if s.get('cari_vkn') and not self.partner_id:
            vkn = ''.join(c for c in s['cari_vkn'] if c.isdigit())
            cari = self.env['res.partner'].search([('vat', 'in', [vkn, f'TR{vkn}'])], limit=1) if vkn else False
            if cari:
                vals['partner_id'] = cari.id
        if vals:
            self.write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        belgeler = super().create(vals_list)
        gelen = self.env.ref('atlas_ai_belgeler.klasor_gelen_kutusu', raise_if_not_found=False)
        if gelen and self.env['atlas.ai.ayar'].hazir():
            hedef = belgeler.filtered(lambda b: b.klasor_id == gelen and b.dosya and not b.ilgili_kayit)
            if hedef:
                hedef.action_atlas_ai_oku()
        return belgeler
