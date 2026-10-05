import json
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

PROTOKOL = '2025-06-18'
EN_FAZLA_KAYIT = 200
ON_EK = 'atlas_mcp.'
YASAK_MODELLER = {'res.users.apikeys', 'ir.config_parameter', 'res.users.log', 'ir.attachment', 'atlas.mcp.gunluk'}


def _sema(ozellikler, zorunlu=()):
    return {'type': 'object', 'properties': ozellikler, 'required': list(zorunlu)}


ARACLAR = [
    {'name': 'modelleri_listele', 'description': 'Erişebildiğin ERP modellerini (tabloları) listeler. İsteğe bağlı arama metni.',
     'inputSchema': _sema({'arama': {'type': 'string', 'description': 'Model adı ya da açıklamasında geçen metin'}})},
    {'name': 'alanlari_getir', 'description': 'Bir modelin alanlarını (ad, tür, açıklama, ilişki) döndürür.',
     'inputSchema': _sema({'model': {'type': 'string'}}, ['model'])},
    {'name': 'kayit_ara', 'description': 'Odoo alan (domain) koşuluyla kayıt arar ve istenen alanları döndürür.',
     'inputSchema': _sema({'model': {'type': 'string'},
                           'domain': {'type': 'array', 'description': 'Örn. [["state", "=", "posted"], ["date", ">=", "2026-01-01"]]'},
                           'alanlar': {'type': 'array', 'items': {'type': 'string'}},
                           'limit': {'type': 'integer', 'description': f'En fazla {EN_FAZLA_KAYIT}'},
                           'siralama': {'type': 'string', 'description': 'Örn. "date desc"'}}, ['model'])},
    {'name': 'kayit_oku', 'description': 'Kimlikleri verilen kayıtları okur.',
     'inputSchema': _sema({'model': {'type': 'string'}, 'kimlikler': {'type': 'array', 'items': {'type': 'integer'}},
                           'alanlar': {'type': 'array', 'items': {'type': 'string'}}}, ['model', 'kimlikler'])},
    {'name': 'kayit_say', 'description': 'Koşula uyan kayıt sayısı.',
     'inputSchema': _sema({'model': {'type': 'string'}, 'domain': {'type': 'array'}}, ['model'])},
    {'name': 'grupla', 'description': 'Kayıtları gruplayıp toplar (ör. müşteri bazında ciro).',
     'inputSchema': _sema({'model': {'type': 'string'}, 'domain': {'type': 'array'},
                           'grupla': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Örn. ["partner_id", "date:month"]'},
                           'toplamlar': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Örn. ["amount_total:sum", "__count"]'}},
                          ['model', 'grupla'])},
]
YAZMA_ARACLARI = [
    {'name': 'kayit_olustur', 'description': 'Yeni kayıt oluşturur (yönetici MCP yazma iznini açtıysa).',
     'inputSchema': _sema({'model': {'type': 'string'}, 'degerler': {'type': 'object'}}, ['model', 'degerler'])},
    {'name': 'kayit_guncelle', 'description': 'Kayıtları günceller (yönetici MCP yazma iznini açtıysa).',
     'inputSchema': _sema({'model': {'type': 'string'}, 'kimlikler': {'type': 'array', 'items': {'type': 'integer'}},
                           'degerler': {'type': 'object'}}, ['model', 'kimlikler', 'degerler'])},
]


class AtlasMcpGunluk(models.Model):
    _name = 'atlas.mcp.gunluk'
    _description = 'MCP Çağrı Günlüğü'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', string='Kullanıcı', readonly=True)
    yontem = fields.Char(string='Yöntem', readonly=True)
    arac = fields.Char(string='Araç', readonly=True)
    model = fields.Char(string='Model', readonly=True)
    basarili = fields.Boolean(string='Başarılı', readonly=True)
    hata = fields.Char(string='Hata', readonly=True)
    parametreler = fields.Text(string='Parametreler', readonly=True)


class AtlasMcpAyar(models.TransientModel):
    _name = 'atlas.mcp.ayar'
    _description = 'MCP Ayarları'

    etkin = fields.Boolean(string='MCP Sunucusu Etkin')
    yazma = fields.Boolean(string='Kayıt Oluşturma / Güncelleme Araçları')
    adres = fields.Char(string='Sunucu Adresi', compute='_compute_adres')

    def _compute_adres(self):
        taban = self.env['ir.config_parameter'].sudo().get_str('web.base.url')
        for a in self:
            a.adres = f'{taban}/mcp'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env['ir.config_parameter'].sudo()
        res.update(etkin=ICP.get_bool(ON_EK + 'etkin'), yazma=ICP.get_bool(ON_EK + 'yazma'))
        return res

    def action_kaydet(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_bool(ON_EK + 'etkin', self.etkin)
        ICP.set_bool(ON_EK + 'yazma', self.yazma)
        return {'type': 'ir.actions.act_window_close'}


class AtlasMcp(models.AbstractModel):
    """MCP JSON-RPC işleyicisi (HTTP katmanından bağımsız; kullanıcının ortamında çalışır)."""
    _name = 'atlas.mcp'
    _description = 'MCP Sunucusu'

    @api.model
    def _etkin(self):
        return self.env['ir.config_parameter'].sudo().get_bool(ON_EK + 'etkin')

    @api.model
    def _yazma(self):
        return self.env['ir.config_parameter'].sudo().get_bool(ON_EK + 'yazma')

    @api.model
    def isle(self, mesaj):
        """Tek JSON-RPC mesajını işler; bildirimlerde None döner."""
        if not isinstance(mesaj, dict) or mesaj.get('jsonrpc') != '2.0' or 'method' not in mesaj:
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Geçersiz istek'}}
        kimlik = mesaj.get('id')
        yontem = mesaj['method']
        parametre = mesaj.get('params') or {}
        if kimlik is None:  # bildirim (notifications/initialized vb.)
            return None
        try:
            if yontem == 'initialize':
                sonuc = {'protocolVersion': PROTOKOL, 'capabilities': {'tools': {'listChanged': False}},
                         'serverInfo': {'name': 'Atlas ERP', 'version': '20.0.1'},
                         'instructions': ('Atlas ERP (Odoo 20 tabanlı Türk ERP). Önce modelleri_listele ve alanlari_getir ile yapıyı öğren, '
                                          'sonra kayit_ara / grupla ile veri sorgula. Tutarlar şirket para birimindedir.')}
            elif yontem == 'ping':
                sonuc = {}
            elif yontem == 'tools/list':
                sonuc = {'tools': ARACLAR + (YAZMA_ARACLARI if self._yazma() else [])}
            elif yontem == 'tools/call':
                sonuc = self._arac_cagir(parametre.get('name'), parametre.get('arguments') or {})
            else:
                return {'jsonrpc': '2.0', 'id': kimlik, 'error': {'code': -32601, 'message': f'Bilinmeyen yöntem: {yontem}'}}
        except Exception as e:  # beklenmeyen hata
            _logger.exception('MCP hatası')
            return {'jsonrpc': '2.0', 'id': kimlik, 'error': {'code': -32603, 'message': str(e)[:500]}}
        return {'jsonrpc': '2.0', 'id': kimlik, 'result': sonuc}

    def _model(self, ad):
        if not ad or ad not in self.env or ad in YASAK_MODELLER or self.env[ad]._abstract or self.env[ad]._transient:
            raise UserError(self.env._('Geçersiz ya da izin verilmeyen model: %s', ad))
        Model = self.env[ad]
        Model.check_access('read')
        return Model

    def _alanlar(self, Model, istenen):
        okunabilir = {ad for ad, f in Model._fields.items() if not f.groups or self.env.user.has_groups(f.groups)}
        okunabilir -= {ad for ad, f in Model._fields.items() if f.type == 'binary'}
        if istenen:
            return [a for a in istenen if a in okunabilir] or ['display_name']
        varsayilan = [ad for ad, f in Model._fields.items() if ad in okunabilir and f.store and f.type not in ('one2many', 'many2many', 'html', 'text')
                      and not ad.startswith(('message_', 'activity_', 'website_'))]
        return ['display_name'] + varsayilan[:25]

    def _arac_cagir(self, ad, a):
        gunluk = {'user_id': self.env.uid, 'yontem': 'tools/call', 'arac': ad, 'model': a.get('model'),
                  'parametreler': json.dumps(a, ensure_ascii=False, default=str)[:4000]}
        try:
            veri = self._arac(ad, a)
            self.env['atlas.mcp.gunluk'].sudo().create(dict(gunluk, basarili=True))
            metin = json.dumps(veri, ensure_ascii=False, default=str)
            return {'content': [{'type': 'text', 'text': metin}], 'structuredContent': {'sonuc': veri}, 'isError': False}
        except (UserError, AccessError, ValidationError, ValueError, KeyError) as e:
            self.env['atlas.mcp.gunluk'].sudo().create(dict(gunluk, basarili=False, hata=str(e)[:250]))
            return {'content': [{'type': 'text', 'text': f'Hata: {e}'}], 'isError': True}

    def _arac(self, ad, a):
        limit = max(1, min(int(a.get('limit') or 50), EN_FAZLA_KAYIT))
        if ad == 'modelleri_listele':
            arama = (a.get('arama') or '').lower()
            sonuc = []
            for m in self.env['ir.model'].sudo().search([('transient', '=', False)], order='model'):
                if m.model in YASAK_MODELLER or m.model not in self.env or self.env[m.model]._abstract:
                    continue
                if arama and arama not in m.model.lower() and arama not in (m.name or '').lower():
                    continue
                if self.env[m.model].has_access('read'):
                    sonuc.append({'model': m.model, 'ad': m.name})
            return sonuc[:300]
        Model = self._model(a.get('model'))
        if ad == 'alanlari_getir':
            alanlar = Model.fields_get(attributes=['string', 'type', 'relation', 'required', 'readonly', 'selection', 'store'])
            izinli = set(self._alanlar(Model, list(alanlar)))
            return {k: v for k, v in alanlar.items() if k in izinli}
        domain = a.get('domain') or []
        if not isinstance(domain, list):
            raise ValueError('domain bir liste olmalı')
        if ad == 'kayit_ara':
            return Model.search_read(domain, self._alanlar(Model, a.get('alanlar')), limit=limit, order=a.get('siralama') or None)
        if ad == 'kayit_oku':
            return Model.browse([int(i) for i in a.get('kimlikler') or []][:EN_FAZLA_KAYIT]).exists().read(self._alanlar(Model, a.get('alanlar')))
        if ad == 'kayit_say':
            return Model.search_count(domain)
        if ad == 'grupla':
            grupla = a.get('grupla') or []
            toplamlar = a.get('toplamlar') or ['__count']
            satirlar = Model._read_group(domain, grupla, toplamlar, limit=limit)
            sonuc = []
            for satir in satirlar:
                kayit = {}
                for i, g in enumerate(grupla):
                    v = satir[i]
                    kayit[g] = v.display_name if isinstance(v, models.BaseModel) else v
                for j, t in enumerate(toplamlar):
                    kayit[t] = satir[len(grupla) + j]
                sonuc.append(kayit)
            return sonuc
        if ad in ('kayit_olustur', 'kayit_guncelle'):
            if not self._yazma():
                raise UserError(self.env._('MCP yazma araçları kapalı.'))
            if ad == 'kayit_olustur':
                return {'id': Model.create(a.get('degerler') or {}).id}
            kayitlar = Model.browse([int(i) for i in a.get('kimlikler') or []]).exists()
            kayitlar.write(a.get('degerler') or {})
            return {'guncellenen': kayitlar.ids}
        raise UserError(self.env._('Bilinmeyen araç: %s', ad))
