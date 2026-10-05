from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.birlestirme import ATLANAN_ALANLAR


class AtlasVeriBirlestir(models.TransientModel):
    """Seçili kayıtları tek kayıtta birleştirir (her modelde)."""
    _name = 'atlas.veri.birlestir'
    _description = 'Kayıtları Birleştir'

    res_model = fields.Char(required=True)
    kayit_ids_metin = fields.Char(required=True)
    ana_id = fields.Integer(string='Ana Kayıt')
    ana_secim = fields.Selection(selection='_secenekler', string='Ana Kayıt (korunacak)')
    kaldirma = fields.Selection([('arsiv', 'Arşivle'), ('sil', 'Sil')], string='Diğerleri', default='arsiv', required=True)

    def _secenekler(self):
        model = self.env.context.get('atlas_veri_model') or (self.res_model if self else False)
        ids = self.env.context.get('atlas_veri_ids') or []
        if not model or model not in self.env:
            return []
        return [(str(r.id), f'{r.display_name} (#{r.id})') for r in self.env[model].with_context(active_test=False).browse(ids).exists()]

    @api.model
    def eylem_ac(self, model, ids):
        if len(ids) < 2:
            raise UserError(self.env._('Birleştirmek için en az iki kayıt seçin.'))
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Kayıtları Birleştir'),
                'context': {'default_res_model': model, 'default_kayit_ids_metin': ','.join(map(str, ids)),
                            'default_ana_secim': str(min(ids)), 'atlas_veri_model': model, 'atlas_veri_ids': ids}}

    def action_birlestir(self):
        self.ensure_one()
        Model = self.env[self.res_model].with_context(active_test=False)
        ids = [int(i) for i in self.kayit_ids_metin.split(',') if i]
        hedef = Model.browse(int(self.ana_secim or min(ids))).exists()
        kaynaklar = Model.browse([i for i in ids if i != hedef.id]).exists()
        self._birlestir(hedef, kaynaklar, self.kaldirma)
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': hedef.id, 'view_mode': 'form'}

    @api.model
    def _birlestir(self, hedef, kaynaklar, kaldirma='arsiv'):
        """Kaynaklara olan bağlantıları hedefe taşır, hedefteki boş alanları doldurur, kaynakları arşivler/siler."""
        if not hedef or not kaynaklar:
            return hedef
        if hedef._name == 'res.partner':
            # Odoo cari birleştirmesi (alt kontak, kullanıcı, banka hesabı kontrolleri dahil) — en fazla 3'lü
            Sihirbaz = self.env['base.partner.merge.automatic.wizard'].sudo()
            for i in range(0, len(kaynaklar), 2):
                Sihirbaz._merge((hedef | kaynaklar[i:i + 2]).ids, hedef, extra_checks=False)
            return hedef
        Sihirbaz = self.env['base.partner.merge.automatic.wizard'].sudo()
        kaynak_idler = kaynaklar.ids
        # Önce boş alanlar için değerleri topla (kaynaklar silinmeden)
        degerler = {}
        for ad, f in hedef._fields.items():
            if not f.store or ad in ATLANAN_ALANLAR or f.compute or f.related or f.type in ('one2many', 'many2many') or f.readonly:
                continue
            if not hedef[ad]:
                for k in kaynaklar:
                    if k[ad]:
                        degerler[ad] = k[ad].id if isinstance(k[ad], models.BaseModel) else k[ad]
                        break
        if hedef._name == 'product.template':
            # Son varyantı silinen şablonu Odoo da siler: kalan kaynaklarla devam edilir
            self._urun_varyantlarini_birlestir(hedef, kaynaklar, Sihirbaz)
            self.env.invalidate_all()
            kaynaklar = kaynaklar.exists()
        if kaynaklar:
            Sihirbaz._update_foreign_keys_generic(hedef._name, kaynaklar, hedef)
            Sihirbaz._update_reference_fields_generic(hedef._name, kaynaklar, hedef)
            self.env.invalidate_all()
            kaynaklar = kaynaklar.exists()
            if kaldirma == 'sil' or 'active' not in hedef._fields:
                kaynaklar.unlink()
            else:
                kaynaklar.write({'active': False})
        if degerler:
            try:
                with self.env.cr.savepoint():
                    hedef.write(degerler)
            except Exception:  # benzersizlik vb. kısıtlar — doldurma isteğe bağlı
                pass
        if hasattr(hedef, 'message_post'):
            hedef.message_post(body=self.env._('Birleştirilen kayıtlar: %s', ', '.join(f'#{i}' for i in kaynak_idler)))
        return hedef

    @api.model
    def _urun_varyantlarini_birlestir(self, hedef, kaynaklar, Sihirbaz):
        """Ürün şablonu birleştirmesi: her kaynak varyant hedefteki aynı kombinasyonlu varyanta (yoksa hedefin ilk varyantına)
        birleştirilir, boşalan kaynak varyant silinir. Aksi halde şablon taşınırken varyant benzersizliği bozulur."""
        Varyant = self.env['product.product'].with_context(active_test=False)
        hedef_varyantlar = Varyant.search([('product_tmpl_id', '=', hedef.id)])
        for kaynak in kaynaklar:
            for v in Varyant.search([('product_tmpl_id', '=', kaynak.id)]):
                esi = hedef_varyantlar.filtered(lambda h: h.combination_indices == v.combination_indices)[:1] or hedef_varyantlar[:1]
                if not esi:
                    continue
                Sihirbaz._update_foreign_keys_generic('product.product', v, esi)
                Sihirbaz._update_reference_fields_generic('product.product', v, esi)
                self.env.invalidate_all()
                try:
                    with self.env.cr.savepoint():
                        v.exists().unlink()
                except Exception as e:
                    raise UserError(self.env._('%(urun)s varyantı silinemedi; birleştirme durduruldu: %(hata)s', urun=v.display_name, hata=e)) from e
