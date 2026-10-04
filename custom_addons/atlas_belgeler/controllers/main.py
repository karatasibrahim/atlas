from markupsafe import escape

from odoo import http
from odoo.http import request


class AtlasBelgePaylasim(http.Controller):

    def _paylasim(self, token):
        paylasim = request.env['atlas.belge.paylasim'].sudo().search([('token', '=', token)], limit=1)
        return paylasim if paylasim and paylasim._gecerli() else None

    def _indir(self, paylasim, belge):
        paylasim.indirme_sayisi += 1
        if belge.tip == 'url':
            return request.redirect(belge.url, local=False)
        stream = request.env['ir.binary']._get_stream_from(belge.sudo(), 'dosya', filename=belge.dosya_adi or belge.name)
        return stream.get_response(as_attachment=True)

    @http.route('/belge/paylas/<string:token>', type='http', auth='public')
    def paylasim(self, token, **kw):
        paylasim = self._paylasim(token)
        if not paylasim:
            return request.not_found()
        belgeler = paylasim.belge_ids.filtered('aktif')
        if len(belgeler) == 1:
            return self._indir(paylasim, belgeler)
        satirlar = ''.join(f'<li><a href="/belge/paylas/{escape(token)}/{b.id}">{escape(b.name)}</a></li>' for b in belgeler)
        html = (f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(paylasim.name)}</title>'
                f'<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
                f'<body style="font-family:sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem">'
                f'<h2>{escape(paylasim.name)}</h2><ul>{satirlar}</ul></body></html>')
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/belge/paylas/<string:token>/<int:belge_id>', type='http', auth='public')
    def paylasim_belge(self, token, belge_id, **kw):
        paylasim = self._paylasim(token)
        belge = paylasim.belge_ids.filtered(lambda b: b.id == belge_id and b.aktif) if paylasim else None
        if not belge:
            return request.not_found()
        return self._indir(paylasim, belge)
