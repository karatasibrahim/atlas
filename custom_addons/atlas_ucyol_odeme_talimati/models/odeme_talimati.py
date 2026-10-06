from odoo import api, fields, models
from odoo.exceptions import UserError


def _engelli(faturalar):
    """3'lü eşleştirmede ödenemeyecek faturalar (şirkette ödeme engeli açıksa)."""
    return faturalar.filtered(lambda m: m.company_id.ucyol_odeme_engeli and m.move_type in ('in_invoice', 'in_refund')
                              and m.ucyol_durum != 'evet')


class AtlasOdemeTalimatSatir(models.Model):
    _inherit = 'atlas.odeme.talimat.satir'

    move_ids = fields.Many2many(domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), "
                                       "('payment_state', 'in', ('not_paid', 'partial')), "
                                       "('commercial_partner_id', '=', commercial_partner_id), "
                                       "'|', ('ucyol_durum', '=', 'evet'), ('company_id.ucyol_odeme_engeli', '=', False)]")
    ucyol_durum = fields.Selection([('evet', 'Ödenebilir'), ('hayir', 'Teslimat bekleniyor'), ('istisna', 'İstisna')],
                                   string='3\'lü Eşleştirme', compute='_compute_ucyol_durum')

    @api.depends('move_ids.ucyol_durum')
    def _compute_ucyol_durum(self):
        for s in self:
            durumlar = set(s.move_ids.mapped('ucyol_durum')) - {False}
            s.ucyol_durum = ('istisna' if 'istisna' in durumlar else 'hayir' if 'hayir' in durumlar else 'evet') if durumlar else False


class AtlasOdemeTalimat(models.Model):
    _inherit = 'atlas.odeme.talimat'

    def _kontrol(self):
        super()._kontrol()
        engelli = _engelli(self.satir_ids.move_ids)
        if engelli:
            raise UserError(self.env._(
                'Talimat onaylanamadı: şu faturalar 3\'lü eşleştirmede ödenebilir değil:\n- %s\n'
                'Mal kabulünü bekleyin, faturayı elle ödemeye serbest bırakın ya da talimattan çıkarın.',
                '\n- '.join(f'{m.name} ({dict(m._fields["ucyol_durum"].selection).get(m.ucyol_durum)})' for m in engelli)))


class AtlasOdemeTalimatEkle(models.TransientModel):
    _inherit = 'atlas.odeme.talimat.ekle'

    def action_ekle(self):
        engelli = _engelli(self.move_ids)
        if engelli and engelli == self.move_ids:
            raise UserError(self.env._('Seçilen faturaların hiçbiri 3\'lü eşleştirmede ödenebilir değil: %s', ', '.join(engelli.mapped('name'))))
        self.move_ids -= engelli
        sonuc = super().action_ekle()
        if engelli:
            talimat = self.env['atlas.odeme.talimat'].browse(sonuc.get('res_id'))
            talimat.message_post(body=self.env._('3\'lü eşleştirmede ödenebilir olmadığı için eklenmeyen faturalar: %s',
                                                 ', '.join(engelli.mapped('name'))))
        return sonuc
