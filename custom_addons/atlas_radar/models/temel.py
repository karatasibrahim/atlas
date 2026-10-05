import json

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.siniflandirici import Kural, kelimeler

ONEMLER = [('dusuk', 'Düşük'), ('orta', 'Orta'), ('yuksek', 'Yüksek'), ('kritik', 'Kritik')]


class AtlasRadarDenetim(models.Model):
    """Silinemez ve değiştirilemez denetim günlüğü."""
    _name = 'atlas.radar.denetim'
    _description = 'Radar Denetim Günlüğü'
    _order = 'id desc'
    _rec_name = 'aciklama'

    tarih = fields.Datetime(string='Tarih', default=fields.Datetime.now, readonly=True, index=True)
    kullanici_id = fields.Many2one('res.users', string='Kullanıcı', default=lambda self: self.env.user, readonly=True)
    model = fields.Char(string='Model', readonly=True, index=True)
    res_id = fields.Integer(string='Kayıt No', readonly=True, index=True)
    kayit_adi = fields.Char(string='Kayıt', readonly=True)
    islem = fields.Selection([
        ('olustur', 'Oluşturma'), ('guncelle', 'Güncelleme'), ('sil', 'Silme'), ('tarama', 'Tarama'),
        ('inceleme', 'İnceleme'), ('gorev', 'Görev'), ('ai', 'Yapay Zekâ'), ('ayar', 'Ayar'), ('bildirim', 'Bildirim'),
    ], string='İşlem', readonly=True, index=True)
    aciklama = fields.Char(string='Açıklama', readonly=True)
    degerler = fields.Text(string='Değerler', readonly=True)

    def write(self, vals):
        raise UserError(self.env._('Denetim günlüğü kayıtları değiştirilemez.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_engelle(self):
        raise UserError(self.env._('Denetim günlüğü kayıtları silinemez.'))

    def action_kayda_git(self):
        self.ensure_one()
        if not (self.model and self.res_id and self.model in self.env):
            return False
        kayit = self.env[self.model].browse(self.res_id).exists()
        if not kayit:
            raise UserError(self.env._('Kayıt artık mevcut değil.'))
        return {'type': 'ir.actions.act_window', 'res_model': self.model, 'res_id': kayit.id, 'view_mode': 'form'}

    @api.model
    def kaydet(self, kayit, islem, aciklama, degerler=None):
        return self.sudo().create({
            'model': kayit._name if kayit is not None else False,
            'res_id': kayit.id if kayit is not None and len(kayit) == 1 else 0,
            'kayit_adi': (kayit.display_name or '')[:200] if kayit is not None and len(kayit) == 1 else False,
            'islem': islem,
            'aciklama': (aciklama or '')[:500],
            'degerler': json.dumps(degerler, ensure_ascii=False, default=str, indent=1) if degerler else False,
        })


class AtlasRadarDenetimMixin(models.AbstractModel):
    """Oluşturma, izlenen alanlardaki değişiklik ve silme işlemlerini denetim günlüğüne yazar."""
    _name = 'atlas.radar.denetim.mixin'
    _description = 'Radar Denetim Karışımı'
    _denetim_alanlari = ()

    def _denetim_deger(self, ad):
        alan = self._fields[ad]
        deger = self[ad]
        if alan.type in ('many2one',):
            return deger.display_name or False
        if alan.type in ('many2many', 'one2many'):
            return deger.mapped('display_name')
        if alan.type == 'selection':
            return dict(alan._description_selection(self.env)).get(deger, deger)
        return deger

    @api.model_create_multi
    def create(self, vals_list):
        kayitlar = super().create(vals_list)
        Denetim = self.env['atlas.radar.denetim']
        for k in kayitlar:
            Denetim.kaydet(k, 'olustur', self.env._('%(model)s oluşturuldu', model=self._description))
        return kayitlar

    def write(self, vals):
        izlenen = [a for a in self._denetim_alanlari if a in vals]
        once = {k.id: {a: k._denetim_deger(a) for a in izlenen} for k in self} if izlenen else {}
        sonuc = super().write(vals)
        if izlenen:
            Denetim = self.env['atlas.radar.denetim']
            for k in self:
                fark = {a: [once[k.id][a], k._denetim_deger(a)] for a in izlenen if once[k.id][a] != k._denetim_deger(a)}
                if fark:
                    etiketler = ', '.join(self._fields[a].string for a in fark)
                    Denetim.kaydet(k, 'guncelle', self.env._('Değişen alanlar: %s', etiketler), fark)
        return sonuc

    def unlink(self):
        Denetim = self.env['atlas.radar.denetim']
        for k in self:
            Denetim.kaydet(k, 'sil', self.env._('%(model)s silindi: %(ad)s', model=self._description, ad=k.display_name))
        return super().unlink()


class AtlasRadarKategori(models.Model):
    _name = 'atlas.radar.kategori'
    _description = 'Radar Kategorisi'
    _order = 'sira, name'

    name = fields.Char(string='Kategori', required=True, translate=True)
    kod = fields.Char(string='Kod', required=True)
    sira = fields.Integer(default=10)
    renk = fields.Integer(string='Renk')
    aciklama = fields.Text(string='Açıklama')
    active = fields.Boolean(default=True)

    _kod_benzersiz = models.Constraint('unique(kod)', 'Kategori kodu benzersiz olmalı.')


class AtlasRadarEtiket(models.Model):
    _name = 'atlas.radar.etiket'
    _description = 'Radar Etiketi'
    _order = 'name'

    name = fields.Char(string='Etiket', required=True)
    renk = fields.Integer(string='Renk')

    _ad_benzersiz = models.Constraint('unique(name)', 'Etiket adı benzersiz olmalı.')


class AtlasRadarModul(models.Model):
    """Değişikliklerin etkileyebileceği Atlas/Odoo modülleri ve sorumluları."""
    _name = 'atlas.radar.modul'
    _description = 'Radar ERP Modülü'
    _order = 'sira, name'

    name = fields.Char(string='Modül', required=True)
    teknik_ad = fields.Char(string='Teknik Ad', required=True, help='ör. atlas_ebelge, account, l10n_tr')
    sira = fields.Integer(default=10)
    aciklama = fields.Text(string='Etki Alanı', help='Bu modülde mevzuat değişikliğinden etkilenebilecek işlemler')
    sorumlu_id = fields.Many2one('res.users', string='Sorumlu', domain=[('share', '=', False)],
                                 help='Bu modülü etkileyen değişikliklerde aktivite atanır ve görev sorumlusu olur.')
    kurulu = fields.Boolean(string='Kurulu', compute='_compute_kurulu')
    etki_ids = fields.One2many('atlas.radar.etki', 'modul_id', string='Etkiler')
    acik_etki_sayisi = fields.Integer(string='Açık Etki', compute='_compute_acik_etki_sayisi')
    active = fields.Boolean(default=True)

    _teknik_ad_benzersiz = models.Constraint('unique(teknik_ad)', 'Teknik ad benzersiz olmalı.')

    def _compute_kurulu(self):
        kurulu = set(self.env['ir.module.module'].sudo().search(
            [('name', 'in', self.mapped('teknik_ad')), ('state', '=', 'installed')]).mapped('name'))
        for m in self:
            m.kurulu = m.teknik_ad in kurulu

    def _compute_acik_etki_sayisi(self):
        veri = dict(self.env['atlas.radar.etki']._read_group([('modul_id', 'in', self.ids), ('durum', '=', 'acik')],
                                                             ['modul_id'], ['__count']))
        for m in self:
            m.acik_etki_sayisi = veri.get(m, 0)


class AtlasRadarKural(models.Model):
    _name = 'atlas.radar.kural'
    _inherit = ['atlas.radar.denetim.mixin']
    _description = 'Radar Sınıflandırma Kuralı'
    _order = 'sira, id'
    _denetim_alanlari = ('anahtar_kelimeler', 'haric_kelimeler', 'birlikte_kelimeler', 'yalniz_baslik', 'kategori_id', 'onem', 'modul_ids', 'active', 'agirlik')

    name = fields.Char(string='Kural', required=True)
    sira = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    anahtar_kelimeler = fields.Text(string='Anahtar Kelimeler', required=True,
                                    help='Virgül veya satırla ayırın. Büyük/küçük harf ve Türkçe ekler önemsizdir '
                                         '("e-fatura" → "e-faturaların" de eşleşir). Başlıktaki eşleşme iki kat sayılır.')
    haric_kelimeler = fields.Text(string='Hariç Kelimeler', help='Bunlardan biri geçerse kural uygulanmaz.')
    birlikte_kelimeler = fields.Text(string='Birlikte Geçmeli', help='Doluysa bunlardan en az biri de metinde geçmelidir '
                                                                     '(ör. "teknik kılavuz" yalnız e-belge bağlamında).')
    yalniz_baslik = fields.Boolean(string='Yalnız Başlıkta Ara', help='Detay metnindeki menü/yan liste gibi gürültüden etkilenmemek için.')
    agirlik = fields.Float(string='Ağırlık', default=1.0)
    kategori_id = fields.Many2one('atlas.radar.kategori', string='Kategori')
    onem = fields.Selection(ONEMLER, string='Önem', default='orta', required=True)
    modul_ids = fields.Many2many('atlas.radar.modul', string='Etkilenen Modüller')
    gelistirme_gerekli = fields.Boolean(string='Geliştirme Gerekebilir')
    ayar_gerekli = fields.Boolean(string='Ayar/Parametre Gerekebilir')
    kullanici_aksiyonu = fields.Boolean(string='Kullanıcı Aksiyonu')
    kirici = fields.Boolean(string='Kırıcı Değişiklik', help='Mevcut entegrasyonu bozabilecek değişiklik (şema, zorunlu alan …)')
    kaynak_ids = fields.Many2many('atlas.radar.kaynak', string='Yalnız Bu Kaynaklar', help='Boşsa tüm kaynaklarda uygulanır.')

    @api.model
    def _motor_kurallari(self, kaynak=None):
        sonuc = []
        for k in self.search([]):
            if k.kaynak_ids and kaynak and kaynak not in k.kaynak_ids:
                continue
            sonuc.append(Kural(k.id, kelimeler(k.anahtar_kelimeler), kelimeler(k.haric_kelimeler), k.agirlik,
                               kelimeler(k.birlikte_kelimeler), k.yalniz_baslik, ad=k.name, kategori_id=k.kategori_id.id, onem=k.onem, modul_ids=k.modul_ids.ids,
                               gelistirme=k.gelistirme_gerekli, ayar=k.ayar_gerekli, kullanici=k.kullanici_aksiyonu,
                               kirici=k.kirici))
        return sonuc
