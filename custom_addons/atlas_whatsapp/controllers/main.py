import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AtlasWhatsappWebhook(http.Controller):

    def _hesap(self, hesap_id):
        return request.env['atlas.whatsapp.hesap'].sudo().browse(hesap_id).exists()

    @http.route('/whatsapp/webhook/<int:hesap_id>', type='http', auth='public', methods=['GET'], csrf=False, sitemap=False)
    def dogrula(self, hesap_id, **kw):
        """Meta webhook doğrulaması: hub.verify_token eşleşirse hub.challenge döner."""
        hesap = self._hesap(hesap_id)
        if hesap and kw.get('hub.mode') == 'subscribe' and kw.get('hub.verify_token') == hesap.dogrulama_anahtari:
            return request.make_response(kw.get('hub.challenge', ''), headers=[('Content-Type', 'text/plain')])
        return request.make_response('Forbidden', status=403)

    @http.route('/whatsapp/webhook/<int:hesap_id>', type='http', auth='public', methods=['POST'], csrf=False, sitemap=False)
    def bildirim(self, hesap_id, **kw):
        hesap = self._hesap(hesap_id)
        if not hesap:
            return request.make_response('Not Found', status=404)
        govde = request.httprequest.get_data()
        if not hesap._imza_dogrula(govde, request.httprequest.headers.get('X-Hub-Signature-256')):
            _logger.warning('WhatsApp webhook imzası geçersiz (hesap %s)', hesap_id)
            return request.make_response('Invalid signature', status=403)
        try:
            veri = json.loads(govde or b'{}')
        except ValueError:
            return request.make_response('Bad Request', status=400)
        hesap._webhook_isle(veri)
        return request.make_response('OK')
