import hmac
from urllib.parse import quote
from datetime import date, timedelta

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request


class AtlasRandevu(http.Controller):

    # ------------------------------------------------------------------ yardımcılar
    def _davet(self, kod):
        return request.env['atlas.randevu.davet']._bul(kod) if kod else request.env['atlas.randevu.davet']

    def _tur(self, tur_id, davet_kodu=None):
        tur = request.env['atlas.randevu.tur'].sudo().browse(tur_id).exists()
        davet = self._davet(davet_kodu)
        if not tur or not tur.active:
            raise request.not_found()
        if davet and tur not in davet.tur_ids:
            raise request.not_found()
        if not tur.yayinda and not davet:
            raise request.not_found()
        return tur, davet

    def _etkinlik(self, etkinlik_id, anahtar):
        e = request.env['calendar.event'].sudo().browse(etkinlik_id).exists()
        if not e or not e.randevu_tur_id or not e.access_token or not hmac.compare_digest(e.access_token, anahtar):
            raise request.not_found()
        return e

    # ------------------------------------------------------------------ sayfalar
    @http.route('/randevu', type='http', auth='public', methods=['GET'], sitemap=True)
    def liste(self, **kw):
        turler = request.env['atlas.randevu.tur'].sudo().search([('yayinda', '=', True)])
        return request.render('atlas_randevu.sayfa_liste', {'turler': turler, 'davet': False})

    @http.route('/randevu/davet/<string:kod>', type='http', auth='public', methods=['GET'], sitemap=False)
    def davet(self, kod, **kw):
        davet = self._davet(kod)
        if not davet:
            raise request.not_found()
        turler = davet.tur_ids.filtered('active')
        if len(turler) == 1:
            return request.redirect(f'/randevu/{turler.id}?davet={kod}')
        return request.render('atlas_randevu.sayfa_liste', {'turler': turler, 'davet': kod})

    @http.route('/randevu/<int:tur_id>', type='http', auth='public', methods=['GET'], sitemap=False)
    def tur(self, tur_id, davet=None, hata=None, **kw):
        tur, davet_kaydi = self._tur(tur_id, davet)
        personel, kaynaklar = tur._izinli(davet_kaydi)
        return request.render('atlas_randevu.sayfa_tur', {
            'tur': tur, 'davet': davet or '', 'personel': personel, 'kaynaklar': kaynaklar, 'hata': hata,
            'bugun': fields.Date.context_today(tur).isoformat(),
        })

    @http.route('/randevu/<int:tur_id>/slotlar', type='http', auth='public', methods=['GET'], sitemap=False)
    def slotlar(self, tur_id, bas=None, bit=None, personel=None, kaynak=None, kisi=1, davet=None, **kw):
        tur, davet_kaydi = self._tur(tur_id, davet)
        try:
            bas_t = date.fromisoformat(bas) if bas else date.today()
            bit_t = date.fromisoformat(bit) if bit else bas_t + timedelta(days=31)
        except ValueError:
            return request.make_json_response({'hata': 'tarih'}, status=400)
        bit_t = min(bit_t, bas_t + timedelta(days=62))
        gunler = tur.musait_slotlar(bas_t, bit_t, personel_id=int(personel) if personel else False,
                                    kaynak_id=int(kaynak) if kaynak else False, kisi=int(kisi or 1), davet=davet_kaydi)
        return request.make_json_response({'gunler': gunler})

    @http.route('/randevu/<int:tur_id>/onayla', type='http', auth='public', methods=['POST'], sitemap=False)
    def onayla(self, tur_id, **post):
        tur, davet_kaydi = self._tur(tur_id, post.get('davet'))
        yanitlar = {}
        for soru in tur.soru_ids:
            anahtar = f'soru_{soru.id}'
            if soru.tip == 'checkbox':
                yanitlar[soru.id] = request.httprequest.form.getlist(anahtar)
            elif post.get(anahtar):
                yanitlar[soru.id] = post[anahtar]
        try:
            etkinlik = tur.randevu_olustur(
                post.get('bas'), {'ad': post.get('ad'), 'email': post.get('email'), 'telefon': post.get('telefon')},
                yanitlar=yanitlar, personel_id=int(post['personel']) if post.get('personel') else False,
                kaynak_id=int(post['kaynak']) if post.get('kaynak') else False, kisi=int(post.get('kisi') or 1),
                davet=davet_kaydi, not_metni=post.get('not') or '')
        except (UserError, ValueError) as e:
            request.env.cr.rollback()
            hedef = f'/randevu/{tur_id}?hata={quote(str(e.args[0] if e.args else e))}'
            if post.get('davet'):
                hedef += f"&davet={quote(post['davet'])}"
            return request.redirect(hedef)
        return request.redirect(f'/randevu/etkinlik/{etkinlik.id}/{etkinlik.access_token}?yeni=1')

    @http.route('/randevu/etkinlik/<int:etkinlik_id>/<string:anahtar>', type='http', auth='public', methods=['GET'], sitemap=False)
    def etkinlik(self, etkinlik_id, anahtar, yeni=None, **kw):
        e = self._etkinlik(etkinlik_id, anahtar)
        return request.render('atlas_randevu.sayfa_etkinlik', {'e': e, 'yeni': bool(yeni), 'tur': e.randevu_tur_id,
                                                               'iptal_edilebilir': e._randevu_iptal_edilebilir()})

    @http.route('/randevu/etkinlik/<int:etkinlik_id>/<string:anahtar>/iptal', type='http', auth='public', methods=['POST'], sitemap=False)
    def iptal(self, etkinlik_id, anahtar, **kw):
        e = self._etkinlik(etkinlik_id, anahtar)
        if e._randevu_iptal_edilebilir():
            e.action_randevu_iptal()
            e.message_post(body=request.env._('Müşteri randevuyu çevrim içi iptal etti.'))
        return request.redirect(f'/randevu/etkinlik/{e.id}/{anahtar}')

    @http.route('/randevu/etkinlik/<int:etkinlik_id>/<string:anahtar>/ics', type='http', auth='public', methods=['GET'], sitemap=False)
    def ics(self, etkinlik_id, anahtar, **kw):
        e = self._etkinlik(etkinlik_id, anahtar)
        return request.make_response(e._randevu_ics(), headers=[('Content-Type', 'text/calendar; charset=utf-8'),
                                                                ('Content-Disposition', 'attachment; filename="randevu.ics"')])
