"""Studio özelleştirmelerini veri modülü (.zip) olarak dışa aktarma.

İçe aktarma Odoo'nun 'Modül İçe Aktar' (base_import_module) özelliğiyle yapılır: yalnız XML veri, Python yok.
"""
import base64
import io
import zipfile
from xml.sax.saxutils import escape

from lxml import etree

from odoo import api, models

from .editor import STUDIO_MODUL

SIRA = ['ir.model', 'ir.model.fields', 'ir.model.fields.selection', 'res.groups', 'ir.access', 'ir.ui.view', 'ir.actions.act_window',
        'ir.actions.server', 'ir.actions.report', 'ir.ui.menu', 'base.automation', 'ir.filters', 'atlas.studio.onay.kural']
ATLA = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name', '__last_update', 'arch_db', 'arch_fs',
        'arch_prev', 'arch_updated', 'model_data_id', 'xml_id', 'field_id', 'inherit_children_ids', 'child_id', 'view_ids',
        'web_icon_data', 'binding_view_types', 'complete_name', 'parent_path', 'selection_ids', 'model_ids'}


class AtlasStudio(models.AbstractModel):
    _inherit = 'atlas.studio'

    @api.model
    def _ref(self, kayit):
        xid = kayit.get_external_id().get(kayit.id)
        if not xid:
            self._xmlid(kayit, 'bagli')
            xid = kayit.get_external_id().get(kayit.id)
        return xid

    @api.model
    def _kayit_xml(self, kayit, xid):
        satirlar = [f'    <record id="{xid.split(".", 1)[1] if xid.startswith(STUDIO_MODUL + ".") else xid}" model="{kayit._name}">']
        for ad, f in kayit._fields.items():
            if ad in ATLA or not f.store or (f.compute and not f.inverse and f.readonly) or f.type == 'one2many':
                continue
            if f.related:
                continue
            deger = kayit[ad]
            if f.type == 'many2one':
                if deger:
                    satirlar.append(f'        <field name="{ad}" ref="{self._ref(deger)}"/>')
            elif f.type == 'many2many':
                if deger:
                    refler = ', '.join(f"ref('{self._ref(r)}')" for r in deger)
                    satirlar.append(f'        <field name="{ad}" eval="[(6, 0, [{refler}])]"/>')
            elif f.type == 'boolean':
                satirlar.append(f'        <field name="{ad}" eval="{bool(deger)}"/>')
            elif f.type in ('integer', 'float', 'monetary'):
                satirlar.append(f'        <field name="{ad}" eval="{deger!r}"/>')
            elif deger in (False, None):
                continue
            elif f.type == 'binary':
                icerik = deger.content if hasattr(deger, 'content') else deger
                satirlar.append(f'        <field name="{ad}">{escape(base64.b64encode(icerik).decode() if isinstance(icerik, bytes) else str(icerik))}</field>')
            elif f.type in ('json', 'properties'):
                satirlar.append(f'        <field name="{ad}" eval="{escape(repr(deger))}"/>')
            else:
                satirlar.append(f'        <field name="{ad}">{escape(str(deger))}</field>')
        if kayit._name == 'ir.ui.view':
            arch = kayit.arch_db or kayit.arch
            satirlar.append(f'        <field name="arch" type="xml">{self._arch_ref(arch)}</field>')
        if kayit._name == 'ir.ui.menu' and kayit.web_icon_data:
            satirlar.append(f'        <field name="web_icon_data">{base64.b64encode(kayit.web_icon_data.content if hasattr(kayit.web_icon_data, "content") else kayit.web_icon_data).decode()}</field>')
        satirlar.append('    </record>')
        return '\n'.join(satirlar)

    @api.model
    def _arch_ref(self, arch):
        """Düğmelerdeki sayısal eylem kimliklerini %(xmlid)d biçimine çevirir (başka veritabanında da çalışsın)."""
        kok = etree.fromstring(arch)
        for d in kok.iter('button'):
            if d.get('type') == 'action' and (d.get('name') or '').isdigit():
                eylem = self.env['ir.actions.actions'].browse(int(d.get('name'))).exists()
                if eylem:
                    gercek = self.env[eylem.type].browse(eylem.id)
                    d.set('name', f'%({self._ref(gercek)})d')
        return etree.tostring(kok, encoding='unicode')

    @api.model
    def disa_aktar(self):
        """Studio özelleştirmelerini içeren veri modülünün zip içeriği (bayt)."""
        self._yetki()
        Veri = self.env['ir.model.data'].sudo()
        kayitlar = Veri.search([('module', '=', STUDIO_MODUL)])
        gruplar = {}
        for v in kayitlar:
            if v.model in self.env and self.env[v.model].browse(v.res_id).exists():
                gruplar.setdefault(v.model, []).append(v)
        bloklar = []
        bagimliliklar = {'base', 'web', 'mail', 'base_automation'}
        for model in sorted(gruplar, key=lambda m: SIRA.index(m) if m in SIRA else len(SIRA)):
            for v in sorted(gruplar[model], key=lambda v: v.res_id):
                kayit = self.env[model].browse(v.res_id)
                if model == 'ir.model.fields' and kayit.state != 'manual':
                    continue
                bloklar.append(self._kayit_xml(kayit, f'{STUDIO_MODUL}.{v.name}'))
                for ad in ('model', 'res_model'):
                    if ad in kayit._fields and kayit[ad] and isinstance(kayit[ad], str):
                        irm = self.env['ir.model']._get(kayit[ad])
                        if irm and irm.modules:
                            bagimliliklar.update(m.strip() for m in irm.modules.split(','))
        bagimliliklar = sorted(m for m in bagimliliklar if m and self.env['ir.module.module'].search_count([('name', '=', m), ('state', '=', 'installed')]))
        veri = '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n' + '\n'.join(bloklar) + '\n</odoo>\n'
        manifest = ("{\n    'name': 'Atlas Studio Özelleştirmeleri',\n    'version': '1.0',\n    'category': 'Customizations',\n"
                    f"    'depends': {bagimliliklar!r},\n    'data': ['data/ozellestirmeler.xml'],\n    'license': 'LGPL-3',\n}}\n")
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr(f'{STUDIO_MODUL}/__manifest__.py', manifest)
            z.writestr(f'{STUDIO_MODUL}/__init__.py', '')
            z.writestr(f'{STUDIO_MODUL}/data/ozellestirmeler.xml', veri)
        return tampon.getvalue()
