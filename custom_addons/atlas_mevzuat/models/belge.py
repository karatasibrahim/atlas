from odoo import fields, models
from odoo.exceptions import UserError


class AtlasMevzuatBelge(models.Model):
    """Kaynakta bulunan bir duyuru/mevzuat öğesi ve son sürümünün içeriği."""
    _name = 'atlas.mevzuat.belge'
    _description = 'Mevzuat Belgesi'
    _order = 'yayim_tarihi desc, id desc'

    name = fields.Char(string='Başlık', required=True)
    kaynak_id = fields.Many2one('atlas.mevzuat.kaynak', string='Kaynak', required=True, ondelete='cascade', index=True)
    kurum = fields.Char(related='kaynak_id.kurum', store=True)
    dis_kimlik = fields.Char(string='Kaynak Kimliği', required=True, index=True)
    url = fields.Char(string='Adres')
    yayim_tarihi = fields.Date(string='Yayım Tarihi')
    kesif_tarihi = fields.Datetime(string='Keşif Tarihi', default=fields.Datetime.now, readonly=True)
    icerik = fields.Text(string='İçerik')
    oge_ozeti = fields.Char(string='Liste Özeti', readonly=True)
    icerik_ozeti = fields.Char(string='İçerik Özeti (SHA-256)', readonly=True, index=True)
    onceki_ozet = fields.Char(string='Önceki Özet', readonly=True)
    onceki_icerik = fields.Text(string='Önceki İçerik', readonly=True)
    surum = fields.Integer(string='Sürüm', default=1, readonly=True)
    durum = fields.Selection([('temel', 'Temel (ilk tarama)'), ('yeni', 'İşlendi'), ('ilgisiz', 'Kurala uymadı')],
                             string='Durum', default='yeni', readonly=True)
    degisiklik_ids = fields.One2many('atlas.mevzuat.degisiklik', 'belge_id', string='Değişiklikler')
    active = fields.Boolean(default=True)

    _kimlik_benzersiz = models.Constraint('unique(kaynak_id, dis_kimlik)', 'Bu öğe kaynakta zaten kayıtlı.')

    def _degisiklik_olustur(self, tur, onceki_metin=None, zorla=False):
        """Belge için değişiklik kaydı açar. Kaynak 'yalnız kurala uyanlar' ise kurala uymayan öğe atlanır."""
        self.ensure_one()
        return self.env['atlas.mevzuat.degisiklik']._belgeden_olustur(self, tur, onceki_metin, zorla)

    def action_degisiklik_olustur(self):
        self.ensure_one()
        if self.degisiklik_ids:
            raise UserError(self.env._('Bu belge için zaten değişiklik kaydı var.'))
        d = self._degisiklik_olustur('yeni', zorla=True)
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.mevzuat.degisiklik', 'res_id': d.id, 'view_mode': 'form'}
