import re

from odoo import fields, models
from odoo.fields import Command

SISTEM = (
    "Türkiye'de düzenlenmiş faturaları (e-Fatura, e-Arşiv, kâğıt fatura) okuyan bir muhasebe asistanısın. "
    "Faturadaki bilgileri olduğu gibi aktar, tahmin etme; bulamadığın alanı boş bırak. Tutarlar sayı olmalı (1.234,56 → 1234.56). "
    "Tarihler YYYY-AA-GG. VKN 10, TCKN 11 hanedir. Yalnız 'fatura' aracını çağır."
)
TARAF = {'type': 'object', 'properties': {'ad': {'type': 'string'}, 'vkn': {'type': 'string', 'description': 'VKN ya da TCKN'},
                                          'vergi_dairesi': {'type': 'string'}, 'adres': {'type': 'string'}}}
ARAC = {
    'name': 'fatura',
    'description': 'Faturadan okunan yapılandırılmış veri',
    'input_schema': {
        'type': 'object',
        'properties': {
            'satici': TARAF, 'alici': TARAF,
            'fatura_no': {'type': 'string'}, 'ettn': {'type': 'string'},
            'fatura_tarihi': {'type': 'string'}, 'vade_tarihi': {'type': 'string'},
            'para_birimi': {'type': 'string', 'description': 'ISO kodu: TRY, USD, EUR'},
            'satirlar': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'aciklama': {'type': 'string'}, 'miktar': {'type': 'number'}, 'birim_fiyat': {'type': 'number'},
                'iskonto_orani': {'type': 'number'}, 'kdv_orani': {'type': 'number'}, 'tutar': {'type': 'number', 'description': 'KDV hariç satır tutarı'}},
                'required': ['aciklama']}},
            'ara_toplam': {'type': 'number'}, 'kdv_toplam': {'type': 'number'}, 'genel_toplam': {'type': 'number'},
            'guven': {'type': 'number', 'description': 'Okumanın doğruluğuna güven, 0-100'},
        },
        'required': ['satirlar', 'guven'],
    },
}


def _vkn(deger):
    return re.sub(r'\D', '', deger or '')


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'atlas.ai.okunabilir']

    def _atlas_ai_okuma(self):
        return SISTEM, ARAC

    def _atlas_ai_cari(self, taraf):
        Partner = self.env['res.partner']
        vkn = _vkn(taraf.get('vkn'))
        if vkn:
            cari = Partner.search([('vat', 'in', [vkn, f'TR{vkn}']), ('company_id', 'in', [False, self.company_id.id])], limit=1)
            if cari:
                return cari
        if taraf.get('ad'):
            cari = Partner.search([('name', '=ilike', taraf['ad'].strip())], limit=1)
            if cari:
                return cari
            # Yeni cari: VKN geçerliyse onunla, değilse VKN'siz oluşturulur
            vals = {'name': taraf['ad'].strip(), 'is_company': True, 'street': taraf.get('adres') or False}
            try:
                with self.env.cr.savepoint():
                    return Partner.create(dict(vals, vat=vkn or False))
            except Exception:  # geçersiz VKN
                return Partner.create(vals)
        return Partner

    def _atlas_ai_vergi(self, oran):
        if oran in (None, ''):
            return self.env['account.tax']
        kullanim = 'purchase' if self.is_purchase_document(include_receipts=True) else 'sale'
        return self.env['account.tax'].search([('type_tax_use', '=', kullanim), ('amount_type', '=', 'percent'),
                                               ('amount', '=', float(oran)), ('company_id', 'in', self.company_id.parent_ids.ids),
                                               ('active', '=', True)], order='sequence, id', limit=1)

    def _atlas_ai_uygula(self, s):
        self.ensure_one()
        if self.state != 'draft':
            return
        vals = {}
        taraf = s.get('satici') if self.is_purchase_document(include_receipts=True) else s.get('alici')
        if not self.partner_id and taraf:
            cari = self._atlas_ai_cari(taraf)
            if cari:
                vals['partner_id'] = cari.id
        if s.get('fatura_no') and not self.ref and self.is_purchase_document(include_receipts=True):
            vals['ref'] = s['fatura_no']
        for alan, anahtar in (('invoice_date', 'fatura_tarihi'), ('invoice_date_due', 'vade_tarihi')):
            if s.get(anahtar) and not self[alan]:
                try:
                    vals[alan] = fields.Date.to_date(s[anahtar][:10])
                except ValueError:
                    pass
        if s.get('para_birimi'):
            para = self.env['res.currency'].with_context(active_test=False).search([('name', '=', s['para_birimi'].upper()[:3])], limit=1)
            if para and para != self.currency_id:
                para.active = True
                vals['currency_id'] = para.id
        if vals:
            self.write(vals)
        if not self.invoice_line_ids:
            satirlar = []
            for st in s.get('satirlar') or []:
                miktar = st.get('miktar') or 1.0
                fiyat = st.get('birim_fiyat')
                if fiyat in (None, 0) and st.get('tutar'):
                    fiyat = st['tutar'] / miktar
                satirlar.append(Command.create({
                    'name': st.get('aciklama') or '/', 'quantity': miktar, 'price_unit': fiyat or 0.0,
                    'discount': st.get('iskonto_orani') or 0.0, 'tax_ids': [Command.set(self._atlas_ai_vergi(st.get('kdv_orani')).ids)],
                }))
            if not satirlar and s.get('genel_toplam'):
                satirlar.append(Command.create({'name': s.get('fatura_no') or self.env._('Fatura toplamı'), 'quantity': 1,
                                                'price_unit': s.get('ara_toplam') or s['genel_toplam']}))
            if satirlar:
                self.write({'invoice_line_ids': satirlar})
        toplam = s.get('genel_toplam')
        if toplam and abs(self.amount_total - toplam) > 0.05:
            self.message_post(body=self.env._('Dikkat: faturadaki genel toplam %(belge)s, oluşan taslak %(taslak)s. Satırları kontrol edin.',
                                              belge=toplam, taslak=self.amount_total))
