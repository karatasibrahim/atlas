from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command

from ..models.atlas_studio import teknik_ad


class AtlasStudioModelAlan(models.TransientModel):
    _name = 'atlas.studio.model.alan'
    _inherit = 'atlas.studio.alan.tanim'
    _description = 'Studio: Yeni Model Alanı'
    _order = 'sira, id'

    sihirbaz_id = fields.Many2one('atlas.studio.model', required=True, ondelete='cascade')
    sira = fields.Integer(default=10)
    listede = fields.Boolean(string='Listede', default=True)


class AtlasStudioModel(models.TransientModel):
    _name = 'atlas.studio.model'
    _description = 'Studio: Yeni Model / Uygulama'

    ad = fields.Char(string='Kayıt Türü', required=True, help='ör. Araç Bakım Kaydı')
    teknik = fields.Char(string='Teknik Ad', compute='_compute_teknik', store=True, readonly=False)
    cogul_ad = fields.Char(string='Menü Adı', help='ör. Bakım Kayıtları. Boşsa kayıt türü adı kullanılır.')
    chatter = fields.Boolean(string='Mesajlaşma ve aktiviteler', default=True)
    arsivlenebilir = fields.Boolean(string='Arşivlenebilir', default=True)
    sirket = fields.Boolean(string='Şirket alanı')
    sorumlu = fields.Boolean(string='Sorumlu kullanıcı alanı', default=True)
    yeni_uygulama = fields.Boolean(string='Yeni uygulama olarak menüye ekle', default=True)
    uygulama_adi = fields.Char(string='Uygulama Adı')
    ust_menu_id = fields.Many2one('ir.ui.menu', string='Üst Menü', help='Mevcut bir uygulamanın altına eklemek için seçin.')
    grup_id = fields.Many2one('res.groups', string='Erişebilen Grup', required=True,
                              default=lambda self: self.env.ref('base.group_user'))
    alan_ids = fields.One2many('atlas.studio.model.alan', 'sihirbaz_id', string='Alanlar')

    @api.depends('ad')
    def _compute_teknik(self):
        for w in self:
            if w.ad and not w.teknik:
                w.teknik = teknik_ad(w.ad)

    def _model_degerleri(self):
        ad = self.teknik
        if not ad or not ad.startswith('x_') or not ad.replace('_', '').replace('.', '').isalnum() or ad != ad.lower():
            raise ValidationError(self.env._('Teknik ad "x_" ile başlamalı ve yalnızca küçük harf, rakam, _ içermeli: %s', ad))
        if ad in self.env:
            raise ValidationError(self.env._('%s adlı model zaten var.', ad))
        alanlar = [Command.create({'name': 'x_name', 'field_description': self.env._('Ad'), 'ttype': 'char',
                                   'required': True, 'copied': True})]
        if self.arsivlenebilir:
            alanlar.append(Command.create({'name': 'x_active', 'field_description': self.env._('Etkin'), 'ttype': 'boolean'}))
        if self.sirket:
            alanlar.append(Command.create({'name': 'x_company_id', 'field_description': self.env._('Şirket'), 'ttype': 'many2one',
                                           'relation': 'res.company'}))
        if self.sorumlu:
            alanlar.append(Command.create({'name': 'x_user_id', 'field_description': self.env._('Sorumlu'), 'ttype': 'many2one',
                                           'relation': 'res.users', 'on_delete': 'set null'}))
        gorulen = {'x_name', 'x_active', 'x_company_id', 'x_user_id'}
        for satir in self.alan_ids:
            if satir.tur == 'monetary':
                raise ValidationError(self.env._('Yeni modelde para alanı yerine "Ondalık sayı" kullanın.'))
            vals = satir._alan_degerleri()
            if vals['name'] in gorulen:
                raise ValidationError(self.env._('%s teknik adı iki kez kullanılmış.', vals['name']))
            gorulen.add(vals['name'])
            alanlar.append(Command.create(vals))
        vals = {'name': self.ad, 'model': ad, 'state': 'manual', 'field_id': alanlar, 'order': 'id desc'}
        if self.chatter:
            vals.update(is_mail_thread=True, is_mail_activity=True)
        return vals

    def _gorunumler(self, model):
        satirlar = self.alan_ids.sorted('sira')
        # Form
        form = etree.Element('form')
        sheet = etree.SubElement(form, 'sheet')
        if self.arsivlenebilir:
            etree.SubElement(sheet, 'widget', name='web_ribbon', title=self.env._('Arşivlendi'), bg_color='text-bg-danger',
                             invisible='x_active')
            etree.SubElement(sheet, 'field', name='x_active', invisible='1')
        baslik = etree.SubElement(sheet, 'div', {'class': 'oe_title'})
        h1 = etree.SubElement(baslik, 'h1')
        etree.SubElement(h1, 'field', name='x_name', placeholder=self.ad)
        grup = etree.SubElement(sheet, 'group')
        sol, sag = etree.SubElement(grup, 'group'), etree.SubElement(grup, 'group')
        kisa = [s for s in satirlar if s.tur not in ('html', 'text')]
        for i, satir in enumerate(kisa):
            (sol if i % 2 == 0 else sag).append(satir._gorunum_alani(satir.teknik))
        if self.sorumlu:
            etree.SubElement(sag, 'field', name='x_user_id', widget='many2one_avatar_user')
        if self.sirket:
            etree.SubElement(sag, 'field', name='x_company_id', groups='base.group_multi_company')
        uzun = [s for s in satirlar if s.tur in ('html', 'text')]
        if uzun:
            defter = etree.SubElement(sheet, 'notebook')
            for satir in uzun:
                sayfa = etree.SubElement(defter, 'page', string=satir.etiket, name=satir.teknik)
                etree.SubElement(sayfa, 'field', name=satir.teknik)
        if self.chatter:
            etree.SubElement(form, 'chatter')
        # Liste
        liste = etree.Element('list')
        etree.SubElement(liste, 'field', name='x_name')
        for satir in satirlar.filtered(lambda s: s.listede and s.tur not in ('html', 'text', 'binary')):
            liste.append(satir._gorunum_alani(satir.teknik, optional='show'))
        if self.sorumlu:
            etree.SubElement(liste, 'field', name='x_user_id', widget='many2one_avatar_user', optional='show')
        # Arama
        arama = etree.Element('search')
        etree.SubElement(arama, 'field', name='x_name')
        for satir in satirlar.filtered(lambda s: s.tur in ('char', 'many2one', 'selection')):
            etree.SubElement(arama, 'field', name=satir.teknik)
        if self.sorumlu:
            etree.SubElement(arama, 'filter', name='benim', string=self.env._('Benim'), domain="[('x_user_id', '=', uid)]")
        if self.arsivlenebilir:
            etree.SubElement(arama, 'filter', name='arsiv', string=self.env._('Arşivlenmiş'), domain="[('x_active', '=', False)]")
        View = self.env['ir.ui.view']
        return (View.create({'name': f'{model}.form', 'model': model, 'type': 'form', 'arch': etree.tostring(form, encoding='unicode')})
                | View.create({'name': f'{model}.list', 'model': model, 'type': 'list', 'arch': etree.tostring(liste, encoding='unicode')})
                | View.create({'name': f'{model}.search', 'model': model, 'type': 'search', 'arch': etree.tostring(arama, encoding='unicode')}))

    def action_olustur(self):
        self.ensure_one()
        for satir in self.alan_ids.filtered(lambda s: not s.teknik):
            satir.teknik = teknik_ad(satir.etiket)
        ir_model = self.env['ir.model'].create(self._model_degerleri())
        model = ir_model.model
        if self.arsivlenebilir:
            # varsayılan: yeni kayıt etkin
            self.env['ir.default'].set(model, 'x_active', True)
        gorunumler = self._gorunumler(model)
        menu_adi = self.cogul_ad or self.ad
        eylem = self.env['ir.actions.act_window'].create({
            'name': menu_adi, 'res_model': model, 'view_mode': 'list,form',
            'context': "{'search_default_benim': 1}" if self.sorumlu else '{}',
            'help': f'<p class="o_view_nocontent_smiling_face">{self.env._("İlk kaydı oluşturun")}</p>',
        })
        Menu = self.env['ir.ui.menu']
        menuler = Menu
        if self.yeni_uygulama and not self.ust_menu_id:
            kok = Menu.create({'name': self.uygulama_adi or menu_adi, 'sequence': 200,
                               'web_icon': 'atlas_studio,static/description/icon.png',
                               'group_ids': [Command.set(self.grup_id.ids)]})
            menuler |= kok | Menu.create({'name': menu_adi, 'parent_id': kok.id, 'action': f'ir.actions.act_window,{eylem.id}',
                                          'sequence': 10})
        elif self.ust_menu_id:
            menuler |= Menu.create({'name': menu_adi, 'parent_id': self.ust_menu_id.id,
                                    'action': f'ir.actions.act_window,{eylem.id}', 'sequence': 100})
        erisim = self.env['ir.access'].create({'name': f'{model} {self.grup_id.name}', 'model_id': ir_model.id,
                                               'group_id': self.grup_id.id, 'operation': 'crud'})
        if self.sirket:
            erisim |= self.env['ir.access'].create({
                'name': f'{model} şirket kuralı', 'model_id': ir_model.id, 'operation': 'crud',
                'domain': "['|', ('x_company_id', '=', False), ('x_company_id', 'in', company_ids)]"})
        self.env['atlas.studio.degisiklik'].create({
            'name': self.env._('Yeni model: %s', self.ad), 'tur': 'model', 'model_id': ir_model.id,
            'view_ids': [Command.set(gorunumler.ids)], 'menu_ids': [Command.set(menuler.ids)], 'action_id': eylem.id,
            'access_ids': [Command.set(erisim.ids)],
        })
        return {'type': 'ir.actions.client', 'tag': 'reload', 'params': {'action': eylem.id}}
