import base64

from odoo import fields, models
from odoo.exceptions import UserError

from ..services import istemci


class AtlasAiOkunabilir(models.AbstractModel):
    """Ekindeki belgeden (PDF/görsel) yapay zekâyla doldurulabilen kayıtlar.

    Alt sınıf şunları sağlar: _atlas_ai_okuma() → (sistem istemi, araç şeması) ve _atlas_ai_uygula(sonuc).
    """
    _name = 'atlas.ai.okunabilir'
    _description = 'Yapay Zekâyla Okunabilir Kayıt'

    atlas_ai_durum = fields.Selection([('kuyrukta', 'Okunuyor'), ('okundu', 'AI ile dolduruldu'), ('hata', 'Okunamadı')],
                                      string='AI Okuma', copy=False, readonly=True)
    atlas_ai_guven = fields.Float(string='AI Güveni (%)', copy=False, readonly=True)
    atlas_ai_hata_mesaji = fields.Char(string='AI Hatası', copy=False, readonly=True)

    def _atlas_ai_dosya(self):
        """Okunacak dosya: ana ek ya da en son PDF/görsel eki → (içerik, mimetype, ad)."""
        self.ensure_one()
        ek = self.message_main_attachment_id if 'message_main_attachment_id' in self._fields else False
        if not ek:
            ek = self.env['ir.attachment'].search([('res_model', '=', self._name), ('res_id', '=', self.id),
                                                   ('mimetype', 'in', ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'])],
                                                  order='id desc', limit=1)
        if not ek:
            raise UserError(self.env._('Okunacak PDF ya da görsel eki yok.'))
        return ek.raw.content, ek.mimetype, ek.name

    def action_atlas_ai_oku(self):
        self.env['atlas.ai.istek'].kuyruga_al(self, 'oku')
        self.write({'atlas_ai_durum': 'kuyrukta', 'atlas_ai_hata_mesaji': False})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'info', 'message': self.env._('Belge yapay zekâyla okunmak üzere kuyruğa alındı.')}}

    def _atlas_belgeden_doldur(self):
        """Belgeler köprülerinin çağırdığı kanca: ayarlarda açıksa otomatik okumayı kuyruğa alır."""
        Ayar = self.env['atlas.ai.ayar']
        if Ayar.hazir() and Ayar._ayar('otomatik_oku'):
            self.action_atlas_ai_oku()

    def _atlas_ai_oku(self):
        self.ensure_one()
        icerik, mimetype, ad = self._atlas_ai_dosya()
        sistem, arac = self._atlas_ai_okuma()
        sonuc = self.env['atlas.ai.istek'].sor(sistem, [istemci.dosya_blogu(icerik, mimetype),
                                                        {'type': 'text', 'text': f'Dosya adı: {ad}'}], arac)
        self._atlas_ai_uygula(sonuc)
        guven = sonuc.get('guven')
        self.write({'atlas_ai_durum': 'okundu', 'atlas_ai_hata_mesaji': False,
                    'atlas_ai_guven': float(guven) if isinstance(guven, (int, float)) else 0.0})
        if hasattr(self, 'message_post'):
            self.message_post(body=self.env._('Belge yapay zekâyla okundu (güven %%%s). Lütfen değerleri kontrol edin.',
                                              round(self.atlas_ai_guven)))
        return sonuc

    def _atlas_ai_hata(self, mesaj):
        self.write({'atlas_ai_durum': 'hata', 'atlas_ai_hata_mesaji': (mesaj or '')[:250]})

    def _atlas_ai_okuma(self):
        raise NotImplementedError

    def _atlas_ai_uygula(self, sonuc):
        raise NotImplementedError
