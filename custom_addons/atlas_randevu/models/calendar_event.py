from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

DURUMLAR = [('talep', 'Talep'), ('onayli', 'Onaylandı'), ('geldi', 'Geldi'), ('gelmedi', 'Gelmedi'), ('iptal', 'İptal')]


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    randevu_tur_id = fields.Many2one('atlas.randevu.tur', string='Randevu Türü', index='btree_not_null', ondelete='set null')
    randevu_durum = fields.Selection(DURUMLAR, string='Randevu Durumu', tracking=True, index='btree_not_null')
    randevu_musteri_id = fields.Many2one('res.partner', string='Randevuyu Alan')
    randevu_kisi = fields.Integer(string='Kişi Sayısı', default=1)
    randevu_kaynak_ids = fields.Many2many('atlas.randevu.kaynak', string='Kaynaklar')
    randevu_davet_id = fields.Many2one('atlas.randevu.davet', string='Davet Bağlantısı', ondelete='set null')
    randevu_yanit_ids = fields.One2many('atlas.randevu.yanit', 'etkinlik_id', string='Yanıtlar')
    randevu_rezervasyon_ids = fields.One2many('atlas.randevu.rezervasyon', 'etkinlik_id', string='Rezervasyonlar')

    def _randevu_kontrol(self):
        if any(not e.randevu_tur_id for e in self):
            raise UserError(self.env._('Bu işlem yalnız randevular için geçerlidir.'))

    def action_randevu_onayla(self):
        self._randevu_kontrol()
        for e in self.filtered(lambda e: e.randevu_durum == 'talep'):
            e.randevu_durum = 'onayli'
            sablon = e.randevu_tur_id.onay_sablon_id
            if sablon and e.randevu_musteri_id.email:
                sablon.sudo().send_mail(e.id, force_send=False, email_values={'email_to': e.randevu_musteri_id.email, 'recipient_ids': []})
            e.activity_ids.filtered(lambda a: a.activity_type_id == self.env.ref('mail.mail_activity_data_todo')).action_feedback(
                feedback=self.env._('Onaylandı'))
        return True

    def action_randevu_geldi(self):
        self._randevu_kontrol()
        self.write({'randevu_durum': 'geldi'})
        return True

    def action_randevu_gelmedi(self):
        self._randevu_kontrol()
        self.write({'randevu_durum': 'gelmedi'})
        return True

    def action_randevu_iptal(self):
        self._randevu_kontrol()
        for e in self.filtered(lambda e: e.randevu_durum != 'iptal'):
            e.write({'randevu_durum': 'iptal', 'show_as': 'free'})
            sablon = e.randevu_tur_id.iptal_sablon_id
            if sablon and e.randevu_musteri_id.email:
                sablon.sudo().send_mail(e.id, force_send=False, email_values={'email_to': e.randevu_musteri_id.email, 'recipient_ids': []})
        return True

    def _randevu_iptal_edilebilir(self):
        self.ensure_one()
        if self.randevu_durum in ('iptal', 'geldi', 'gelmedi'):
            return False
        return self.start - timedelta(hours=self.randevu_tur_id.min_iptal_saat) > fields.Datetime.now()

    def _randevu_url(self):
        self.ensure_one()
        taban = self.env['ir.config_parameter'].sudo().get_str('web.base.url') or ''
        return f'{taban}/randevu/etkinlik/{self.id}/{self._calendar_event_ensure_token()}'

    def _randevu_ics(self):
        self.ensure_one()
        bicim = '%Y%m%dT%H%M%SZ'
        satirlar = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Atlas//Randevu//TR', 'BEGIN:VEVENT',
                    f'UID:atlas-randevu-{self.id}@{(self.env["ir.config_parameter"].sudo().get_str("web.base.url") or "atlas").split("//")[-1]}',
                    f'DTSTAMP:{fields.Datetime.now().strftime(bicim)}', f'DTSTART:{self.start.strftime(bicim)}',
                    f'DTEND:{self.stop.strftime(bicim)}', f'SUMMARY:{self.name}']
        if self.location:
            satirlar.append(f'LOCATION:{self.location}')
        if self.videocall_location:
            satirlar.append(f'URL:{self.videocall_location}')
        satirlar += ['END:VEVENT', 'END:VCALENDAR']
        return '\r\n'.join(s.replace('\n', ' ') for s in satirlar) + '\r\n'

    @api.model
    def _randevu_durum_rengi(self):
        return {'talep': 3, 'onayli': 10, 'geldi': 4, 'gelmedi': 1, 'iptal': 0}
