import difflib
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .metin import normal

_logger = logging.getLogger(__name__)
ATLANAN_ALANLAR = {'id', 'create_date', 'create_uid', 'write_date', 'write_uid', 'display_name', 'active', '__last_update'}


class AtlasVeriModel(models.Model):
    _name = 'atlas.veri.model'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Tekilleştirme Modeli'
    _order = 'name'

    name = fields.Char(string='Ad', required=True)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(related='model_id.model', store=True, string='Model Adı')
    alan = fields.Char(string='Kapsam (Alan)', default='[]', help='Yalnız bu alandaki kayıtlar taranır')
    kosul = fields.Selection([('veya', 'Kurallardan biri uyarsa'), ('ve', 'Kuralların tümü uyarsa')], string='Eşleşme',
                             default='veya', required=True)
    kural_ids = fields.One2many('atlas.veri.kural', 'vmodel_id', string='Tekilleştirme Kuralları')
    kaldirma = fields.Selection([('arsiv', 'Arşivle'), ('sil', 'Sil')], string='Kopyalar', default='arsiv', required=True)
    mod = fields.Selection([('manuel', 'Elle onay'), ('otomatik', 'Otomatik birleştir')], string='Birleştirme', default='manuel',
                           required=True, help='Otomatik: benzerliği %100 olan gruplar taramada kendiliğinden birleştirilir.')
    benzerlik_esigi = fields.Integer(string='Benzerlik Eşiği (%)', default=0, help='Bu değerin altındaki gruplar önerilmez.')
    sirketler_arasi = fields.Boolean(string='Şirketler Arası', help='Farklı şirketlerin kayıtları da eşleştirilir.')
    bildirim_user_ids = fields.Many2many('res.users', string='Bildirim Alacaklar')
    eylem_id = fields.Many2one('ir.actions.server', string='Birleştir Eylemi', readonly=True, copy=False)
    grup_sayisi = fields.Integer(string='Grup', compute='_compute_grup_sayisi')

    def _compute_grup_sayisi(self):
        veri = dict(self.env['atlas.veri.grup']._read_group([('vmodel_id', 'in', self.ids)], ['vmodel_id'], ['__count']))
        for m in self:
            m.grup_sayisi = veri.get(m, 0)

    # ------------------------------------------------------------------ tarama
    def _kayitlar(self):
        Model = self.env[self.model].with_context(active_test=True)
        from odoo.tools.safe_eval import safe_eval
        alan = safe_eval(self.alan or '[]')
        return Model.search(alan)

    def _anahtarlar(self, kayitlar):
        """{kural: {kayıt id: anahtar}}"""
        sonuc = {}
        for kural in self.kural_ids:
            ad = kural.field_id.name
            if ad not in kayitlar._fields:
                continue
            degerler = {}
            for k in kayitlar:
                v = k[ad]
                if isinstance(v, models.BaseModel):
                    v = v.id if v else False
                if v in (False, None, ''):
                    continue
                anahtar = str(v).strip() if kural.eslesme == 'tam' else normal(v)
                if anahtar:
                    if not self.sirketler_arasi and 'company_id' in kayitlar._fields:
                        anahtar = (k.company_id.id, anahtar)
                    degerler[k.id] = anahtar
            sonuc[kural] = degerler
        return sonuc

    def _gruplar(self, kayitlar):
        """Eşleşen kayıt kümeleri (kayıt id listeleri)."""
        anahtarlar = self._anahtarlar(kayitlar)
        if not anahtarlar:
            return []
        if self.kosul == 've':
            birlesik = {}
            ortak = set(kayitlar.ids)
            for d in anahtarlar.values():
                ortak &= set(d)
            for rid in ortak:
                birlesik.setdefault(tuple(anahtarlar[k][rid] for k in anahtarlar), []).append(rid)
            return [ids for ids in birlesik.values() if len(ids) > 1]
        ebeveyn = {}

        def bul(x):
            while ebeveyn.setdefault(x, x) != x:
                ebeveyn[x] = ebeveyn[ebeveyn[x]]
                x = ebeveyn[x]
            return x
        for d in anahtarlar.values():
            kova = {}
            for rid, a in d.items():
                kova.setdefault(a, []).append(rid)
            for ids in kova.values():
                for diger in ids[1:]:
                    ebeveyn[bul(diger)] = bul(ids[0])
        kumeler = {}
        for rid in ebeveyn:
            kumeler.setdefault(bul(rid), []).append(rid)
        return [sorted(ids) for ids in kumeler.values() if len(ids) > 1]

    @staticmethod
    def _benzerlik(adlar):
        if len(adlar) < 2:
            return 100.0
        oranlar = [difflib.SequenceMatcher(None, normal(a), normal(b)).ratio() for i, a in enumerate(adlar) for b in adlar[i + 1:]]
        return round(100.0 * sum(oranlar) / len(oranlar), 1)

    def action_tara(self):
        Grup = self.env['atlas.veri.grup']
        Yoksay = self.env['atlas.veri.yoksay']
        yeni_toplam = 0
        for m in self:
            if m.model not in self.env:
                continue
            kayitlar = m._kayitlar()
            mevcut = {frozenset(g.kayit_ids.mapped('res_id')) for g in Grup.with_context(active_test=False).search([('vmodel_id', '=', m.id)])}
            yoksayilan = {frozenset(map(int, y.anahtar.split(','))) for y in Yoksay.search([('model', '=', m.model)])}
            Model = self.env[m.model]
            for ids in m._gruplar(kayitlar):
                kume = frozenset(ids)
                if kume in mevcut or kume in yoksayilan:
                    continue
                recs = Model.browse(ids)
                benzerlik = self._benzerlik(recs.mapped('display_name'))
                if benzerlik < m.benzerlik_esigi:
                    continue
                grup = Grup.create({'vmodel_id': m.id, 'benzerlik': benzerlik, 'kayit_ids': [(0, 0, {
                    'res_id': r.id, 'ad': r.display_name, 'olusturma': r.create_date, 'guncelleme': r.write_date,
                    'company_id': r.company_id.id if 'company_id' in r._fields else False}) for r in recs]})
                grup._farkli_alanlari_hesapla()
                yeni_toplam += 1
                if m.mod == 'otomatik' and benzerlik >= 100:
                    grup.action_birlestir()
            if yeni_toplam and m.bildirim_user_ids:
                for u in m.bildirim_user_ids:
                    m.activity_schedule('mail.mail_activity_data_todo', user_id=u.id,
                                        summary=self.env._('%s modelinde yeni mükerrer kayıt grupları bulundu', m.name))
        return yeni_toplam

    @api.model
    def _cron_tara(self):
        self.search([]).action_tara()

    def action_gruplar(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Mükerrer Kayıtlar'), 'res_model': 'atlas.veri.grup',
                'view_mode': 'list,form', 'domain': [('vmodel_id', 'in', self.ids)]}

    # ------------------------------------------------------------------ "Birleştir" eylemi
    def action_eylem_ekle(self):
        for m in self.filtered(lambda m: not m.eylem_id):
            m.eylem_id = self.env['ir.actions.server'].sudo().create({
                'name': self.env._('Birleştir'), 'model_id': m.model_id.id, 'binding_model_id': m.model_id.id,
                'binding_view_types': 'list', 'state': 'code',
                'code': "action = env['atlas.veri.birlestir'].eylem_ac(model._name, records.ids)",
                'group_ids': [(6, 0, self.env.ref('base.group_system').ids)]})

    def action_eylem_kaldir(self):
        self.eylem_id.unlink()


