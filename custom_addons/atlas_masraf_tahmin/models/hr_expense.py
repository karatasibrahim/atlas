import re
import unicodedata
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models

DOLGU = {'ve', 'ile', 'icin', 'bir', 'bu', 'de', 'da', 'the', 'for', 'of', 'masraf', 'fatura', 'fis', 'odeme'}


def _kelimeler(metin):
    metin = (metin or '').replace('İ', 'i').replace('I', 'ı').lower().replace('ı', 'i')
    metin = ''.join(c for c in unicodedata.normalize('NFKD', metin) if not unicodedata.combining(c))
    # Kaba Türkçe kök: ilk 4 harf (yemek / yemeği / yemekleri → "yeme"; ünsüz yumuşaması ve ekler)
    return {k[:4] for k in re.findall(r'[a-z]{3,}', metin) if k not in DOLGU}


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    @api.model
    def _atlas_kategori_tahmin(self, aciklama, company=None, calisan=None):
        """Açıklamaya en çok benzeyen geçmiş masrafların kategorisi (kelime örtüşmesi; aynı çalışana ek ağırlık)."""
        aranan = _kelimeler(aciklama)
        if not aranan:
            return self.env['product.product']
        company = company or self.env.company
        gecmis = self.sudo().search_read([
            ('company_id', '=', company.id), ('product_id', '!=', False),
            ('date', '>=', fields.Date.context_today(self) - timedelta(days=730)),
        ], ['name', 'product_id', 'employee_id'], order='date desc', limit=2000)
        puan = defaultdict(float)
        for g in gecmis:
            ortak = aranan & _kelimeler(g['name'])
            if not ortak:
                continue
            benzerlik = len(ortak) / len(aranan | _kelimeler(g['name']))
            if calisan and g['employee_id'] and g['employee_id'][0] == calisan.id:
                benzerlik *= 1.5
            puan[g['product_id'][0]] += benzerlik
        if not puan:
            return self.env['product.product']
        en_iyi, deger = max(puan.items(), key=lambda x: x[1])
        return self.env['product.product'].browse(en_iyi) if deger >= 0.3 else self.env['product.product']

    @api.onchange('name')
    def _onchange_atlas_kategori_tahmin(self):
        for masraf in self:
            if masraf.name and not masraf.product_id:
                tahmin = self._atlas_kategori_tahmin(masraf.name, masraf.company_id, masraf.employee_id)
                if tahmin:
                    masraf.product_id = tahmin

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name') and not vals.get('product_id'):
                tahmin = self._atlas_kategori_tahmin(vals['name'], self.env['res.company'].browse(vals.get('company_id')) or None,
                                                     self.env['hr.employee'].browse(vals.get('employee_id')) or None)
                if tahmin:
                    vals['product_id'] = tahmin.id
        return super().create(vals_list)
