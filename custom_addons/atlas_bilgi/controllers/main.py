import hmac

from odoo import http
from odoo.http import request


class AtlasBilgiPaylasim(http.Controller):

    @http.route('/bilgi/paylas/<int:makale_id>/<string:anahtar>', type='http', auth='public', methods=['GET'], sitemap=False)
    def paylas(self, makale_id, anahtar, **kw):
        """Bağlantıyla herkese açık makale (salt okunur)."""
        makale = self._makale(makale_id, anahtar)
        alt = makale.child_ids.filtered(lambda a: a.active and a.herkese_acik and a.erisim_anahtari and not a.oge_mi)
        return request.render('atlas_bilgi.paylasim_sayfasi', {'makale': makale, 'alt_makaleler': alt})

    @http.route('/bilgi/paylas/<int:makale_id>/<string:anahtar>/kapak', type='http', auth='public', methods=['GET'], sitemap=False)
    def kapak(self, makale_id, anahtar, **kw):
        makale = self._makale(makale_id, anahtar)
        return request.env['ir.binary']._get_image_stream_from(makale, 'kapak').get_response()

    def _makale(self, makale_id, anahtar):
        makale = request.env['atlas.bilgi.makale'].sudo().browse(makale_id).exists()
        if (not makale or not makale.active or not makale.herkese_acik or not makale.erisim_anahtari
                or not hmac.compare_digest(makale.erisim_anahtari, anahtar)):
            raise request.not_found()
        return makale