class AtlasVeriKural(models.Model):
    _name = 'atlas.veri.kural'
    _description = 'Tekilleştirme Kuralı'
    _order = 'sira, id'

    vmodel_id = fields.Many2one('atlas.veri.model', required=True, ondelete='cascade')
    sira = fields.Integer(default=10)
    field_id = fields.Many2one('ir.model.fields', string='Alan', required=True, ondelete='cascade',
                               domain="[('model_id', '=', parent.model_id), ('store', '=', True), "
                                      "('ttype', 'in', ['char', 'text', 'many2one', 'integer'])]")
    eslesme = fields.Selection([('tam', 'Birebir aynı'), ('aksan', 'Büyük/küçük harf ve aksan duyarsız')], string='Eşleşme',
                               default='aksan', required=True)


class AtlasVeriYoksay(models.Model):
    """Kullanıcının 'mükerrer değil' dediği kümeler tekrar önerilmez."""
    _name = 'atlas.veri.yoksay'
    _description = 'Yoksayılan Mükerrer Grubu'

    model = fields.Char(required=True, index=True)
    anahtar = fields.Char(required=True, help='Sıralı kayıt kimlikleri')


class AtlasVeriGrup(models.Model):
    _name = 'atlas.veri.grup'
    _description = 'Mükerrer Kayıt Grubu'
    _order = 'benzerlik desc, id desc'

    vmodel_id = fields.Many2one('atlas.veri.model', string='Tekilleştirme', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='vmodel_id.model', store=True)
    active = fields.Boolean(default=True)
    benzerlik = fields.Float(string='Benzerlik %', digits=(5, 1))
    farkli_alanlar = fields.Char(string='Farklı Alanlar')
    kayit_ids = fields.One2many('atlas.veri.grup.kayit', 'grup_id', string='Kayıtlar')
    kayit_sayisi = fields.Integer(compute='_compute_kayit_sayisi', string='Kayıt')
    ad = fields.Char(compute='_compute_kayit_sayisi', string='Kayıt Adları')

    def _compute_kayit_sayisi(self):
        for g in self:
            g.kayit_sayisi = len(g.kayit_ids)
            g.ad = ' | '.join(g.kayit_ids.mapped('ad'))[:200]

    def _farkli_alanlari_hesapla(self):
        for g in self:
            recs = g._kayitlar()
            farkli = []
            for ad, f in recs._fields.items():
                if not f.store or ad in ATLANAN_ALANLAR or f.type in ('binary', 'one2many', 'many2many', 'html') or f.compute:
                    continue
                degerler = {str(r[ad].id if isinstance(r[ad], models.BaseModel) else r[ad]) for r in recs if r[ad]}
                if len(degerler) > 1:
                    farkli.append(f.string)
            g.farkli_alanlar = ', '.join(farkli[:12])

    def _kayitlar(self):
        self.ensure_one()
        return self.env[self.model].with_context(active_test=False).browse(self.kayit_ids.mapped('res_id')).exists()

    def action_birlestir(self):
        for g in self:
            ana = g.kayit_ids.filtered('ana')[:1] or g.kayit_ids.sorted(lambda k: (k.olusturma or fields.Datetime.now(), k.res_id))[:1]
            if not ana:
                continue
            Model = self.env[g.model].with_context(active_test=False)
            hedef = Model.browse(ana.res_id).exists()
            kaynaklar = Model.browse((g.kayit_ids - ana).mapped('res_id')).exists()
            if hedef and kaynaklar:
                self.env['atlas.veri.birlestir']._birlestir(hedef, kaynaklar, g.vmodel_id.kaldirma)
            g.active = False
        return True

    def action_yoksay(self):
        for g in self:
            self.env['atlas.veri.yoksay'].create({'model': g.model, 'anahtar': ','.join(map(str, sorted(g.kayit_ids.mapped('res_id'))))})
        self.write({'active': False})


