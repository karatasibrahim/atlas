from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from ..models.atlas_studio import teknik_ad

ALAN_TURLERI = [
    ('char', 'Metin'),
    ('text', 'Çok satırlı metin'),
    ('html', 'Biçimli metin'),
    ('integer', 'Tam sayı'),
    ('float', 'Ondalık sayı'),
    ('monetary', 'Para'),
    ('boolean', 'Onay kutusu'),
    ('date', 'Tarih'),
    ('datetime', 'Tarih ve saat'),
    ('selection', 'Seçim listesi'),
    ('many2one', 'Bağlantı (tek kayıt)'),
    ('many2many', 'Etiketler (çok kayıt)'),
    ('binary', 'Dosya'),
]


def secenekleri_ayir(metin):
    """Her satır bir seçenek: 'anahtar:Etiket' veya yalnız 'Etiket'."""
    sonuc = []
    for sira, satir in enumerate(l.strip() for l in (metin or '').splitlines()):
        if not satir:
            continue
        anahtar, _, etiket = satir.partition(':')
        if not etiket:
            etiket, anahtar = anahtar, teknik_ad(anahtar, onek='') or f's{sira}'
        sonuc.append((anahtar.strip(), etiket.strip()))
    return sonuc


class AtlasStudioAlanSatir(models.AbstractModel):
    """Alan tanımı ortak alanları (alan ekleme ve yeni model sihirbazları)."""
    _name = 'atlas.studio.alan.tanim'
    _description = 'Studio Alan Tanımı'

    etiket = fields.Char(string='Alan Etiketi', required=True)
    teknik = fields.Char(string='Teknik Ad', compute='_compute_teknik', store=True, readonly=False)
    tur = fields.Selection(ALAN_TURLERI, string='Tür', required=True, default='char')
    secenekler = fields.Text(string='Seçenekler', help='Her satıra bir seçenek. İsterseniz "anahtar:Etiket" biçiminde yazın.')
    iliski_model_id = fields.Many2one('ir.model', string='Bağlı Model', ondelete='cascade',
                                      domain=[('transient', '=', False)])
    zorunlu = fields.Boolean(string='Zorunlu')
    yardim = fields.Char(string='Açıklama (ipucu)')

    @api.depends('etiket')
    def _compute_teknik(self):
        for satir in self:
            if satir.etiket and not satir.teknik:
                satir.teknik = teknik_ad(satir.etiket)

    def _alan_degerleri(self, model=None):
        """ir.model.fields create değerleri (model: alanın ekleneceği mevcut model; yeni modelde None)."""
        self.ensure_one()
        ad = self.teknik or teknik_ad(self.etiket)
        if not ad.startswith('x_') or not ad.replace('_', '').isalnum() or ad != ad.lower():
            raise ValidationError(self.env._('Teknik ad "x_" ile başlamalı ve yalnızca küçük harf, rakam ve _ içermeli: %s', ad))
        if model and ad in self.env[model]._fields:
            raise ValidationError(self.env._('%(model)s modelinde %(ad)s alanı zaten var.', model=model, ad=ad))
        vals = {'name': ad, 'field_description': self.etiket, 'ttype': self.tur, 'required': self.zorunlu,
                'help': self.yardim or False, 'state': 'manual'}
        if self.tur == 'selection':
            secenekler = secenekleri_ayir(self.secenekler)
            if not secenekler:
                raise ValidationError(self.env._('%s için en az bir seçenek yazın.', self.etiket))
            vals['selection_ids'] = [Command.create({'value': k, 'name': e, 'sequence': i}) for i, (k, e) in enumerate(secenekler)]
        elif self.tur in ('many2one', 'many2many'):
            if not self.iliski_model_id:
                raise ValidationError(self.env._('%s için bağlı modeli seçin.', self.etiket))
            vals['relation'] = self.iliski_model_id.model
            if self.tur == 'many2one':
                vals['on_delete'] = 'set null'
        elif self.tur == 'monetary':
            if not model or 'currency_id' not in self.env[model]._fields:
                raise ValidationError(self.env._('Para alanı için modelde para birimi (currency_id) alanı olmalı; "Ondalık sayı" seçin.'))
            vals['currency_field'] = 'currency_id'
        elif self.tur == 'binary':
            vals['store'] = True
        return vals

    def _gorunum_alani(self, ad, **attrs):
        widget = {'many2many': 'many2many_tags', 'binary': 'binary'}.get(self.tur)
        alan = etree.Element('field', name=ad)
        if widget:
            alan.set('widget', widget)
        for k, v in attrs.items():
            alan.set(k, v)
        return alan


