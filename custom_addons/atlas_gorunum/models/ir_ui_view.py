from lxml import etree

from odoo import fields, models

GANTT_ALANLARI = ('date_start', 'date_stop', 'default_group_by', 'color', 'progress', 'label')
HARITA_ALANLARI = ('partner', 'lat', 'lng', 'label')
GANTT_NITELIKLERI = {'__validate__', 'string', 'class', 'js_class', 'create', 'edit', 'delete', 'default_scale',
                     'precision', *GANTT_ALANLARI}
HARITA_NITELIKLERI = {'__validate__', 'string', 'class', 'js_class', 'create', 'edit', 'delete', *HARITA_ALANLARI}


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('atlas_gantt', 'Gantt'), ('atlas_harita', 'Harita')],
                            ondelete={'atlas_gantt': 'cascade', 'atlas_harita': 'cascade'})

    def _get_view_info(self):
        return {'atlas_gantt': {'icon': 'view_timeline'}, 'atlas_harita': {'icon': 'map'}} | super()._get_view_info()

    def _atlas_alanlari_kaydet(self, node, name_manager, node_info, alanlar):
        for nitelik in alanlar:
            if fname := node.get(nitelik):
                name_manager.has_field(node, fname, node_info)
        for f in node.iterchildren(tag='field'):
            name_manager.has_field(node, f.get('name'), node_info)

    def _postprocess_tag_atlas_gantt(self, node, name_manager, node_info):
        self._atlas_alanlari_kaydet(node, name_manager, node_info, GANTT_ALANLARI)

    def _postprocess_tag_atlas_harita(self, node, name_manager, node_info):
        self._atlas_alanlari_kaydet(node, name_manager, node_info, HARITA_ALANLARI)

    def _atlas_dogrula(self, node, name_manager, node_info, gecerli, zorunlu):
        if not node_info['validate']:
            return
        for child in node.iterchildren(tag=etree.Element):
            if child.tag != 'field':
                self._raise_view_error(self.env._('<%(tag)s> içinde yalnızca <field> kullanılabilir, bulunan: <%(alt)s>',
                                                  tag=node.tag, alt=child.tag), child)
        fazla = set(node.attrib) - gecerli
        if fazla:
            self._raise_view_error(self.env._('Geçersiz nitelik(ler): %s', ', '.join(sorted(fazla))), node)
        for nitelik in zorunlu:
            if not node.get(nitelik):
                self._raise_view_error(self.env._('<%(tag)s> görünümünde "%(nitelik)s" niteliği zorunlu.',
                                                  tag=node.tag, nitelik=nitelik), node)

    def _validate_tag_atlas_gantt(self, node, name_manager, node_info):
        self._atlas_dogrula(node, name_manager, node_info, GANTT_NITELIKLERI, ('date_start', 'date_stop'))
        self._atlas_alanlari_kaydet(node, name_manager, node_info, GANTT_ALANLARI)

    def _validate_tag_atlas_harita(self, node, name_manager, node_info):
        self._atlas_dogrula(node, name_manager, node_info, HARITA_NITELIKLERI, ())
        self._atlas_alanlari_kaydet(node, name_manager, node_info, HARITA_ALANLARI)
        if node_info['validate'] and not node.get('partner') and not (node.get('lat') and node.get('lng')):
            self._raise_view_error(self.env._('<atlas_harita> için "partner" ya da "lat" ve "lng" nitelikleri gerekli.'), node)


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(selection_add=[('atlas_gantt', 'Gantt'), ('atlas_harita', 'Harita')],
                                 ondelete={'atlas_gantt': 'cascade', 'atlas_harita': 'cascade'})
