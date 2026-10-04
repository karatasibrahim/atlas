from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class AtlasDestekPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'destek_count':
            partner = request.env.user.partner_id
            return 'atlas.destek.talep', [('partner_id', 'child_of', [partner.commercial_partner_id.id])], 'read'
        return super()._prepare_portal_counter_values(counter)

    @http.route(['/my/destek', '/my/destek/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_destek(self, page=1, filtre='acik', **kw):
        Talep = request.env['atlas.destek.talep']
        partner = request.env.user.partner_id.commercial_partner_id
        domain = [('partner_id', 'child_of', [partner.id])]
        if filtre == 'acik':
            domain.append(('kapali', '=', False))
        adet = Talep.search_count(domain)
        pager = portal_pager(url='/my/destek', url_args={'filtre': filtre}, total=adet, page=page, step=self._items_per_page)
        talepler = Talep.search(domain, order='create_date desc', limit=self._items_per_page, offset=pager['offset'])
        values = self._prepare_portal_layout_values()
        values.update({'talepler': talepler, 'pager': pager, 'filtre': filtre, 'page_name': 'destek', 'default_url': '/my/destek'})
        return request.render('atlas_destek.portal_my_destek', values)

    @http.route(['/my/destek/<int:talep_id>'], type='http', auth='public', website=True)
    def portal_destek_detay(self, talep_id, access_token=None, **kw):
        try:
            talep = self._document_check_access('atlas.destek.talep', talep_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._get_page_view_values(talep, access_token, {'talep': talep, 'page_name': 'destek_talep', 'object': talep},
                                            'my_destek_history', False, **kw)
        return request.render('atlas_destek.portal_destek_detay', values)

    @http.route(['/my/destek/yeni'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_destek_yeni(self, **post):
        ekipler = request.env['atlas.destek.ekip'].sudo().search([('portal_gorunur', '=', True)])
        tipler = request.env['atlas.destek.tip'].sudo().search([])
        hata = None
        if request.httprequest.method == 'POST':
            baslik = (post.get('baslik') or '').strip()
            if not baslik:
                hata = 'Konu zorunludur.'
            else:
                ekip = ekipler.filtered(lambda e: str(e.id) == post.get('ekip_id'))[:1] or ekipler[:1]
                partner = request.env.user.partner_id
                talep = request.env['atlas.destek.talep'].sudo().create({
                    'baslik': baslik, 'aciklama': (post.get('aciklama') or '').replace('\n', '<br/>'),
                    'partner_id': partner.id, 'ekip_id': ekip.id, 'kanal': 'portal',
                    'tip_id': int(post['tip_id']) if post.get('tip_id', '').isdigit() else False,
                    'company_id': ekip.company_id.id,
                })
                return request.redirect(f'/my/destek/{talep.id}')
        values = self._prepare_portal_layout_values()
        values.update({'ekipler': ekipler, 'tipler': tipler, 'hata': hata, 'page_name': 'destek_yeni', 'post': post})
        return request.render('atlas_destek.portal_destek_yeni', values)