class AtlasStudioAlan(models.TransientModel):
    _name = 'atlas.studio.alan'
    _inherit = 'atlas.studio.alan.tanim'
    _description = 'Studio: Alan Ekle'

    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=[('transient', '=', False), ('abstract', '=', False)])
    form_view_id = fields.Many2one('ir.ui.view', string='Form Görünümü', compute='_compute_gorunumler', store=True,
                                   readonly=False, domain="[('model', '=', model_name), ('type', '=', 'form'), ('mode', '=', 'primary')]")
    model_name = fields.Char(related='model_id.model', string='Model Teknik Adı')
    hedef_alan_id = fields.Many2one('ir.model.fields', string='Konum: şu alanın', ondelete='cascade',
                                    domain="[('model_id', '=', model_id)]",
                                    help='Yeni alan formda bu alanın yanına eklenir. Boşsa formun sonuna ayrı bir bölüm olarak eklenir.')
    konum = fields.Selection([('after', 'Sonrasına'), ('before', 'Öncesine')], string='Konum', default='after', required=True)
    listeye_ekle = fields.Boolean(string='Liste görünümüne ekle', default=True)
    aramaya_ekle = fields.Boolean(string='Aramaya ekle')
    takip = fields.Boolean(string='Değişiklikleri izle (chatter)')
    model_takipli = fields.Boolean(compute='_compute_model_takipli')

    @api.depends('model_id')
    def _compute_gorunumler(self):
        for w in self:
            w.form_view_id = self.env['ir.model']._atlas_studio_view(w.model_id.model, 'form') if w.model_id else False

    @api.depends('model_id')
    def _compute_model_takipli(self):
        for w in self:
            w.model_takipli = bool(w.model_id) and 'message_ids' in self.env[w.model_id.model]._fields

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        model = self.env.context.get('atlas_studio_model')
        if model and 'model_id' in fields_list:
            res['model_id'] = self.env['ir.model']._get_id(model)
        return res

    def _xpath(self, arch, ad):
        """Form görünümünde yeni alanın konacağı yer."""
        hedef = self.hedef_alan_id.name if self.hedef_alan_id else None
        if hedef:
            if arch.xpath(f"//field[@name='{hedef}']"):
                return etree.Element('xpath', expr=f"//field[@name='{hedef}'][not(ancestor::field)]", position=self.konum), None
            raise UserError(self.env._('"%s" alanı form görünümünde bulunmuyor; başka bir konum seçin.', self.hedef_alan_id.field_description))
        hedef_dugum = '//sheet' if arch.xpath('//sheet') else '/form'
        return etree.Element('xpath', expr=hedef_dugum, position='inside'), True

    def action_ekle(self):
        self.ensure_one()
        model = self.model_id.model
        vals = self._alan_degerleri(model)
        if self.takip and self.model_takipli:
            vals['tracking'] = 100
        alan = self.env['ir.model.fields'].create(dict(vals, model_id=self.model_id.id, model=model))
        gorunumler = self.env['ir.ui.view']
        if self.form_view_id:
            arch = etree.fromstring(self.env[model].get_view(self.form_view_id.id, 'form')['arch'])
            xpath, grup_gerek = self._xpath(arch, alan.name)
            dugum = self._gorunum_alani(alan.name)
            if grup_gerek:
                grup = etree.SubElement(xpath, 'group', string=self.env._('Ek Bilgiler'), name=f'{alan.name}_grup')
                grup.append(dugum)
            else:
                xpath.append(dugum)
            gorunumler |= self._miras_gorunum(self.form_view_id, xpath, alan)
        if self.listeye_ekle and self.tur not in ('html', 'binary', 'text'):
            liste = self.env['ir.model']._atlas_studio_view(model, 'list')
            if liste:
                xpath = etree.Element('xpath', expr='/list', position='inside')
                xpath.append(self._gorunum_alani(alan.name, optional='show'))
                gorunumler |= self._miras_gorunum(liste, xpath, alan)
        if self.aramaya_ekle and self.tur in ('char', 'text', 'selection', 'many2one', 'many2many', 'integer'):
            arama = self.env['ir.model']._atlas_studio_view(model, 'search')
            if arama:
                xpath = etree.Element('xpath', expr='/search', position='inside')
                xpath.append(etree.Element('field', name=alan.name))
                gorunumler |= self._miras_gorunum(arama, xpath, alan)
        self.env['atlas.studio.degisiklik'].create({
            'name': self.env._('%(model)s: %(alan)s alanı', model=self.model_id.name, alan=self.etiket), 'tur': 'alan',
            'model_id': self.model_id.id, 'alan_id': alan.id, 'view_ids': [Command.set(gorunumler.ids)],
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _miras_gorunum(self, ana, xpath, alan):
        data = etree.Element('data')
        data.append(xpath)
        return self.env['ir.ui.view'].create({
            'name': f'{ana.model}.atlas.studio.{alan.name}', 'model': ana.model, 'inherit_id': ana.id, 'mode': 'extension',
            'priority': 99, 'arch': etree.tostring(data, encoding='unicode'),
        })
