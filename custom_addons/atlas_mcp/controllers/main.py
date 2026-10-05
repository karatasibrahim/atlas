import json

from odoo import http
from odoo.http import request


class AtlasMcpController(http.Controller):

    def _yanit(self, veri, durum=200):
        return request.make_response(json.dumps(veri, ensure_ascii=False, default=str), status=durum,
                                     headers=[('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store')])

    @http.route('/mcp', type='http', auth='bearer', bearer_scope='rpc', methods=['POST'], csrf=False, save_session=False)
    def mcp(self, **kw):
        Mcp = request.env['atlas.mcp']
        if not Mcp._etkin():
            return self._yanit({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32000, 'message': 'MCP sunucusu kapalı'}}, 503)
        try:
            mesaj = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return self._yanit({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'JSON ayrıştırılamadı'}}, 400)
        sonuc = Mcp.isle(mesaj)
        if sonuc is None:  # bildirim
            return request.make_response('', status=202)
        return self._yanit(sonuc)

    @http.route('/mcp', type='http', auth='none', methods=['GET', 'DELETE'], csrf=False, save_session=False)
    def mcp_get(self, **kw):
        # Sunucu tarafından başlatılan akış (SSE) desteklenmez
        return request.make_response('', status=405, headers=[('Allow', 'POST')])