class AtlasVeriGrupKayit(models.Model):
    _name = 'atlas.veri.grup.kayit'
    _description = 'Mükerrer Grup Kaydı'
    _order = 'ana desc, olusturma, id'

    grup_id = fields.Many2one('atlas.veri.grup', required=True, ondelete='cascade', index=True)
    res_id = fields.Many2oneReference(string='Kayıt No', model_field='model', required=True)
    model = fields.Char(related='grup_id.model')
    ad = fields.Char(string='Kayıt')
    ana = fields.Boolean(string='Ana Kayıt')
    olusturma = fields.Datetime(string='Oluşturulma')
    guncelleme = fields.Datetime(string='Güncellenme')
    company_id = fields.Many2one('res.company', string='Şirket')
    kullanim = fields.Integer(string='Kullanım', compute='_compute_kullanim', help='Bu kayda bağlı diğer kayıtların sayısı')

    def _compute_kullanim(self):
        for k in self:
            say = 0
            if k.model in self.env:
                for f in self.env['ir.model.fields'].sudo().search([('relation', '=', k.model), ('ttype', '=', 'many2one'), ('store', '=', True)], limit=60):
                    if f.model in self.env and not self.env[f.model]._abstract and self.env[f.model]._auto:
                        try:
                            say += self.env[f.model].sudo().with_context(active_test=False).search_count([(f.name, '=', k.res_id)])
                        except Exception:  # erişilemeyen/özel modeller
                            continue
            k.kullanim = say

    @api.onchange('ana')
    def _onchange_ana(self):
        if self.ana:
            for diger in self.grup_id.kayit_ids - self:
                diger.ana = False

    def write(self, vals):
        if vals.get('ana'):
            (self.grup_id.kayit_ids - self).filtered('ana').write({'ana': False})
        return super().write(vals)

    def action_kayit_ac(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.model, 'res_id': self.res_id, 'view_mode': 'form'}
