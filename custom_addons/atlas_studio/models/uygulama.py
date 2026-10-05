from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .atlas_studio import teknik_ad
from .editor import OZELLIKLER


class AtlasStudio(models.AbstractModel):
    _inherit = 'atlas.studio'

    # ================================================================== yeni model (13 hazır özellik)
    @api.model
    def ozellik_listesi(self):
        return [{'anahtar': k, 'ad': ad, 'aciklama': ac, 'varsayilan': v} for k, ad, ac, v in OZELLIKLER]

    @api.model
    def model_olustur(self, ad, ozellikler=None, menu_ust_id=False):
        """Yeni özel model; seçilen özelliklere göre alanlar, görünümler, erişim, eylem ve (isteğe bağlı) menü."""
        self._yetki()
        ozellikler = set(ozellikler if ozellikler is not None else [k for k, _a, _c, v in OZELLIKLER if v])
        teknik = teknik_ad(ad, 'x_')
        if not teknik or len(teknik) < 3:
            raise UserError(self.env._('Geçerli bir model adı girin.'))
        aday, i = teknik, 2
        while aday in self.env or self.env['ir.model'].search_count([('model', '=', aday)]):
            aday, i = f'{teknik[:55]}_{i}', i + 1
        teknik = aday
        alanlar = [Command.create({'name': 'x_name', 'field_description': 'Ad', 'ttype': 'char', 'required': True, 'copied': True})]
        if 'use_active' in ozellikler:
            alanlar.append(Command.create({'name': 'x_active', 'field_description': 'Etkin', 'ttype': 'boolean'}))
        if 'use_sequence' in ozellikler:
            alanlar.append(Command.create({'name': 'x_studio_sequence', 'field_description': 'Sıra', 'ttype': 'integer'}))
        if 'use_partner' in ozellikler:
            alanlar += [Command.create({'name': 'x_studio_partner_id', 'field_description': 'Kontak', 'ttype': 'many2one', 'relation': 'res.partner'}),
                        Command.create({'name': 'x_studio_partner_phone', 'field_description': 'Telefon', 'ttype': 'char',
                                        'related': 'x_studio_partner_id.phone', 'readonly': False}),
                        Command.create({'name': 'x_studio_partner_email', 'field_description': 'E-posta', 'ttype': 'char',
                                        'related': 'x_studio_partner_id.email', 'readonly': False})]
        if 'use_responsible' in ozellikler:
            alanlar.append(Command.create({'name': 'x_studio_user_id', 'field_description': 'Sorumlu', 'ttype': 'many2one', 'relation': 'res.users'}))
        if 'use_date' in ozellikler:
            alanlar.append(Command.create({'name': 'x_studio_date', 'field_description': 'Tarih', 'ttype': 'date'}))
        if 'use_double_dates' in ozellikler:
            alanlar += [Command.create({'name': 'x_studio_date_start', 'field_description': 'Başlangıç', 'ttype': 'datetime'}),
                        Command.create({'name': 'x_studio_date_stop', 'field_description': 'Bitiş', 'ttype': 'datetime'})]
        if 'use_image' in ozellikler:
            alanlar.append(Command.create({'name': 'x_studio_image', 'field_description': 'Resim', 'ttype': 'binary'}))
        if 'use_notes' in ozellikler:
            alanlar.append(Command.create({'name': 'x_studio_notes', 'field_description': 'Notlar', 'ttype': 'html'}))
        if 'use_value' in ozellikler:
            alanlar += [Command.create({'name': 'x_studio_currency_id', 'field_description': 'Para Birimi', 'ttype': 'many2one', 'relation': 'res.currency'}),
                        Command.create({'name': 'x_studio_value', 'field_description': 'Değer', 'ttype': 'monetary',
                                        'currency_field': 'x_studio_currency_id'})]
        irm = self._xmlid(self.env['ir.model'].create({
            'name': ad, 'model': teknik, 'state': 'manual', 'field_id': alanlar,
            'is_mail_thread': 'use_mail' in ozellikler, 'is_mail_activity': 'use_mail' in ozellikler,
            'order': 'x_studio_sequence, id' if 'use_sequence' in ozellikler else 'id desc'}), 'model')
        self._xmlid(irm.field_id.filtered(lambda f: f.state == 'manual'), 'alan')
        self._erisim_olustur(irm)
        if 'use_value' in ozellikler:
            self.env['ir.default'].set(teknik, 'x_studio_currency_id', self.env.company.currency_id.id)
        if 'use_active' in ozellikler:
            self.env['ir.default'].set(teknik, 'x_active', True)
        if 'use_responsible' in ozellikler:
            pass  # sorumlu varsayılanı: oluşturan kullanıcı (form görünümünde context ile)
        if 'use_stages' in ozellikler:
            asama = self._alt_model(teknik, 'stage', f'{ad} Aşamaları', [
                {'name': 'x_studio_sequence', 'ttype': 'integer', 'field_description': 'Sıra'},
                {'name': 'x_studio_fold', 'ttype': 'boolean', 'field_description': 'Kanbanda Katla'}])
            self.env['ir.model']._get(asama).order = 'x_studio_sequence, id'
            self._alan_olustur_basit(teknik, 'x_studio_stage_id', 'many2one', 'Aşama', relation=asama, on_delete='restrict')
            ilk = None
            for i, a in enumerate(('Yeni', 'Devam Ediyor', 'Tamamlandı')):
                kayit = self.env[asama].create({'x_name': a, 'x_studio_sequence': i})
                self._xmlid(kayit, 'asama')
                ilk = ilk or kayit
            self.env['ir.default'].set(teknik, 'x_studio_stage_id', ilk.id)
        if 'use_tags' in ozellikler:
            etiket = self._alt_model(teknik, 'tag', f'{ad} Etiketleri', [{'name': 'x_color', 'ttype': 'integer', 'field_description': 'Renk'}])
            self._alan_olustur_basit(teknik, 'x_studio_tag_ids', 'many2many', 'Etiketler', relation=etiket)
        if 'lines' in ozellikler:
            satir = self._alt_model(teknik, 'line', f'{ad} Satırları', [
                {'name': 'x_studio_sequence', 'ttype': 'integer', 'field_description': 'Sıra'},
                {'name': 'x_studio_value', 'ttype': 'float', 'field_description': 'Değer'}])
            ters = f'{teknik}_id'[:60]
            self._alan_olustur_basit(satir, ters, 'many2one', ad, relation=teknik, on_delete='cascade')
            self._alan_olustur_basit(teknik, 'x_studio_line_ids', 'one2many', 'Satırlar', relation=satir, relation_field=ters)
        eylem = self._gorunumleri_kur(teknik, ad, ozellikler)
        menu = False
        if menu_ust_id:
            menu = self._xmlid(self.env['ir.ui.menu'].create({'name': ad, 'parent_id': menu_ust_id,
                                                              'action': f'ir.actions.act_window,{eylem.id}', 'sequence': 50}), 'menu')
        return {'model': teknik, 'action_id': eylem.id, 'menu_id': menu.id if menu else False}

    @api.model
    def _gorunumleri_kur(self, model, ad, ozellikler):
        M = self.env[model]
        View = self.env['ir.ui.view']
        baslik = []
        if 'use_stages' in ozellikler:
            baslik.append('<header><field name="x_studio_stage_id" widget="statusbar" options="{\'clickable\': \'1\'}"/></header>')
        sol = [f for f in ('x_studio_partner_id', 'x_studio_partner_phone', 'x_studio_partner_email') if f in M._fields]
        sag = [f for f in ('x_studio_user_id', 'x_studio_date', 'x_studio_date_start', 'x_studio_date_stop', 'x_studio_value',
                           'x_studio_currency_id', 'x_studio_tag_ids') if f in M._fields]
        def g(alan):
            if alan == 'x_studio_tag_ids':
                return '<field name="x_studio_tag_ids" widget="many2many_tags" options="{\'color_field\': \'x_color\'}"/>'
            if alan == 'x_studio_currency_id':
                return '<field name="x_studio_currency_id" groups="base.group_multi_currency"/>'
            if alan == 'x_studio_user_id':
                return '<field name="x_studio_user_id" widget="many2one_avatar_user"/>'
            return f'<field name="{alan}"/>'
        resim = '<field name="x_studio_image" widget="image" class="oe_avatar"/>' if 'x_studio_image' in M._fields else ''
        arsiv = '<widget name="web_ribbon" title="Arşiv" bg_color="text-bg-danger" invisible="x_active"/>' if 'x_active' in M._fields else ''
        sekmeler = []
        if 'x_studio_line_ids' in M._fields:
            sekmeler.append('<page string="Satırlar" name="satirlar"><field name="x_studio_line_ids"><list editable="bottom">'
                            + ('<field name="x_studio_sequence" widget="handle"/>') + '<field name="x_name"/><field name="x_studio_value"/>'
                            + '</list></field></page>')
        if 'x_studio_notes' in M._fields:
            sekmeler.append('<page string="Notlar" name="notlar"><field name="x_studio_notes"/></page>')
        defter = f'<notebook>{"".join(sekmeler)}</notebook>' if sekmeler else ''
        form = (f'<form>{"".join(baslik)}<sheet>{arsiv}{resim}<div class="oe_title"><h1><field name="x_name" placeholder="{ad}"/></h1></div>'
                f'<group name="studio_group_1"><group name="studio_group_sol">{"".join(g(a) for a in sol)}</group>'
                f'<group name="studio_group_sag">{"".join(g(a) for a in sag)}</group></group>{defter}</sheet>'
                + ('<chatter/>' if 'use_mail' in ozellikler else '') + '</form>')
        liste = ('<list>' + ('<field name="x_studio_sequence" widget="handle"/>' if 'x_studio_sequence' in M._fields else '')
                 + '<field name="x_name"/>' + ''.join(g(a) for a in (sol[:1] + sag[:3])) + '</list>')
        arama = ('<search><field name="x_name"/>' + ''.join(f'<field name="{a}"/>' for a in sol[:1] + [x for x in ('x_studio_user_id',) if x in M._fields])
                 + ('<filter name="arsiv" string="Arşivlenenler" domain="[(\'x_active\', \'=\', False)]"/>' if 'x_active' in M._fields else '')
                 + ('<filter name="g_asama" string="Aşama" context="{\'group_by\': \'x_studio_stage_id\'}"/>' if 'x_studio_stage_id' in M._fields else '')
                 + '</search>')
        turler = {'form': form, 'list': liste, 'search': arama}
        modlar = ['list', 'form']
        if 'use_stages' in ozellikler:
            turler['kanban'] = ('<kanban default_group_by="x_studio_stage_id"><templates><t t-name="card"><field name="x_name" class="fw-bold"/>'
                                + ('<field name="x_studio_tag_ids" widget="many2many_tags" options="{\'color_field\': \'x_color\'}"/>' if 'x_studio_tag_ids' in M._fields else '')
                                + ('<footer><field name="x_studio_user_id" widget="many2one_avatar_user" class="ms-auto"/></footer>' if 'x_studio_user_id' in M._fields else '')
                                + '</t></templates></kanban>')
            modlar = ['kanban'] + modlar
        if 'use_date' in ozellikler:
            turler['calendar'] = f'<calendar date_start="x_studio_date" string="{ad}" mode="month"><field name="x_name"/></calendar>'
            modlar.append('calendar')
        if 'use_double_dates' in ozellikler and 'atlas_gantt' in dict(View._fields['type'].selection):
            turler['atlas_gantt'] = f'<atlas_gantt date_start="x_studio_date_start" date_stop="x_studio_date_stop" string="{ad}"/>'
            modlar.append('atlas_gantt')
        for tur, arch in turler.items():
            self._xmlid(View.create({'name': f'{model} {tur}', 'model': model, 'type': tur, 'arch': arch}), 'gorunum')
        baglam = "{'default_x_studio_user_id': uid}" if 'x_studio_user_id' in M._fields else '{}'
        return self._xmlid(self.env['ir.actions.act_window'].create({
            'name': ad, 'res_model': model, 'view_mode': ','.join(modlar), 'context': baglam,
            'help': f'<p class="o_view_nocontent_smiling_face">İlk kaydı oluşturun</p><p>{ad}</p>'}), 'eylem')

    # ================================================================== uygulama
    @api.model
    def uygulama_olustur(self, ad, simge=False, model_adi='', ozellikler=None):
        """Yeni uygulama: kök menü (simge) + ilk model ve menüsü."""
        self._yetki()
        if not ad:
            raise UserError(self.env._('Uygulama adı gerekli.'))
        kok = self._xmlid(self.env['ir.ui.menu'].create({'name': ad, 'sequence': 90, 'web_icon_data': simge or False}), 'uygulama')
        sonuc = self.model_olustur(model_adi or ad, ozellikler, menu_ust_id=kok.id)
        kok.action = f'ir.actions.act_window,{sonuc["action_id"]}'
        return dict(sonuc, kok_menu_id=kok.id)

    @api.model
    def uygulama_simge(self, menu_id, simge):
        self._yetki()
        self.env['ir.ui.menu'].browse(menu_id).write({'web_icon_data': simge, 'web_icon': False})
        return True

    # ================================================================== menü düzenleyici
    @api.model
    def menu_agaci(self, kok_id):
        self._yetki()
        Menu = self.env['ir.ui.menu']

        def dugum(m):
            return {'id': m.id, 'ad': m.name, 'eylem': bool(m.action),
                    'cocuklar': [dugum(c) for c in Menu.search([('parent_id', '=', m.id)], order='sequence, id')]}
        return dugum(Menu.browse(kok_id))

    @api.model
    def menu_kaydet(self, kok_id, agac):
        """agac: [{'id', 'ad', 'cocuklar': [...]}] — kök menünün altı; sıra ve üst menü bu ağaca göre yazılır."""
        self._yetki()
        Menu = self.env['ir.ui.menu']

        def yaz(dugumler, ust_id):
            for i, d in enumerate(dugumler):
                menu = Menu.browse(d['id'])
                vals = {'parent_id': ust_id, 'sequence': (i + 1) * 10}
                if d.get('ad') and d['ad'] != menu.name:
                    vals['name'] = d['ad']
                menu.write(vals)
                yaz(d.get('cocuklar') or [], menu.id)
        yaz(agac, kok_id)
        return self.menu_agaci(kok_id)

    @api.model
    def menu_olustur(self, ust_id, ad, tur, model=False, ozellikler=None):
        """tur: yeni_model / mevcut_model / ust"""
        self._yetki()
        Menu = self.env['ir.ui.menu']
        vals = {'name': ad, 'parent_id': ust_id, 'sequence': 100}
        if tur == 'yeni_model':
            sonuc = self.model_olustur(ad, ozellikler)
            vals['action'] = f'ir.actions.act_window,{sonuc["action_id"]}'
        elif tur == 'mevcut_model':
            if not model or model not in self.env:
                raise UserError(self.env._('Model seçin.'))
            vals['action'] = f'ir.actions.act_window,{self._varsayilan_eylem(model).id}'
        menu = self._xmlid(Menu.create(vals), 'menu')
        return {'id': menu.id}

    @api.model
    def menu_sil(self, menu_id):
        self._yetki()
        self.env['ir.ui.menu'].browse(menu_id).unlink()
        return True
