import json

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class AtlasIotVeri(http.Controller):

    @http.route('/iot/veri/<string:anahtar>', type='http', auth='public', methods=['GET', 'POST'], csrf=False, sitemap=False)
    def veri(self, anahtar, **kw):
        """Makine sayacı / sensör verisi. JSON gövde, form ya da sorgu parametresi kabul edilir."""
        cihaz = request.env['atlas.iot.cihaz'].sudo().search([('anahtar', '=', anahtar), ('tur', 'in', ('sayac', 'sensor'))],
                                                             limit=1) if len(anahtar) >= 16 else None
        if not cihaz:
            return request.make_response('Not Found', status=404)
        veri = dict(kw)
        if request.httprequest.mimetype == 'application/json':
            try:
                veri.update(json.loads(request.httprequest.get_data() or b'{}'))
            except ValueError:
                return self._json({'ok': False, 'hata': 'Geçersiz JSON'}, 400)
        try:
            sonuc = cihaz.with_company(cihaz.company_id or request.env.company)._veri_isle(veri)
        except UserError as hata:
            request.env.cr.rollback()
            return self._json({'ok': False, 'hata': str(hata)}, 400)
        return self._json({'ok': True, **sonuc})

    def _json(self, veri, durum=200):
        return request.make_response(json.dumps(veri, ensure_ascii=False, default=str), status=durum,
                                     headers=[('Content-Type', 'application/json; charset=utf-8')])
