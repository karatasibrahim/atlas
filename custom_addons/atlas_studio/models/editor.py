"""Atlas Studio düzenleyici API'si (istemcideki Studio arayüzü bu metotları çağırır).

Mimari (Enterprise Studio'daki gibi): her ana görünüm için tek bir "Atlas Studio" miras görünümü tutulur; her düzenleme
bu görünüme bir <xpath> işlemi olarak eklenir (atlas.studio.islem). Geri al / yinele işlemleri pasif / aktif yapar.
Studio'nun oluşturduğu her kayıt "atlas_studio_ozel" modülünde bir XML kimliği alır (dışa aktarma için).
"""
import json
import re
import uuid

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

from .atlas_studio import teknik_ad

STUDIO_MODUL = 'atlas_studio_ozel'
STUDIO_ONEK = 'Atlas Studio: '
ADLI_ETIKETLER = ('field', 'page', 'group', 'button', 'filter', 'notebook', 'div', 'widget', 'separator', 'header', 'sheet')
GORUNUM_TURLERI = [
    ('form', 'Form', 'genel'), ('search', 'Arama', 'genel'), ('activity', 'Aktivite', 'genel'),
    ('list', 'Liste', 'coklu'), ('kanban', 'Kanban', 'coklu'), ('atlas_harita', 'Harita', 'coklu'),
    ('calendar', 'Takvim', 'zaman'), ('atlas_gantt', 'Gantt', 'zaman'),
    ('graph', 'Grafik', 'rapor'), ('pivot', 'Pivot', 'rapor'), ('atlas_kohort', 'Kohort', 'rapor'),
]
OZELLIKLER = [
    ('use_partner', 'İletişim bilgileri', 'Kontak, telefon ve e-posta alanları', False),
    ('use_responsible', 'Kullanıcı ataması', 'Her kayda sorumlu atama', False),
    ('use_date', 'Tarih ve Takvim', 'Tarih alanı + takvim görünümü', False),
    ('use_double_dates', 'Tarih aralığı & Gantt', 'Başlangıç/bitiş tarihleri + Gantt görünümü', False),
    ('use_stages', 'Pipeline aşamaları', 'Aşamalar + kanban pipeline', False),
    ('use_tags', 'Etiketler', 'Özel etiketlerle kategorilendirme', False),
    ('use_image', 'Resim', 'Kayda resim ekleme', False),
    ('lines', 'Satırlar', 'Gömülü liste ile detay satırları', False),
    ('use_notes', 'Notlar', 'Not / yorum alanı', False),
    ('use_value', 'Parasal değer', 'Fiyat veya maliyet alanı', False),
    ('use_sequence', 'Özel Sıralama', 'Kanban ve listede elle sıralama', True),
    ('use_mail', 'Mesajlaşma (Chatter)', 'Mesaj, not, aktivite planlama', True),
    ('use_active', 'Arşivleme', 'Kayıt arşivleme', True),
]
ALAN_TURLERI = [
    ('char', 'Metin'), ('text', 'Çok Satırlı Metin'), ('integer', 'Tamsayı'), ('float', 'Ondalık'), ('html', 'HTML'),
    ('monetary', 'Parasal Değer'), ('date', 'Tarih'), ('datetime', 'Tarih Saat'), ('boolean', 'Onay Kutusu'),
    ('selection', 'Seçim'), ('binary', 'Dosya'), ('lines', 'Satırlar'), ('one2many', 'One2Many'), ('many2one', 'Many2One'),
    ('many2many', 'Many2Many'), ('image', 'Görsel'), ('tags', 'Etiketler'), ('priority', 'Öncelik'), ('signature', 'İmza'),
    ('related', 'İlişkili Alan'),
]


class AtlasStudioIslem(models.Model):
    """Studio miras görünümüne uygulanan tek bir düzenleme (geri al / yinele için sıralı)."""
    _name = 'atlas.studio.islem'
    _description = 'Studio Görünüm İşlemi'
    _order = 'studio_view_id, sira, id'

    studio_view_id = fields.Many2one('ir.ui.view', string='Studio Görünümü', required=True, ondelete='cascade', index=True)
    sira = fields.Integer(string='Sıra')
    xml = fields.Text(string='XPath', required=True)
    aciklama = fields.Char(string='Açıklama')
    aktif = fields.Boolean(string='Uygulanıyor', default=True)
    user_id = fields.Many2one('res.users', string='Kullanıcı', default=lambda self: self.env.user)


