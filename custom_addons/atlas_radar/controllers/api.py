"""Salt okunur Radar REST API.

Kimlik doğrulama: Authorization: Bearer <API anahtarı> (Tercihler → Hesap Güvenliği → API Anahtarları).
Yalnız sistem yöneticisi kullanıcıların anahtarları kabul edilir.

GET /atlas_radar/api/v1/degisiklikler?durum=yeni&onem=kritik&kategori=ebelge&tarih_bas=2026-01-01&limit=50&offset=0
GET /atlas_radar/api/v1/degisiklikler/<id>
GET /atlas_radar/api/v1/kaynaklar
"""
import json

from odoo import fields, http
from odoo.http import request

AZAMI_LIMIT = 200


def _yanit(veri, durum=200):
    return request.make_response(json.dumps(veri, ensure_ascii=False, default=str),
                                 headers=[('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store')],
                                 status=durum)


def _degisiklik(d, ayrinti=False):
    veri = {
        'id': d.id, 'baslik': d.name, 'durum': d.durum, 'onem': d.onem, 'tur': d.tur,
        'kategori': d.kategori_id.kod or None, 'kurum': d.kurum, 'kaynak': d.kaynak_id.name, 'ulke': d.ulke_id.code or None,
        'url': d.url, 'yayim_tarihi': d.yayim_tarihi, 'tespit_tarihi': fields.Datetime.to_string(d.tespit_tarihi),
        'yururluk_tarihi': d.yururluk_tarihi, 'kirici': d.kirici, 'gelistirme_gerekli': d.gelistirme_gerekli,
        'ayar_gerekli': d.ayar_gerekli, 'kullanici_aksiyonu': d.kullanici_aksiyonu, 'siniflandirma': d.siniflandirma,
        'guven': d.guven, 'ai_onerisi': d.ai_onerisi, 'moduller': d.modul_ids.mapped('teknik_ad'),
        'sirketler': d.company_ids.mapped('name'),
    }
    if ayrinti:
        veri.update({
            'ozet': d.ozet, 'icerik': d.icerik, 'fark': d.fark, 'inceleme_notu': d.inceleme_notu,
            'etkiler': [{'modul': e.modul_id.teknik_ad, 'sirket': e.company_id.name or None, 'durum': e.durum,
                         'sorumlu': e.sorumlu_id.name or None, 'aciklama': e.aciklama} for e in d.etki_ids],
            'gorevler': [{'id': t.id, 'ad': t.name, 'kapali': t.is_closed} for t in d.sudo().task_ids],
            'mukerrer_id': d.mukerrer_id.id or None,
        })
    return veri


class AtlasRadarApi(http.Controller):

    def _yetkili(self):
        return request.env.user.has_group('base.group_system')

    @http.route('/atlas_radar/api/v1/degisiklikler', type='http', auth='bearer', bearer_scope='rpc', methods=['GET'],
                csrf=False, readonly=True, sitemap=False)
    def degisiklikler(self, durum=None, onem=None, kategori=None, tarih_bas=None, limit=50, offset=0, **kw):
        if not self._yetkili():
            return _yanit({'hata': 'Yetkisiz'}, 403)
        alan = []
        if durum:
            alan.append(('durum', 'in', durum.split(',')))
        if onem:
            alan.append(('onem', 'in', onem.split(',')))
        if kategori:
            alan.append(('kategori_id.kod', 'in', kategori.split(',')))
        if tarih_bas:
            try:
                alan.append(('tespit_tarihi', '>=', fields.Datetime.to_datetime(tarih_bas)))
            except ValueError:
                return _yanit({'hata': 'tarih_bas geçersiz (YYYY-AA-GG)'}, 400)
        try:
            limit, offset = min(max(int(limit), 1), AZAMI_LIMIT), max(int(offset), 0)
        except ValueError:
            return _yanit({'hata': 'limit/offset sayı olmalı'}, 400)
        Degisiklik = request.env['atlas.radar.degisiklik']
        kayitlar = Degisiklik.search(alan, limit=limit, offset=offset)
        return _yanit({'toplam': Degisiklik.search_count(alan), 'limit': limit, 'offset': offset,
                       'kayitlar': [_degisiklik(d) for d in kayitlar]})

    @http.route('/atlas_radar/api/v1/degisiklikler/<int:kayit_id>', type='http', auth='bearer', bearer_scope='rpc',
                methods=['GET'], csrf=False, readonly=True, sitemap=False)
    def degisiklik(self, kayit_id, **kw):
        if not self._yetkili():
            return _yanit({'hata': 'Yetkisiz'}, 403)
        d = request.env['atlas.radar.degisiklik'].browse(kayit_id).exists()
        if not d:
            return _yanit({'hata': 'Bulunamadı'}, 404)
        return _yanit(_degisiklik(d, ayrinti=True))

    @http.route('/atlas_radar/api/v1/kaynaklar', type='http', auth='bearer', bearer_scope='rpc', methods=['GET'],
                csrf=False, readonly=True, sitemap=False)
    def kaynaklar(self, **kw):
        if not self._yetkili():
            return _yanit({'hata': 'Yetkisiz'}, 403)
        kaynaklar = request.env['atlas.radar.kaynak'].with_context(active_test=False).search([])
        return _yanit({'kayitlar': [{
            'id': k.id, 'ad': k.name, 'kurum': k.kurum, 'url': k.url, 'etkin': k.active, 'tur': k.tur, 'ulke': k.ulke_id.code or None,
            'yetki_alani': k.yetki_alani, 'saglik': k.saglik, 'robots': k.robots_durumu,
            'son_kontrol': fields.Datetime.to_string(k.son_kontrol) if k.son_kontrol else None,
            'son_basari': fields.Datetime.to_string(k.son_basari) if k.son_basari else None,
            'ardisik_hata': k.ardisik_hata, 'yanit_suresi_ms': k.yanit_suresi, 'son_hata': k.son_hata,
        } for k in kaynaklar]})
