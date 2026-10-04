import base64
import binascii

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class AtlasImzaSayfasi(http.Controller):

    def _imzaci(self, token):
        if not token or len(token) < 20:
            return None
        imzaci = request.env['atlas.imza.imzaci'].sudo().search([('token', '=', token)], limit=1)
        return imzaci or None

    def _istemci(self):
        return request.httprequest.remote_addr, request.httprequest.headers.get('User-Agent', '')

    @http.route('/imza/<string:token>', type='http', auth='public', methods=['GET'], sitemap=False)
    def imza_sayfasi(self, token, hata=None, **kw):
        imzaci = self._imzaci(token)
        if not imzaci:
            return request.not_found()
        if imzaci._imzalayabilir():
            ip, tarayici = self._istemci()
            imzaci._goruntulendi(ip=ip, tarayici=tarayici)
        return request.render('atlas_imza.imza_sayfasi', {
            'imzaci': imzaci, 'talep': imzaci.talep_id, 'token': token, 'hata': hata,
            'imzalayabilir': imzaci._imzalayabilir(),
        })

    @http.route('/imza/<string:token>/belge', type='http', auth='public', methods=['GET'], sitemap=False)
    def imza_belge(self, token, **kw):
        imzaci = self._imzaci(token)
        if not imzaci:
            return request.not_found()
        talep = imzaci.talep_id
        alan = 'imzali_dosya' if talep.durum == 'tamamlandi' else 'dosya'
        ad = (talep.imzali_dosya_adi if alan == 'imzali_dosya' else talep.dosya_adi) or f'{talep.name}.pdf'
        stream = request.env['ir.binary']._get_stream_from(talep, alan, filename=ad, mimetype='application/pdf')
        return stream.get_response(as_attachment=bool(kw.get('indir')))

    @http.route('/imza/<string:token>/imzala', type='http', auth='public', methods=['POST'], sitemap=False)
    def imzala(self, token, imza=None, ad_soyad=None, onay=None, **kw):
        imzaci = self._imzaci(token)
        if not imzaci:
            return request.not_found()
        try:
            if not onay:
                raise UserError(request.env._('Belgeyi okuduğunuzu ve onayladığınızı işaretleyin.'))
            if not imza or not imza.startswith('data:image/png;base64,'):
                raise UserError(request.env._('Lütfen imzanızı çizin.'))
            try:
                png = base64.b64decode(imza.split(',', 1)[1], validate=True)
            except (binascii.Error, ValueError) as hata:
                raise UserError(request.env._('İmza görüntüsü okunamadı.')) from hata
            if len(png) > 2 * 1024 * 1024:
                raise UserError(request.env._('İmza görüntüsü çok büyük.'))
            ip, tarayici = self._istemci()
            imzaci._imzala(png, ad_soyad, ip=ip, tarayici=tarayici)
        except UserError as hata:
            request.env.cr.rollback()
            return self.imza_sayfasi(token, hata=str(hata))
        return request.redirect(f'/imza/{token}')

    @http.route('/imza/<string:token>/reddet', type='http', auth='public', methods=['POST'], sitemap=False)
    def reddet(self, token, neden=None, **kw):
        imzaci = self._imzaci(token)
        if not imzaci:
            return request.not_found()
        try:
            ip, tarayici = self._istemci()
            imzaci._reddet(neden, ip=ip, tarayici=tarayici)
        except UserError as hata:
            request.env.cr.rollback()
            return self.imza_sayfasi(token, hata=str(hata))
        return request.redirect(f'/imza/{token}')
