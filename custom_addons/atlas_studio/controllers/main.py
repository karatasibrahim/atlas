from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition


class AtlasStudioController(http.Controller):

    @http.route('/atlas_studio/disa_aktar', type='http', auth='user', methods=['GET'])
    def disa_aktar(self, **kw):
        icerik = request.env['atlas.studio'].disa_aktar()
        return request.make_response(icerik, headers=[('Content-Type', 'application/zip'),
                                                      ('Content-Disposition', content_disposition('atlas_studio_ozel.zip'))])
