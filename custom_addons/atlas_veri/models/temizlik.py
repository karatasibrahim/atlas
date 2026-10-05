import logging

from odoo import api, fields, models

from . import metin

_logger = logging.getLogger(__name__)


class AtlasVeriTemizlik(models.Model):
    _name = 'atlas.veri.temizlik'
    _description = 'Biçim Temizliği'
    _order = 'name'

    name = fields.Char(string='Ad', required=True)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(related='model_id.model', store=True)
    mod = fields.Selection([('manuel', 'Önerileri incele'), ('otomatik', 'Otomatik uygula')], string='Mod', default='manuel', required=True)
    kural_ids = fields.One2many('atlas.veri.temizlik.kural', 'temizlik_id', string='Kurallar')
    oneri_sayisi = fields.Integer(compute='_compute_oneri_sayisi', string='Öneri')

    def _compute_oneri_sayisi(self):
        veri = dict(self.env['atlas.veri.temizlik.kayit']._read_group([('temizlik_id', 'in', self.ids)], ['temizlik_id'], ['__count']))
        for t in self:
            t.oneri_sayisi = veri.get(t, 0)

    def action_tara(self):
        Kayit = self.env['atlas.veri.temizlik.kayit']
        toplam = 0
        for t in self.filtered(lambda t: t.model in self.env):
            Model = self.env[t.model]
            alanlar = t.kural_ids.mapped('field_id')
            mevcut = {(k.res_id, k.field_id.id) for k in Kayit.with_context(active_test=False).search([('temizlik_id', '=', t.id)])}
            for kayit in Model.search([]):
                for alan in alanlar:
                    deger = kayit[alan.name]
                    if not deger or not isinstance(deger, str):
                        continue
                    kurallar = t.kural_ids.filtered(lambda k: k.field_id == alan)
                    yeni = deger
                    for kural in kurallar:
                        yeni = kural._uygula(yeni, kayit)
                    if yeni == deger or (kayit.id, alan.id) in mevcut:
                        continue
                    if t.mod == 'otomatik':
                        kayit.write({alan.name: yeni})
                    else:
                        Kayit.create({'temizlik_id': t.id, 'res_id': kayit.id, 'ad': kayit.display_name, 'field_id': alan.id,
                                      'mevcut': deger, 'onerilen': yeni, 'eylem': ', '.join(kurallar.mapped('eylem_adi'))})
                    toplam += 1
        return toplam

    @api.model
    def _cron_tara(self):
        self.search([]).action_tara()

    def action_oneriler(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Biçim Önerileri'), 'res_model': 'atlas.veri.temizlik.kayit',
                'view_mode': 'list', 'domain': [('temizlik_id', 'in', self.ids)]}


class AtlasVeriTemizlikKural(models.Model):
    _name = 'atlas.veri.temizlik.kural'
    _description = 'Biçim Temizliği Kuralı'
    _order = 'sira, id'

    temizlik_id = fields.Many2one('atlas.veri.temizlik', required=True, ondelete='cascade')
    sira = fields.Integer(default=10)
    field_id = fields.Many2one('ir.model.fields', string='Alan', required=True, ondelete='cascade',
                               domain="[('model_id', '=', parent.model_id), ('store', '=', True), ('ttype', 'in', ['char', 'text'])]")
    eylem = fields.Selection([('bosluk', 'Boşlukları temizle'), ('harf', 'Büyük / küçük harf'), ('telefon', 'Telefonu biçimlendir'),
                              ('html', 'HTML etiketlerini kaldır')], string='Eylem', required=True, default='bosluk')
    bosluk = fields.Selection([('fazla', 'Fazlalık boşluklar'), ('tum', 'Tüm boşluklar')], string='Boşluk', default='fazla')
    harf = fields.Selection([('ilk', 'Kelime Başları Büyük'), ('buyuk', 'TÜMÜ BÜYÜK'), ('kucuk', 'tümü küçük')], string='Harf', default='ilk')
    eylem_adi = fields.Char(compute='_compute_eylem_adi', string='Eylem Adı')

    @api.depends('eylem', 'bosluk', 'harf')
    def _compute_eylem_adi(self):
        for k in self:
            ad = dict(self._fields['eylem'].selection).get(k.eylem, '')
            if k.eylem == 'bosluk':
                ad += f" ({dict(self._fields['bosluk'].selection).get(k.bosluk)})"
            elif k.eylem == 'harf':
                ad += f" ({dict(self._fields['harf'].selection).get(k.harf)})"
            k.eylem_adi = ad

    def _uygula(self, deger, kayit):
        if self.eylem == 'bosluk':
            return metin.bosluk_tum(deger) if self.bosluk == 'tum' else metin.bosluk_fazla(deger)
        if self.eylem == 'harf':
            if '@' in deger or '://' in deger or deger.startswith('www.') or self.field_id.name in ('email', 'email_from', 'website'):
                # e-posta / web adresi: Türkçe harf kuralı uygulanmaz (Info@ → info@, ınfo@ değil)
                return {'ilk': str.lower, 'buyuk': str.upper, 'kucuk': str.lower}[self.harf](deger)
            return {'ilk': metin.tr_baslik, 'buyuk': metin.tr_buyuk, 'kucuk': metin.tr_kucuk}[self.harf](deger)
        if self.eylem == 'html':
            return metin.html_temizle(deger)
        if self.eylem == 'telefon':
            from odoo.addons.phone_validation.tools import phone_validation
            ulke = kayit.country_id if 'country_id' in kayit._fields and kayit.country_id else self.env.company.country_id
            try:
                return phone_validation.phone_format(deger, ulke.code or 'TR', ulke.phone_code or 90, force_format='INTERNATIONAL',
                                                     raise_exception=True)
            except Exception:  # geçersiz numara: dokunma
                return deger
        return deger


class AtlasVeriTemizlikKayit(models.Model):
    _name = 'atlas.veri.temizlik.kayit'
    _description = 'Biçim Önerisi'
    _order = 'id desc'

    temizlik_id = fields.Many2one('atlas.veri.temizlik', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='temizlik_id.model', store=True)
    active = fields.Boolean(default=True)
    res_id = fields.Many2oneReference(string='Kayıt No', model_field='model', required=True)
    ad = fields.Char(string='Kayıt')
    field_id = fields.Many2one('ir.model.fields', string='Alan', ondelete='cascade')
    mevcut = fields.Char(string='Mevcut Değer')
    onerilen = fields.Char(string='Önerilen Değer')
    eylem = fields.Char(string='Eylem')

    def action_uygula(self):
        for k in self:
            kayit = self.env[k.model].browse(k.res_id).exists()
            if kayit and kayit[k.field_id.name] == k.mevcut:
                kayit.write({k.field_id.name: k.onerilen})
        self.unlink()

    def action_yoksay(self):
        self.write({'active': False})
