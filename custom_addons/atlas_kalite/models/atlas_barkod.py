"""Barkod uygulamasına kalite kontrol ekranları için sunucu metotları."""
from odoo import api, models
from odoo.exceptions import UserError

from .atlas_kalite_nokta import ASAMALAR, TEST_TIPLERI

QC_PREFIX = 'ATL:QC:'


class AtlasBarkod(models.AbstractModel):
    _inherit = 'atlas.barkod'

    @api.model
    def _parse(self, code, products=None):
        kod = (code or '').strip()
        if kod.upper().startswith(QC_PREFIX):
            kontrol = self.env['atlas.kalite.kontrol'].search([('name', '=', kod[len(QC_PREFIX):])], limit=1)
            if not kontrol:
                raise UserError(self.env._('Kalite kontrolü bulunamadı: %s', kod))
            return {'tip': 'kalite', 'product': self.env['product.product'], 'lot': self.env['stock.lot'],
                    'lot_name': False, 'location': self.env['stock.location'], 'record': kontrol, 'kod': kod}
        try:
            return super()._parse(code, products)
        except UserError:
            kontrol = self.env['atlas.kalite.kontrol'].search([('name', '=', kod)], limit=1) if kod else False
            if not kontrol:
                raise
            return {'tip': 'kalite', 'product': self.env['product.product'], 'lot': self.env['stock.lot'],
                    'lot_name': False, 'location': self.env['stock.location'], 'record': kontrol, 'kod': kod}

    @api.model
    def cozumle(self, code):
        parsed = self._parse(code)
        if parsed['tip'] == 'kalite':
            return {'tip': 'kalite', 'kod': code, 'kalite': self.kalite_ac(parsed['record'].id)}
        return super().cozumle(code)

    @api.model
    def _bekleyen_kalite_domain(self):
        return [('durum', '=', 'bekliyor'), ('company_id', 'in', self.env.companies.ids),
                '|', '|', ('picking_id.state', 'in', ('draft', 'waiting', 'confirmed', 'assigned')),
                ('production_id.state', 'in', ('draft', 'confirmed', 'progress', 'to_close')),
                '&', ('picking_id', '=', False), ('production_id', '=', False)]

    @api.model
    def ana_ekran(self):
        res = super().ana_ekran()
        res['kalite'] = self.env['atlas.kalite.kontrol'].search_count(self._bekleyen_kalite_domain())
        return res

    @api.model
    def _kalite_ozet(self, kontrol):
        return {'id': kontrol.id, 'ad': kontrol.name, 'nokta': kontrol.nokta_id.name,
                'urun': kontrol.product_id.display_name or '', 'seri': kontrol.lot_name or '',
                'durum': kontrol.durum, 'engelleyici': kontrol.engelleyici, 'test_tipi': kontrol.test_tipi}

    @api.model
    def belge_listesi(self, islem, arama=''):
        if islem != 'kalite':
            return super().belge_listesi(islem, arama)
        domain = self._bekleyen_kalite_domain()
        if arama:
            domain += ['|', '|', '|', ('name', 'ilike', arama), ('nokta_id', 'ilike', arama),
                       ('product_id', 'ilike', arama), ('lot_name', 'ilike', arama)]
        return [{'id': k.id, 'ad': f'{k.name} · {k.nokta_id.name}',
                 'alt': ' / '.join(x for x in (k.product_id.display_name, k.lot_name) if x),
                 'bilgi': k.belge or '', 'tarih': '', 'durum': k.durum}
                for k in self.env['atlas.kalite.kontrol'].search(domain, order='id', limit=100)]

    @api.model
    def belge_ac(self, islem, res_id):
        if islem == 'kalite':
            return self.kalite_ac(res_id)
        res = super().belge_ac(islem, res_id)
        if islem in ('mal_kabul', 'sevkiyat'):
            belge = self.env['stock.picking'].browse(res_id)
        elif islem == 'uretim':
            belge = self.env['mrp.production'].browse(res_id)
        else:
            return res
        belge._atlas_kalite_olustur()
        res['kalite'] = [self._kalite_ozet(k) for k in belge.atlas_kalite_kontrol_ids.sorted('id')]
        return res

    @api.model
    def _kontrol(self, kontrol_id):
        kontrol = self.env['atlas.kalite.kontrol'].browse(kontrol_id).exists()
        if not kontrol:
            raise UserError(self.env._('Kalite kontrolü bulunamadı.'))
        return kontrol

    @api.model
    def kalite_ac(self, kontrol_id):
        k = self._kontrol(kontrol_id)
        belge = k.picking_id or k.production_id
        islem = False
        if k.picking_id:
            islem = {'incoming': 'mal_kabul', 'outgoing': 'sevkiyat'}.get(k.picking_id.picking_type_code)
        elif k.production_id:
            islem = 'uretim'
        return {
            **self._kalite_ozet(k),
            'qr': k.atlas_qr,
            'asama': dict(ASAMALAR).get(k.asama, ''),
            'test_tipi_ad': dict(TEST_TIPLERI).get(k.test_tipi, ''),
            'belge': {'id': belge.id, 'ad': k.belge, 'islem': islem} if belge else False,
            'talimat': k.talimat or '',
            'basarisiz_mesaj': k.basarisiz_mesaj or '',
            'norm': k.norm, 'alt_sinir': k.alt_sinir, 'ust_sinir': k.ust_sinir, 'birim': k.olcu_birimi or '',
            'olcum': k.olcum if k.olcum_girildi else None,
            'test_edilen': k.test_edilen, 'hatali': k.hatali, 'kabul_orani': k.kabul_orani,
            'maddeler': [{'id': m.id, 'ad': m.name, 'sonuc': m.sonuc or ''} for m in k.madde_ids],
            'foto_var': bool(k.foto),
            'notlar': k.notlar or '',
            'kontrol_eden': k.kontrol_eden_id.name or '',
            'uyarilar': [u.display_name for u in k.uyari_ids],
        }

    @api.model
    def kalite_sonuc(self, kontrol_id, islem, degerler=None):
        """Mobil ekrandan kontrol sonucu.

        :param islem: gecti | kaldi | degerlendir
        :param degerler: {notlar, foto (base64), olcum, test_edilen, hatali, maddeler: {madde_id: uygun|uygun_degil}}
        """
        k = self._kontrol(kontrol_id)
        k._kontrol_acik()
        degerler = degerler or {}
        vals = {}
        if degerler.get('notlar') is not None:
            vals['notlar'] = degerler['notlar']
        if degerler.get('foto'):
            vals['foto'] = degerler['foto']
        if degerler.get('olcum') not in (None, ''):
            vals.update(olcum=float(degerler['olcum']), olcum_girildi=True)
        for alan in ('test_edilen', 'hatali'):
            if degerler.get(alan) not in (None, ''):
                vals[alan] = float(degerler[alan])
        if vals:
            k.write(vals)
        for madde_id, sonuc in (degerler.get('maddeler') or {}).items():
            k.madde_ids.filtered(lambda m: m.id == int(madde_id)).sonuc = sonuc or False
        if islem == 'gecti':
            k.action_gecti()
        elif islem == 'kaldi':
            k.action_kaldi()
        elif islem == 'degerlendir':
            k.action_degerlendir()
        else:
            raise UserError(self.env._('Tanımsız işlem: %s', islem))
        mesaj = self.env._('%(no)s: %(sonuc)s', no=k.name, sonuc=dict(k._fields['durum'].selection)[k.durum])
        if k.uyari_ids:
            mesaj += ' ' + self.env._('Uygunsuzluk açıldı: %s', ', '.join(k.uyari_ids.mapped('name')))
        return {'kontrol': self.kalite_ac(k.id), 'sonuc': 'ok' if k.durum == 'gecti' else 'uyari', 'mesaj': mesaj}
