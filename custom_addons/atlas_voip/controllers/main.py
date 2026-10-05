import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AtlasVoipOlay(http.Controller):

    @http.route('/voip/olay/<string:anahtar>', type='http', auth='public', methods=['GET', 'POST'], csrf=False, sitemap=False)
    def olay(self, anahtar, **kw):
        """Santral çağrı olayları (JSON gövde, form ya da sorgu parametreleri)."""
        saglayici = request.env['atlas.voip.saglayici'].sudo().search([('olay_anahtari', '=', anahtar)], limit=1) if len(anahtar) >= 16 else None
        if not saglayici:
            return request.make_response('Not Found', status=404)
        veri = dict(kw)
        if request.httprequest.mimetype == 'application/json':
            try:
                veri.update(json.loads(request.httprequest.get_data() or b'{}'))
            except ValueError:
                return request.make_response('Bad Request', status=400)
        cagri = request.env['atlas.voip.cagri'].sudo().with_company(saglayici.company_id or request.env.company)._olay_isle(veri)
        return request.make_response(json.dumps({'ok': True, 'cagri_id': cagri.id or None}),
                                     headers=[('Content-Type', 'application/json')])