class AtlasStudio(models.AbstractModel):
    _name = 'atlas.studio'
    _description = 'Atlas Studio'

    # ================================================================== yardımcılar
    @api.model
    def _yetki(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Studio yalnız sistem yöneticilerine açıktır.'))

    @api.model
    def _xmlid(self, kayit, on_ek='kayit'):
        """Studio kaydına dışa aktarılabilir XML kimliği verir."""
        Veri = self.env['ir.model.data'].sudo()
        for k in kayit:
            if not Veri.search_count([('model', '=', k._name), ('res_id', '=', k.id), ('module', '=', STUDIO_MODUL)]):
                Veri.create({'module': STUDIO_MODUL, 'name': f'{on_ek}_{uuid.uuid4().hex[:10]}', 'model': k._name, 'res_id': k.id,
                             'noupdate': True})
        return kayit

    @api.model
    def _teknik(self, model, etiket, onek='x_studio_'):
        ad = teknik_ad(etiket, onek) or f'{onek}alan'
        mevcut = self.env[model]._fields if model in self.env else {}
        aday, i = ad, 2
        while aday in mevcut or self.env['ir.model.fields'].search_count([('model', '=', model), ('name', '=', aday)]):
            aday, i = f'{ad[:52]}_{i}', i + 1
        return aday

    @api.model
    def _ad_alani(self, model):
        M = self.env[model]
        return M._rec_name if M._rec_name in M._fields else ('x_name' if 'x_name' in M._fields else 'display_name')

    # ================================================================== bağlam ve uygulamalar
    @api.model
    def uygulamalar(self):
        self._yetki()
        menuler = self.env['ir.ui.menu'].search([('parent_id', '=', False)], order='sequence, id')
        return [{'id': m.id, 'ad': m.name, 'simge': m.web_icon or False, 'simge_veri': bool(m.web_icon_data),
                 'eylem_id': self._menu_eylemi(m)}
                for m in menuler if m.child_id or m.action]

    @api.model
    def _menu_eylemi(self, menu):
        """Menünün (ya da ilk alt menüsünün) pencere eylemi."""
        if menu.action and menu.action._name == 'ir.actions.act_window' and menu.action.res_model:
            return menu.action.id
        for c in self.env['ir.ui.menu'].search([('parent_id', '=', menu.id)], order='sequence, id'):
            eid = self._menu_eylemi(c)
            if eid:
                return eid
        return False

    @api.model
    def baglam(self, action_id=False, model=False):
        self._yetki()
        eylem = self.env['ir.actions.act_window'].browse(action_id).exists() if action_id else self.env['ir.actions.act_window']
        if eylem and eylem.res_model:
            model = eylem.res_model
        if not model or model not in self.env:
            return {'model': False, 'uygulamalar': self.uygulamalar()}
        if not eylem:
            eylem = self._varsayilan_eylem(model)
        irm = self.env['ir.model']._get(model)
        modlar = [m for m in (eylem.view_mode or '').split(',') if m]
        return {
            'model': model, 'model_adi': irm.name, 'model_id': irm.id, 'ozel_model': irm.state == 'manual',
            'mail': 'message_ids' in self.env[model]._fields, 'aktivite': 'activity_ids' in self.env[model]._fields,
            'eylem': {'id': eylem.id, 'ad': eylem.name, 'yardim': eylem.help or '', 'gruplar': [(g.id, g.display_name) for g in eylem.group_ids],
                      'modlar': modlar},
            'gorunum_turleri': [{'tur': t, 'ad': ad, 'kategori': kat, 'aktif': t in modlar or (t == 'search' and bool(self._ana_gorunum(model, 'search', eylem))),
                                 'varsayilan': bool(modlar) and modlar[0] == t,
                                 'kullanilabilir': self._tur_kullanilabilir(model, t)} for t, ad, kat in GORUNUM_TURLERI],
            'menu': self._menu_yolu(eylem),
            'website': 'website.controller.page' in self.env,
        }

    @api.model
    def _tur_kullanilabilir(self, model, tur):
        if tur == 'activity':
            return 'activity_ids' in self.env[model]._fields
        if tur in ('atlas_gantt', 'atlas_harita', 'atlas_kohort'):
            return tur in dict(self.env['ir.ui.view']._fields['type'].selection)
        return True

    @api.model
    def _menu_yolu(self, eylem):
        menu = self.env['ir.ui.menu'].search([('action', '=', f'ir.actions.act_window,{eylem.id}')], limit=1)
        kok = menu
        while kok.parent_id:
            kok = kok.parent_id
        return {'id': menu.id, 'ad': menu.name or eylem.name, 'kok_id': kok.id, 'kok_ad': kok.name or ''}

    @api.model
    def _varsayilan_eylem(self, model):
        eylem = self.env['ir.actions.act_window'].search([('res_model', '=', model)], order='id', limit=1)
        if not eylem:
            eylem = self._xmlid(self.env['ir.actions.act_window'].create({
                'name': self.env['ir.model']._get(model).name, 'res_model': model, 'view_mode': 'list,form'}), 'eylem')
        return eylem

    @api.model
    def eylem_kaydet(self, action_id, degerler):
        """Görünümler sekmesinin sol paneli: başlık, boş liste mesajı, grup kısıtı."""
        self._yetki()
        eylem = self.env['ir.actions.act_window'].browse(action_id)
        yaz = {}
        if 'ad' in degerler:
            yaz['name'] = degerler['ad']
        if 'yardim' in degerler:
            yaz['help'] = degerler['yardim']
        if 'gruplar' in degerler:
            yaz['group_ids'] = [Command.set([int(g) for g in degerler['gruplar']])]
        eylem.write(yaz)
        return True

    # ================================================================== görünüm türleri
    @api.model
    def _ana_gorunum(self, model, tur, eylem=None):
        View = self.env['ir.ui.view']
        if eylem:
            satir = eylem.view_ids.filtered(lambda v: v.view_mode == tur and v.view_id)
            if satir:
                return satir[0].view_id
            if eylem.view_id and eylem.view_id.type == tur:
                return eylem.view_id
            if tur == 'search' and eylem.search_view_id:
                return eylem.search_view_id
        vid = View.default_view(model, tur)
        return View.browse(vid) if vid else View

    @api.model
    def _alan_bul(self, model, turler, ad_ipucu=()):
        alanlar = self.env[model]._fields
        for ipucu in ad_ipucu:
            if ipucu in alanlar and alanlar[ipucu].type in turler:
                return ipucu
        for ad, f in alanlar.items():
            if f.type in turler and f.store and ad not in ('create_date', 'write_date'):
                return ad
        return False

    @api.model
    def _alan_olustur_basit(self, model, ad, tur, etiket, **ek):
        if ad not in self.env[model]._fields:
            self._xmlid(self.env['ir.model.fields'].create(dict({'model_id': self.env['ir.model']._get_id(model), 'name': ad, 'ttype': tur,
                                                                 'field_description': etiket, 'state': 'manual'}, **ek)), 'alan')
        return ad

    @api.model
    def _varsayilan_arch(self, model, tur):
        M = self.env[model]
        ad = self._ad_alani(model)
        basit = [n for n, f in M._fields.items() if f.store and f.type in ('char', 'date', 'datetime', 'many2one', 'selection', 'monetary', 'float', 'integer', 'boolean')
                 and n not in ('id', 'create_uid', 'write_uid', 'create_date', 'write_date', ad) and not n.startswith(('message_', 'activity_'))][:5]
        if tur == 'form':
            chatter = '<chatter/>' if 'message_ids' in M._fields else ''
            alanlar = ''.join(f'<field name="{n}"/>' for n in basit[:4])
            return (f'<form><sheet><div class="oe_title"><h1><field name="{ad}" placeholder="{M._description}"/></h1></div>'
                    f'<group><group>{alanlar}</group><group/></group></sheet>{chatter}</form>')
        if tur == 'list':
            return '<list>' + f'<field name="{ad}"/>' + ''.join(f'<field name="{n}"/>' for n in basit[:4]) + '</list>'
        if tur == 'search':
            return f'<search><field name="{ad}"/></search>'
        if tur == 'kanban':
            return (f'<kanban><templates><t t-name="card"><field name="{ad}" class="fw-bold"/>'
                    + ''.join(f'<field name="{n}"/>' for n in basit[:2]) + '</t></templates></kanban>')
        if tur == 'calendar':
            tarih = self._alan_bul(model, ('date', 'datetime'), ('x_studio_date', 'date', 'date_start')) or \
                self._alan_olustur_basit(model, 'x_studio_date', 'date', 'Tarih')
            return f'<calendar date_start="{tarih}" string="{M._description}" mode="month"><field name="{ad}"/></calendar>'
        if tur == 'atlas_gantt':
            bas = self._alan_bul(model, ('datetime', 'date'), ('x_studio_date_start', 'date_start', 'date_begin')) or \
                self._alan_olustur_basit(model, 'x_studio_date_start', 'datetime', 'Başlangıç')
            bit = next((n for n in ('x_studio_date_stop', 'date_stop', 'date_end', 'date_deadline') if n in M._fields), False) or \
                self._alan_olustur_basit(model, 'x_studio_date_stop', 'datetime', 'Bitiş')
            return f'<atlas_gantt date_start="{bas}" date_stop="{bit}" string="{M._description}"/>'
        if tur == 'atlas_harita':
            cari = next((n for n, f in M._fields.items() if f.type == 'many2one' and f.comodel_name == 'res.partner' and f.store), False) or \
                self._alan_olustur_basit(model, 'x_studio_partner_id', 'many2one', 'Kontak', relation='res.partner')
            return f'<atlas_harita partner="{cari}" string="{M._description}"/>'
        if tur in ('pivot', 'graph'):
            grup = next((n for n in basit if M._fields[n].type in ('many2one', 'selection')), False)
            satir = f'<field name="{grup}" type="row"/>' if grup else ''
            return f'<{tur} string="{M._description}">{satir}</{tur}>'
        if tur == 'atlas_kohort':
            bit = self._alan_bul(model, ('date', 'datetime'), ('x_studio_date_stop', 'date_end', 'date_stop')) or 'write_date'
            return f'<atlas_kohort date_start="create_date" date_stop="{bit}" interval="month" string="{M._description}"/>'
        if tur == 'activity':
            return f'<activity string="{M._description}"><templates><div t-name="activity-box"><field name="{ad}"/></div></templates></activity>'
        raise UserError(self.env._('Desteklenmeyen görünüm türü: %s', tur))

    @api.model
    def _gorunum_olustur(self, model, tur):
        view = self.env['ir.ui.view'].create({'name': f'{STUDIO_ONEK}{model} {tur}', 'model': model, 'type': tur,
                                              'arch': self._varsayilan_arch(model, tur), 'priority': 99})
        return self._xmlid(view, 'gorunum')

    @api.model
    def gorunum_turu_ayarla(self, action_id, tur, islem):
        """islem: etkinlestir / devre_disi / varsayilan"""
        self._yetki()
        eylem = self.env['ir.actions.act_window'].browse(action_id)
        model = eylem.res_model
        modlar = [m for m in (eylem.view_mode or '').split(',') if m]
        if tur == 'search':
            if islem == 'etkinlestir' and not self._ana_gorunum(model, 'search', eylem):
                self._gorunum_olustur(model, 'search')
            return self.baglam(action_id)
        if islem == 'etkinlestir':
            if not self._ana_gorunum(model, tur, eylem):
                self._gorunum_olustur(model, tur)
            if tur not in modlar:
                modlar.append(tur)
        elif islem == 'devre_disi':
            if len(modlar) <= 1:
                raise UserError(self.env._('Son görünüm devre dışı bırakılamaz.'))
            modlar = [m for m in modlar if m != tur]
            eylem.view_ids.filtered(lambda v: v.view_mode == tur).unlink()
        elif islem == 'varsayilan':
            if tur not in modlar:
                if not self._ana_gorunum(model, tur, eylem):
                    self._gorunum_olustur(model, tur)
            modlar = [tur] + [m for m in modlar if m != tur]
        eylem.view_mode = ','.join(modlar)
        if eylem.view_ids:
            for i, satir in enumerate(eylem.view_ids.sorted(lambda v: modlar.index(v.view_mode) if v.view_mode in modlar else 99)):
                satir.sequence = i
        return self.baglam(action_id)

    # ================================================================== görünüm düzenleyici
    @api.model
    def _studio_gorunumu(self, view, olustur=True):
        View = self.env['ir.ui.view']
        studio = View.search([('inherit_id', '=', view.id), ('name', '=like', f'{STUDIO_ONEK}%'), ('mode', '=', 'extension')], limit=1)
        if not studio and olustur:
            studio = self._xmlid(View.create({'name': f'{STUDIO_ONEK}{view.name} özelleştirme', 'model': view.model, 'type': view.type,
                                              'inherit_id': view.id, 'mode': 'extension', 'priority': 990, 'arch': '<data/>'}), 'ozellestirme')
        return studio

    @api.model
    def _durum(self, view):
        studio = self._studio_gorunumu(view, olustur=False)
        Islem = self.env['atlas.studio.islem']
        arch = view._get_combined_arch()
        M = self.env[view.model]
        alanlar = M.fields_get(attributes=['string', 'type', 'relation', 'selection', 'required', 'readonly', 'store', 'help',
                                           'related', 'currency_field', 'manual', 'sortable', 'groupable'])
        for ad, f in alanlar.items():
            f['ozel'] = ad.startswith('x_')
            f['takip'] = bool(getattr(M._fields.get(ad), 'tracking', False))
        return {
            'view_id': view.id, 'model': view.model, 'tur': view.type, 'arch': etree.tostring(arch, encoding='unicode'),
            'alanlar': alanlar,
            'geri': bool(studio and Islem.search_count([('studio_view_id', '=', studio.id), ('aktif', '=', True)])),
            'ileri': bool(studio and Islem.search_count([('studio_view_id', '=', studio.id), ('aktif', '=', False)])),
            'mail': 'message_ids' in M._fields,
        }

    @api.model
    def gorunum_getir(self, model, tur, action_id=False):
        self._yetki()
        eylem = self.env['ir.actions.act_window'].browse(action_id).exists() if action_id else None
        view = self._ana_gorunum(model, tur, eylem)
        if not view:
            view = self._gorunum_olustur(model, tur)
        while view.mode == 'extension' and view.inherit_id:
            view = view.inherit_id
        return self._durum(view)

    @staticmethod
    def _dugum(root, yol):
        dugum = root
        for i in yol or []:
            cocuklar = [c for c in dugum if isinstance(c.tag, str)]
            if i >= len(cocuklar):
                raise UserError('Görünümde hedef öğe bulunamadı; sayfayı yenileyin.')
            dugum = cocuklar[i]
        return dugum

    @staticmethod
    def _xpath(root, dugum):
        if dugum is root:
            return f'/{root.tag}'
        ad = dugum.get('name')
        if ad and dugum.tag in ADLI_ETIKETLER and "'" not in ad:
            ifade = f"//{dugum.tag}[@name='{ad}']"
            if len(root.xpath(ifade)) == 1:
                return ifade
        parcalar = []
        n = dugum
        while n is not None and n is not root:
            ust = n.getparent()
            ayni = [c for c in ust if c.tag == n.tag]
            parcalar.append(f'{n.tag}[{ayni.index(n) + 1}]')
            n = ust
        return '/' + root.tag + '/' + '/'.join(reversed(parcalar))

    @api.model
    def _eleman(self, tanim):
        """{'tag', 'attrs': {}, 'children': [...], 'text'} → etree öğesi"""
        el = etree.Element(tanim['tag'])
        for k, v in (tanim.get('attrs') or {}).items():
            if v not in (None, False, ''):
                el.set(k, str(v))
        if tanim.get('text'):
            el.text = tanim['text']
        for c in tanim.get('children') or []:
            el.append(self._eleman(c))
        return el

    @api.model
    def _grup_metni(self, deger):
        """[(id, izin_mi)] ya da ['!12', '13'] → 'base.group_x,!base.group_y'"""
        if isinstance(deger, str):
            return deger
        parcalar = []
        for g in deger or []:
            yasak = isinstance(g, str) and g.startswith('!')
            gid = int(str(g).lstrip('!'))
            grup = self.env['res.groups'].browse(gid)
            xid = grup.get_external_id().get(gid) or self._xmlid(grup, 'grup').get_external_id()[gid]
            parcalar.append(('!' if yasak else '') + xid)
        return ','.join(parcalar)

    @api.model
    def _islem_xml(self, root, islem):
        tur = islem['islem']
        if tur == 'ekle':
            hedef = self._dugum(root, islem.get('hedef_yol'))
            xp = etree.Element('xpath', expr=self._xpath(root, hedef), position=islem.get('konum') or 'after')
            xp.append(self._eleman(islem['dugum']))
            return xp, f"Eklendi: {islem['dugum'].get('tag')} {(islem['dugum'].get('attrs') or {}).get('name', '')}"
        if tur == 'kaldir':
            hedef = self._dugum(root, islem['hedef_yol'])
            if hedef is root:
                raise UserError(self.env._('Görünümün kökü kaldırılamaz.'))
            return etree.Element('xpath', expr=self._xpath(root, hedef), position='replace'), f'Kaldırıldı: {hedef.tag} {hedef.get("name") or ""}'
        if tur == 'tasi':
            kaynak = self._dugum(root, islem['kaynak_yol'])
            hedef = self._dugum(root, islem['hedef_yol'])
            if kaynak is hedef or hedef in kaynak.iterdescendants():
                raise UserError(self.env._('Öğe kendi içine taşınamaz.'))
            xp = etree.Element('xpath', expr=self._xpath(root, hedef), position=islem.get('konum') or 'after')
            etree.SubElement(xp, 'xpath', expr=self._xpath(root, kaynak), position='move')
            return xp, f'Taşındı: {kaynak.tag} {kaynak.get("name") or ""}'
        if tur == 'nitelik':
            hedef = self._dugum(root, islem.get('hedef_yol'))
            xp = etree.Element('xpath', expr=self._xpath(root, hedef), position='attributes')
            for ad, deger in (islem.get('nitelikler') or {}).items():
                if ad == 'groups' and isinstance(deger, list):
                    deger = self._grup_metni(deger)
                a = etree.SubElement(xp, 'attribute', name=ad)
                a.text = '' if deger in (None, False) else str(deger)
            return xp, f'Özellik: {hedef.tag} {hedef.get("name") or ""} ({", ".join(islem.get("nitelikler") or {})})'
        raise UserError(self.env._('Bilinmeyen işlem: %s', tur))

    @api.model
    def _studio_arch_yaz(self, studio):
        islemler = self.env['atlas.studio.islem'].search([('studio_view_id', '=', studio.id), ('aktif', '=', True)], order='sira, id')
        studio.arch = '<data>' + ''.join(i.xml for i in islemler) + '</data>'

    @api.model
    def islem_uygula(self, view_id, islemler):
        """Bir ya da daha fazla düzenlemeyi uygular; geçersiz görünüm oluşursa hiçbiri kaydedilmez."""
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        if isinstance(islemler, dict):
            islemler = [islemler]
        studio = self._studio_gorunumu(view)
        Islem = self.env['atlas.studio.islem']
        try:
            with self.env.cr.savepoint():
                Islem.search([('studio_view_id', '=', studio.id), ('aktif', '=', False)]).unlink()
                for islem in islemler:
                    root = view._get_combined_arch()
                    xp, aciklama = self._islem_xml(root, islem)
                    sira = (Islem.search([('studio_view_id', '=', studio.id)], order='sira desc', limit=1).sira or 0) + 1
                    Islem.create({'studio_view_id': studio.id, 'sira': sira, 'xml': etree.tostring(xp, encoding='unicode'),
                                  'aciklama': aciklama[:250]})
                    self._studio_arch_yaz(studio)
                    self.env['ir.ui.view'].invalidate_model()
                    view._get_combined_arch()
                    self.env[view.model].get_view(view.id, view.type)
        except (ValidationError, UserError, ValueError, etree.LxmlError) as e:
            raise UserError(self.env._('Bu değişiklik uygulanamadı: %s', str(e)[:600])) from e
        return self._durum(view)

    @api.model
    def geri_al(self, view_id):
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        studio = self._studio_gorunumu(view, olustur=False)
        if studio:
            son = self.env['atlas.studio.islem'].search([('studio_view_id', '=', studio.id), ('aktif', '=', True)], order='sira desc, id desc', limit=1)
            son.aktif = False
            self._studio_arch_yaz(studio)
        return self._durum(view)

    @api.model
    def yinele(self, view_id):
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        studio = self._studio_gorunumu(view, olustur=False)
        if studio:
            ilk = self.env['atlas.studio.islem'].search([('studio_view_id', '=', studio.id), ('aktif', '=', False)], order='sira, id', limit=1)
            ilk.aktif = True
            self._studio_arch_yaz(studio)
        return self._durum(view)

    @api.model
    def xml_getir(self, view_id):
        """XML düzenleyici: ana görünümün arşivi (salt okunur) ve Studio miras görünümünün arşivi."""
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        studio = self._studio_gorunumu(view, olustur=False)
        ana = etree.fromstring(view.arch)
        return {'ana': etree.tostring(ana, encoding='unicode', pretty_print=True),
                'studio': etree.tostring(etree.fromstring(studio.arch), encoding='unicode', pretty_print=True) if studio else '<data>\n</data>\n'}

    @api.model
    def xml_kaydet(self, view_id, arch):
        """Studio miras görünümünü elle yazılmış XML ile değiştirir (tek bir işlem olarak kaydedilir, geri alınabilir)."""
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        try:
            kok = etree.fromstring(arch.strip())
        except etree.XMLSyntaxError as e:
            raise UserError(self.env._('XML hatalı: %s', e)) from e
        if kok.tag != 'data':
            raise UserError(self.env._('Kök öğe <data> olmalı.'))
        studio = self._studio_gorunumu(view)
        Islem = self.env['atlas.studio.islem']
        try:
            with self.env.cr.savepoint():
                Islem.search([('studio_view_id', '=', studio.id)]).unlink()
                Islem.create({'studio_view_id': studio.id, 'sira': 1, 'aciklama': 'XML düzenlendi',
                              'xml': ''.join(etree.tostring(c, encoding='unicode') for c in kok if isinstance(c.tag, str))})
                self._studio_arch_yaz(studio)
                self.env['ir.ui.view'].invalidate_model()
                self.env[view.model].get_view(view.id, view.type)
        except (ValidationError, UserError, ValueError, etree.LxmlError) as e:
            raise UserError(self.env._('Bu değişiklik uygulanamadı: %s', str(e)[:600])) from e
        return self._durum(view)

    @api.model
    def sifirla(self, view_id):
        """Görünümdeki tüm Studio düzenlemelerini kaldırır."""
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        studio = self._studio_gorunumu(view, olustur=False)
        if studio:
            self.env['atlas.studio.islem'].search([('studio_view_id', '=', studio.id)]).unlink()
            studio.arch = '<data/>'
        return self._durum(view)

    @api.model
    def ornek_kayitlar(self, model, alanlar, limit=5):
        """Liste düzenleyicisinde gerçek örnek satırlar."""
        self._yetki()
        M = self.env[model]
        alanlar = [a for a in alanlar if a in M._fields and M._fields[a].type not in ('binary', 'html', 'one2many', 'many2many')]
        return M.search_read([], alanlar, limit=limit) if alanlar else []

    # ================================================================== alanlar
    @api.model
    def alan_turleri(self):
        return [{'tur': t, 'ad': ad} for t, ad in ALAN_TURLERI]

    @api.model
    def _para_birimi_alani(self, model):
        M = self.env[model]
        for ad in ('currency_id', 'x_studio_currency_id', 'company_currency_id'):
            if ad in M._fields and M._fields[ad].type == 'many2one':
                return ad
        self._alan_olustur_basit(model, 'x_studio_currency_id', 'many2one', 'Para Birimi', relation='res.currency')
        self.env['ir.default'].set(model, 'x_studio_currency_id', self.env.company.currency_id.id)
        return 'x_studio_currency_id'

    @api.model
    def _alt_model(self, ust_model, son_ek, etiket, ek_alanlar=()):
        """Satır / etiket / aşama gibi yardımcı model oluşturur."""
        taban = ust_model.replace('.', '_')
        if not taban.startswith('x_'):
            taban = f'x_{taban}'
        ad = f'{taban}_{son_ek}'[:60]
        if ad in self.env:
            return ad
        irm = self._xmlid(self.env['ir.model'].create({'name': etiket, 'model': ad, 'state': 'manual'}), 'model')
        for alan in ek_alanlar:
            self._xmlid(self.env['ir.model.fields'].create(dict(alan, model_id=irm.id, state='manual')), 'alan')
        self._erisim_olustur(irm)
        return ad

    @api.model
    def _erisim_olustur(self, irm):
        Access = self.env['ir.access']
        for grup, islem in (('base.group_system', 'crud'), ('base.group_user', 'cru')):
            self._xmlid(Access.create({'name': f'{irm.model} {grup.split(".")[1]}', 'model_id': irm.id,
                                       'group_id': self.env.ref(grup).id, 'operation': islem}), 'erisim')

    @api.model
    def alan_olustur(self, model, tanim):
        """tanim: {tur, etiket, secenekler[[anahtar, etiket]], iliski, ters_alan, yol}. Dönüş: {ad, dugum_nitelikleri}"""
        self._yetki()
        tur = tanim['tur']
        etiket = (tanim.get('etiket') or dict(ALAN_TURLERI).get(tur) or 'Alan').strip()
        ad = self._teknik(model, etiket)
        irm = self.env['ir.model']._get(model)
        vals = {'model_id': irm.id, 'name': ad, 'field_description': etiket, 'state': 'manual'}
        nitelik = {}
        if tur in ('char', 'text', 'integer', 'float', 'html', 'date', 'datetime', 'boolean'):
            vals['ttype'] = tur
        elif tur == 'monetary':
            vals.update(ttype='monetary', currency_field=self._para_birimi_alani(model))
        elif tur in ('selection', 'priority'):
            secenekler = tanim.get('secenekler') or []
            if tur == 'priority':
                secenekler = [['0', 'Normal'], ['1', 'Düşük'], ['2', 'Yüksek'], ['3', 'Çok Yüksek']]
                nitelik['widget'] = 'priority'
            if not secenekler:
                raise UserError(self.env._('Seçim alanı için en az bir değer girin.'))
            vals.update(ttype='selection', selection_ids=[Command.create({'value': str(k), 'name': str(e), 'sequence': i})
                                                          for i, (k, e) in enumerate(secenekler)])
        elif tur in ('binary', 'image', 'signature'):
            vals['ttype'] = 'binary'
            if tur == 'binary':
                dosya_adi = self._alan_olustur_basit(model, f'{ad}_filename'[:60], 'char', f'{etiket} Dosya Adı')
                nitelik['filename'] = dosya_adi
            else:
                nitelik['widget'] = 'image' if tur == 'image' else 'signature'
                if tur == 'image':
                    nitelik['class'] = 'oe_avatar' if tanim.get('avatar') else False
        elif tur == 'many2one':
            vals.update(ttype='many2one', relation=tanim['iliski'])
        elif tur == 'many2many':
            vals.update(ttype='many2many', relation=tanim['iliski'])
        elif tur == 'tags':
            etiket_modeli = self._alt_model(model, 'tag', f'{irm.name} Etiketleri', [
                {'name': 'x_color', 'ttype': 'integer', 'field_description': 'Renk'}])
            vals.update(ttype='many2many', relation=etiket_modeli)
            nitelik.update(widget='many2many_tags', options="{'color_field': 'x_color'}")
        elif tur == 'one2many':
            if not tanim.get('iliski') or not tanim.get('ters_alan'):
                raise UserError(self.env._('One2Many için ilişkili model ve o modeldeki Many2One alanı seçilmeli.'))
            vals.update(ttype='one2many', relation=tanim['iliski'], relation_field=tanim['ters_alan'])
        elif tur == 'lines':
            satir_modeli = self._alt_model(model, 'line', f'{irm.name} Satırları', [
                {'name': 'x_studio_sequence', 'ttype': 'integer', 'field_description': 'Sıra'},
                {'name': 'x_studio_value', 'ttype': 'float', 'field_description': 'Değer'}])
            ters = f'x_{model.replace(".", "_")}_id'[:60]
            self._alan_olustur_basit(satir_modeli, ters, 'many2one', irm.name, relation=model, on_delete='cascade')
            vals.update(ttype='one2many', relation=satir_modeli, relation_field=ters)
        elif tur == 'related':
            yol = (tanim.get('yol') or '').strip()
            hedef_model, hedef = self.env[model], None
            for parca in yol.split('.'):
                if parca not in hedef_model._fields:
                    raise UserError(self.env._('Geçersiz alan yolu: %s', yol))
                hedef = hedef_model._fields[parca]
                hedef_model = self.env[hedef.comodel_name] if hedef.relational else hedef_model
            vals.update(ttype=hedef.type, related=yol, readonly=True, store=False,
                        relation=hedef.comodel_name if hedef.relational else False)
            if hedef.type == 'selection':
                vals['selection_ids'] = [Command.create({'value': k, 'name': e, 'sequence': i})
                                         for i, (k, e) in enumerate(hedef._description_selection(self.env))]
            if hedef.type == 'monetary':
                vals['currency_field'] = self._para_birimi_alani(model)
        else:
            raise UserError(self.env._('Bilinmeyen alan tipi: %s', tur))
        alan = self._xmlid(self.env['ir.model.fields'].create(vals), 'alan')
        return {'ad': alan.name, 'nitelikler': {k: v for k, v in nitelik.items() if v}}

    @api.model
    def alan_ozellik(self, model, alan, degerler):
        """Görünümden bağımsız alan ayarları: takip, varsayılan değer, (özel alanlarda) etiket ve yardım."""
        self._yetki()
        f = self.env['ir.model.fields']._get(model, alan)
        if 'takip' in degerler and f.state == 'manual':
            f.tracking = 100 if degerler['takip'] else 0
        if 'varsayilan' in degerler:
            deger = degerler['varsayilan']
            self.env['ir.default'].set(model, alan, deger if deger not in ('', None) else False)
        if f.state == 'manual':
            for anahtar, hedef in (('etiket', 'field_description'), ('yardim', 'help')):
                if anahtar in degerler:
                    f[hedef] = degerler[anahtar]
        if 'ai_istem' in degerler:
            self._ai_otomatik_doldur(model, alan, degerler['ai_istem'])
        return {'varsayilan': self.env['ir.default']._get(model, alan)}

    @api.model
    def _ai_otomatik_doldur(self, model, alan, istem):
        """Autofill: kayıt oluşturulunca/değişince alanı yapay zekâyla dolduran otomasyon (atlas_ai sunucu eylemi)."""
        if 'atlas_ai_istem' not in self.env['ir.actions.server']._fields:
            raise UserError(self.env._('Yapay zekâ modülü kurulu değil.'))
        ad = f'{STUDIO_ONEK}AI ile doldur {model}.{alan}'
        Oto = self.env['base.automation']
        mevcut = Oto.search([('name', '=', ad)], limit=1)
        if not istem:
            mevcut.action_server_ids.unlink()
            mevcut.unlink()
            return
        alan_kaydi = self.env['ir.model.fields']._get(model, alan)
        if mevcut:
            mevcut.action_server_ids.write({'atlas_ai_istem': istem})
            return
        eylem = self._xmlid(self.env['ir.actions.server'].create({
            'name': f'AI: {alan_kaydi.field_description}', 'model_id': alan_kaydi.model_id.id, 'state': 'atlas_ai',
            'atlas_ai_istem': istem, 'atlas_ai_alan_id': alan_kaydi.id, 'usage': 'base_automation'}), 'eylem')
        self._xmlid(Oto.create({'name': ad, 'model_id': alan_kaydi.model_id.id, 'trigger': 'on_create',
                                'action_server_ids': [Command.set(eylem.ids)]}), 'otomasyon')

    @api.model
    def alan_bilgisi(self, model, alan):
        self._yetki()
        f = self.env['ir.model.fields']._get(model, alan)
        oto = self.env['base.automation'].search([('name', '=', f'{STUDIO_ONEK}AI ile doldur {model}.{alan}')], limit=1)
        return {'ozel': f.state == 'manual', 'takip': bool(f.tracking) if 'tracking' in f._fields else False,
                'varsayilan': self.env['ir.default']._get(model, alan),
                'ai_istem': oto.action_server_ids[:1].atlas_ai_istem if oto else ''}

    # ================================================================== düğmeler
    @api.model
    def akilli_dugme_ekle(self, view_id, iliski_alan_id, etiket, simge='list'):
        """Başka modelden bu modele işaret eden Many2One alanı için sayılı akıllı düğme."""
        self._yetki()
        view = self.env['ir.ui.view'].browse(view_id)
        model = view.model
        iliski = self.env['ir.model.fields'].browse(iliski_alan_id)
        if iliski.ttype != 'many2one' or iliski.relation != model:
            raise UserError(self.env._('Seçilen alan bu modele işaret eden bir Many2One olmalı.'))
        sayac = self._teknik(model, f'{iliski.model} {iliski.name} sayısı')
        self._xmlid(self.env['ir.model.fields'].create({
            'model_id': self.env['ir.model']._get_id(model), 'name': sayac, 'ttype': 'integer', 'state': 'manual',
            'field_description': etiket, 'store': False,
            'compute': (f"for record in self:\n    record['{sayac}'] = record.env['{iliski.model}'].search_count("
                        f"[('{iliski.name}', '=', record.id)])"), 'depends': ''}), 'alan')
        eylem = self._xmlid(self.env['ir.actions.act_window'].create({
            'name': etiket, 'res_model': iliski.model, 'view_mode': 'list,form',
            'domain': f"[('{iliski.name}', '=', active_id)]", 'context': f"{{'default_{iliski.name}': active_id}}"}), 'eylem')
        root = view._get_combined_arch()
        dugme = {'tag': 'button', 'attrs': {'class': 'oe_stat_button', 'type': 'action', 'name': str(eylem.id), 'icon': simge},
                 'children': [{'tag': 'field', 'attrs': {'name': sayac, 'widget': 'statinfo', 'string': etiket}}]}
        kutu = root.xpath("//div[@name='button_box']")
        if kutu:
            islem = {'islem': 'ekle', 'hedef_yol': self._yol(root, kutu[0]), 'konum': 'inside', 'dugum': dugme}
        else:
            sheet = root.xpath('//sheet')
            hedef = sheet[0] if sheet else root
            cocuklar = [c for c in hedef if isinstance(c.tag, str)]
            dugum = {'tag': 'div', 'attrs': {'class': 'oe_button_box', 'name': 'button_box'}, 'children': [dugme]}
            islem = ({'islem': 'ekle', 'hedef_yol': self._yol(root, cocuklar[0]), 'konum': 'before', 'dugum': dugum} if cocuklar
                     else {'islem': 'ekle', 'hedef_yol': self._yol(root, hedef), 'konum': 'inside', 'dugum': dugum})
        return self.islem_uygula(view_id, islem)

    @staticmethod
    def _yol(root, dugum):
        yol = []
        n = dugum
        while n is not root:
            ust = n.getparent()
            yol.append([c for c in ust if isinstance(c.tag, str)].index(n))
            n = ust
        return list(reversed(yol))

    @api.model
    def sunucu_eylemleri(self, model):
        self._yetki()
        return [{'id': e.id, 'ad': e.name} for e in self.env['ir.actions.server'].search([('model_id.model', '=', model)])]

    @api.model
    def gelen_iliskiler(self, model):
        """Akıllı düğme için: başka modellerden bu modele işaret eden Many2One alanları."""
        self._yetki()
        alanlar = self.env['ir.model.fields'].search([('ttype', '=', 'many2one'), ('relation', '=', model), ('store', '=', True)], order='model')
        return [{'id': f.id, 'ad': f'{f.model_id.name} › {f.field_description}', 'model': f.model, 'alan': f.name} for f in alanlar
                if f.model in self.env and not self.env[f.model]._transient and not self.env[f.model]._abstract][:200]

    @api.model
    def grup_ara(self, arama=''):
        self._yetki()
        gruplar = self.env['res.groups'].search([('name', 'ilike', arama)], limit=40)
        return [{'id': g.id, 'ad': g.display_name, 'xmlid': g.get_external_id().get(g.id) or self._xmlid(g, 'grup').get_external_id()[g.id]}
                for g in gruplar]

    @api.model
    def grup_adlari(self, xmlidler):
        """'groups' niteliğindeki XML kimliklerinin görünen adları."""
        self._yetki()
        sonuc = {}
        for x in xmlidler:
            g = self.env.ref(x.lstrip('!'), raise_if_not_found=False)
            sonuc[x.lstrip('!')] = g.display_name if g else x
        return sonuc

    @api.model
    def modeller(self, arama=''):
        self._yetki()
        sonuc = self.env['ir.model'].search(['|', ('name', 'ilike', arama), ('model', 'ilike', arama), ('transient', '=', False)], limit=40)
        return [{'model': m.model, 'ad': f'{m.name} ({m.model})'} for m in sonuc if m.model in self.env]
