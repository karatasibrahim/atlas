import io
import json
import zipfile

from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition


class AtlasTabloController(http.Controller):

    @http.route('/atlas_tablo/xlsx', type='http', auth='user', methods=['POST'], csrf=True)
    def xlsx(self, veri, ad='tablo', **kw):
        """o-spreadsheet exportXLSX çıktısını (dosya listesi) .xlsx (zip) olarak döndürür."""
        dosyalar = json.loads(veri)
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for d in dosyalar:
                if 'content' in d:
                    z.writestr(d['path'], d['content'])
        ad = (ad or 'tablo').replace('/', '-')
        return request.make_response(tampon.getvalue(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(f'{ad}.xlsx'))])
