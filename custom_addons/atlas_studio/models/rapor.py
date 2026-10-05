from lxml import etree

from odoo import api, models
from odoo.exceptions import UserError

from .editor import STUDIO_ONEK


class AtlasStudio(models.AbstractModel):
    _inherit = 'atlas.studio'

    @api.model
    def raporlar(self, model):
        self._yetki()
        return [{'id': r.id, 'ad': r.name, 'report_name': r.report_name, 'tur': r.report_type,
                 'yazdir_menusu': bool(r.binding_model_id)}
                for r in self.env['ir.actions.report'].search([('model', '=', model)], order='name')]

    @api.model
    def _rapor_govdesi(self, model):
        M = self.env[model]
        ad = self._ad_alani(model)
        uygun = lambda n: (n in M._fields and M._fields[n].store and n not in ('id', 'create_uid', 'write_uid', 'create_date', 'write_date', ad, 'display_name')
                           and M._fields[n].type in ('char', 'date', 'datetime', 'many2one', 'selection', 'monetary', 'float', 'integer')
                           and not n.startswith(('message_', 'activity_')))
        # Öncelik formdaki alanlarda (kullanıcının gördüğü sırayla); yoksa modelin alanları
        try:
            form = etree.fromstring(M.get_view(view_type='form')['arch'])
            sirali = list(dict.fromkeys(f.get('name') for f in form.iter('field') if not f.get('invisible') and f.getparent().tag != 'list'))
        except Exception:
            sirali = []
        basit = [n for n in sirali if uygun(n)][:8] or [n for n in M._fields if uygun(n)][:8]
        satirlar = ''.join(f'<tr><th style="width: 35%;">{M._fields[n].string}</th><td><span t-field="doc.{n}"/></td></tr>' for n in basit)
        return (f'<h2><span t-field="doc.{ad}"/></h2>'
                f'<table class="table table-sm o_main_table mt-3"><tbody>{satirlar}</tbody></table>')

    @api.model
    def rapor_olustur(self, model, ad, duzen='dis'):
        """duzen: dis (şirket başlıklı) / ic (iç düzen) / bos"""
        self._yetki()
        if model not in self.env:
            raise UserError(self.env._('Model yok.'))
        sablon_kodu = f'atlas_studio_rapor_{model.replace(".", "_")}_{self.env["ir.ui.view"].search_count([]) + 1}'
        anahtar = f'{"atlas_studio_ozel"}.{sablon_kodu}'
        govde = self._rapor_govdesi(model)
        if duzen == 'bos':
            icerik = f'<t t-foreach="docs" t-as="doc"><div class="page">{govde}</div></t>'
        else:
            yerlesim = 'web.external_layout' if duzen == 'dis' else 'web.internal_layout'
            icerik = f'<t t-foreach="docs" t-as="doc"><t t-call="{yerlesim}"><div class="page">{govde}</div></t></t>'
        arch = f'<t t-name="{anahtar}"><t t-call="web.html_container">{icerik}</t></t>'
        sablon = self.env['ir.ui.view'].create({'name': f'{STUDIO_ONEK}{ad}', 'type': 'qweb', 'key': anahtar, 'arch': arch})
        self.env['ir.model.data'].sudo().create({'module': 'atlas_studio_ozel', 'name': sablon_kodu, 'model': 'ir.ui.view',
                                                 'res_id': sablon.id, 'noupdate': True})
        rapor = self._xmlid(self.env['ir.actions.report'].create({
            'name': ad, 'model': model, 'report_type': 'qweb-pdf', 'report_name': anahtar,
            'binding_model_id': self.env['ir.model']._get_id(model), 'binding_type': 'report'}), 'rapor')
        return {'id': rapor.id}

    @api.model
    def _rapor_sablonu(self, rapor):
        sablon = self.env['ir.ui.view'].search([('type', '=', 'qweb'), ('key', '=', rapor.report_name)], limit=1)
        if not sablon:
            raise UserError(self.env._('Rapor şablonu bulunamadı: %s', rapor.report_name))
        return sablon

    @api.model
    def rapor_getir(self, rapor_id):
        self._yetki()
        rapor = self.env['ir.actions.report'].browse(rapor_id)
        sablon = self._rapor_sablonu(rapor)
        return {'id': rapor.id, 'ad': rapor.name, 'arch': etree.tostring(etree.fromstring(sablon.arch), encoding='unicode', pretty_print=True),
                'yazdir_menusu': bool(rapor.binding_model_id), 'kagit': rapor.paperformat_id.id or False,
                'dosya_adi': rapor.print_report_name or ''}

    @api.model
    def rapor_kaydet(self, rapor_id, arch=None, ad=None, yazdir_menusu=None, dosya_adi=None):
        self._yetki()
        rapor = self.env['ir.actions.report'].browse(rapor_id)
        if arch is not None:
            sablon = self._rapor_sablonu(rapor)
            try:
                with self.env.cr.savepoint():
                    etree.fromstring(arch)
                    sablon.arch = arch
                    self._rapor_html(rapor)
            except Exception as e:
                raise UserError(self.env._('Rapor şablonu geçersiz: %s', str(e)[:500])) from e
        vals = {}
        if ad:
            vals['name'] = ad
        if yazdir_menusu is not None:
            vals.update(binding_model_id=self.env['ir.model']._get_id(rapor.model) if yazdir_menusu else False,
                        binding_type='report')
        if dosya_adi is not None:
            vals['print_report_name'] = dosya_adi or False
        if vals:
            rapor.write(vals)
        return self.rapor_getir(rapor_id)

    @api.model
    def _rapor_html(self, rapor):
        kayit = self.env[rapor.model].search([], limit=1)
        if not kayit:
            return '<p style="font-family: sans-serif; color: #888;">Önizleme için bu modelde en az bir kayıt olmalı.</p>'
        html, _tur = self.env['ir.actions.report']._render_qweb_html(rapor.report_name, kayit.ids)
        return html.decode() if isinstance(html, bytes) else html

    @api.model
    def rapor_onizle(self, rapor_id):
        self._yetki()
        return self._rapor_html(self.env['ir.actions.report'].browse(rapor_id))

    @api.model
    def rapor_sil(self, rapor_id):
        self._yetki()
        rapor = self.env['ir.actions.report'].browse(rapor_id)
        sablon = self.env['ir.ui.view'].search([('type', '=', 'qweb'), ('key', '=', rapor.report_name),
                                                ('key', '=like', 'atlas_studio_ozel.%')], limit=1)
        rapor.unlink()
        sablon.unlink()
        return True
