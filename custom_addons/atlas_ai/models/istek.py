import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import istemci

_logger = logging.getLogger(__name__)


class AtlasAiIstek(models.Model):
    """Yapay zekâ istek kuyruğu ve günlüğü."""
    _name = 'atlas.ai.istek'
    _description = 'Yapay Zekâ İsteği'
    _order = 'id desc'

    name = fields.Char(string='İstek', compute='_compute_name', store=True)
    model = fields.Char(string='Model', required=True, index=True)
    res_id = fields.Integer(string='Kayıt No', required=True, index=True)
    kayit_adi = fields.Char(string='Kayıt')
    gorev = fields.Char(string='Görev', required=True)
    eylem_id = fields.Many2one('ir.actions.server', string='Sunucu Eylemi', ondelete='cascade')
    durum = fields.Selection([('bekliyor', 'Kuyrukta'), ('tamam', 'Tamamlandı'), ('hata', 'Hata')], string='Durum',
                             default='bekliyor', required=True, index=True)
    hata = fields.Text(string='Hata')
    sonuc = fields.Text(string='Sonuç (JSON)')
    giris_token = fields.Integer(string='Giriş Token')
    cikis_token = fields.Integer(string='Çıkış Token')
    sure_ms = fields.Integer(string='Süre (ms)')
    deneme = fields.Integer(string='Deneme')
    user_id = fields.Many2one('res.users', string='İsteyen', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('gorev', 'kayit_adi')
    def _compute_name(self):
        for i in self:
            i.name = f'{i.gorev}: {i.kayit_adi or i.model + "," + str(i.res_id)}'

    # ------------------------------------------------------------------ kuyruk
    @api.model
    def kuyruga_al(self, kayitlar, gorev, eylem=None):
        if not self.env['atlas.ai.ayar'].hazir():
            raise UserError(self.env._('Yapay zekâ kapalı ya da API anahtarı girilmemiş (Ayarlar > Yapay Zekâ).'))
        istekler = self.sudo().create([{'model': k._name, 'res_id': k.id, 'kayit_adi': (k.display_name or '')[:200], 'gorev': gorev,
                                        'eylem_id': eylem.id if eylem else False} for k in kayitlar])
        cron = self.env.ref('atlas_ai.ir_cron_ai_kuyruk', raise_if_not_found=False)
        if cron:
            cron._trigger()
        return istekler

    def _isle(self):
        """İstekleri sırayla işler (her biri ayrı kayıt noktasında)."""
        for istek in self:
            kayit = self.env[istek.model].browse(istek.res_id).exists() if istek.model in self.env else None
            istek.deneme += 1
            if not kayit:
                istek.write({'durum': 'hata', 'hata': self.env._('Kayıt artık yok')})
                continue
            try:
                with self.env.cr.savepoint():
                    if istek.gorev == 'eylem':
                        sonuc = istek.with_context(atlas_ai_istek_id=istek.id)._eylem_isle(kayit)
                    else:
                        isleyici = getattr(kayit.with_context(atlas_ai_istek_id=istek.id), f'_atlas_ai_{istek.gorev}')
                        sonuc = isleyici()
                istek.write({'durum': 'tamam', 'hata': False,
                             'sonuc': json.dumps(sonuc, ensure_ascii=False, default=str, indent=1) if sonuc is not None else False})
            except (istemci.AiHatasi, UserError) as e:
                istek.write({'durum': 'hata', 'hata': str(e)[:2000]})
                if hasattr(kayit, '_atlas_ai_hata'):
                    kayit._atlas_ai_hata(str(e))
            except Exception as e:  # beklenmeyen hata kuyruğu durdurmasın
                _logger.exception('Yapay zekâ isteği işlenemedi: %s', istek.name)
                istek.write({'durum': 'hata', 'hata': str(e)[:2000]})
                if hasattr(kayit, '_atlas_ai_hata'):
                    kayit._atlas_ai_hata(str(e))

    @api.model
    def _cron_isle(self):
        bekleyen = self.search([('durum', '=', 'bekliyor')], order='id', limit=50)
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(bekleyen))
        for istek in bekleyen:
            istek._isle()
            if not Cron._commit_progress(1):
                break

    def action_yeniden_dene(self):
        self.write({'durum': 'bekliyor', 'hata': False})
        self.env.ref('atlas_ai.ir_cron_ai_kuyruk')._trigger()

    def action_kayda_git(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.model, 'res_id': self.res_id, 'view_mode': 'form'}

    # ------------------------------------------------------------------ API çağrısı
    @api.model
    def sor(self, sistem, icerik, arac=None, en_fazla_token=4096):
        """Ayarlardaki anahtar/model ile sorar; kullanım bilgisi aktif isteğe yazılır."""
        Ayar = self.env['atlas.ai.ayar']
        if not Ayar._ayar('etkin'):
            raise istemci.AiHatasi('Yapay zekâ kapalı')
        sonuc, kullanim = istemci.sor(Ayar._ayar('anahtar'), Ayar._ayar('model'), sistem, icerik, arac, en_fazla_token,
                                      oturum=self.env.context.get('atlas_ai_oturum'))
        istek = self.browse(self.env.context.get('atlas_ai_istek_id')).exists()
        if istek:
            istek.write({'giris_token': istek.giris_token + kullanim['giris'], 'cikis_token': istek.cikis_token + kullanim['cikis'],
                         'sure_ms': istek.sure_ms + kullanim['sure_ms']})
        return sonuc

    # ------------------------------------------------------------------ AI sunucu eylemi
    def _eylem_isle(self, kayit):
        eylem = self.eylem_id
        alan = eylem.atlas_ai_alan_id
        if not alan:
            raise UserError(self.env._('Eylemde hedef alan seçilmemiş.'))
        f = kayit._fields[alan.name]
        sema, cevir = self._alan_semasi(kayit, f)
        istem = eylem._atlas_ai_istem_olustur(kayit)
        sistem = ('Sen bir ERP asistanısın. Kullanıcının talimatına göre tek bir alan değeri üret. '
                  f'Hedef alan: "{f.string}" ({f.type}). Yalnız "deger" aracını çağır.')
        sonuc = self.sor(sistem, istem, {'name': 'deger', 'description': f'"{f.string}" alanının yeni değeri',
                                         'input_schema': {'type': 'object', 'properties': {'deger': sema}, 'required': ['deger']}})
        deger = cevir(sonuc.get('deger'))
        kayit.write({alan.name: deger})
        return {'alan': alan.name, 'deger': sonuc.get('deger')}

    def _alan_semasi(self, kayit, f):
        """(json şeması, ham değer → alan değeri çevirici)"""
        if f.type in ('char', 'text', 'html'):
            return {'type': 'string'}, lambda v: v or False
        if f.type in ('integer',):
            return {'type': 'integer'}, lambda v: int(v or 0)
        if f.type in ('float', 'monetary'):
            return {'type': 'number'}, lambda v: float(v or 0)
        if f.type == 'boolean':
            return {'type': 'boolean'}, bool
        if f.type == 'date':
            return {'type': 'string', 'description': 'YYYY-AA-GG'}, lambda v: fields.Date.to_date(v) if v else False
        if f.type == 'selection':
            secenek = f._description_selection(self.env)
            return ({'type': 'string', 'enum': [k for k, _e in secenek], 'description': '; '.join(f'{k} = {e}' for k, e in secenek)},
                    lambda v: v if v in dict(secenek) else False)
        if f.type in ('many2one', 'many2many'):
            adaylar = self.env[f.comodel_name].search([], limit=200)
            adlar = {a.display_name: a.id for a in adaylar}
            if f.type == 'many2one':
                return {'type': 'string', 'enum': list(adlar)}, lambda v: adlar.get(v, False)
            return ({'type': 'array', 'items': {'type': 'string', 'enum': list(adlar)}},
                    lambda v: [(6, 0, [adlar[x] for x in (v or []) if x in adlar])])
        raise UserError(self.env._('Bu alan türü yapay zekâyla doldurulamaz: %s', f.type))
