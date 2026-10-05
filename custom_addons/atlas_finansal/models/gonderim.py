import base64
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AtlasFinansalGonderim(models.Model):
    """Raporun dönemsel olarak e-postayla gönderilmesi."""
    _name = 'atlas.finansal.gonderim'
    _description = 'Finansal Rapor Otomatik Gönderimi'
    _order = 'sonraki_tarih, id'

    name = fields.Char(string='Ad', compute='_compute_name', store=True)
    rapor_id = fields.Many2one('atlas.finansal.rapor', string='Rapor', required=True, ondelete='cascade')
    alici_ids = fields.Many2many('res.partner', string='Alıcılar', required=True)
    siklik = fields.Selection([('haftalik', 'Haftalık'), ('aylik', 'Aylık'), ('ceyreklik', 'Çeyreklik'), ('yillik', 'Yıllık')],
                              string='Sıklık', default='aylik', required=True)
    donem = fields.Selection([('onceki_ay', 'Önceki ay'), ('bu_ay', 'Bu ay (bugüne kadar)'), ('onceki_ceyrek', 'Önceki çeyrek'),
                              ('bu_yil', 'Bu yıl (bugüne kadar)'), ('onceki_yil', 'Önceki yıl')], string='Raporlanan Dönem',
                             default='onceki_ay', required=True)
    karsilastir = fields.Boolean(string='Önceki Dönemle Karşılaştır')
    bicim = fields.Selection([('xlsx', 'Excel'), ('pdf', 'PDF')], string='Biçim', default='xlsx', required=True)
    sonraki_tarih = fields.Date(string='Sonraki Gönderim', required=True, default=fields.Date.context_today)
    son_gonderim = fields.Datetime(string='Son Gönderim', readonly=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    @api.depends('rapor_id', 'siklik')
    def _compute_name(self):
        siklik = dict(self._fields['siklik'].selection)
        for g in self:
            g.name = f'{g.rapor_id.name or ""} — {siklik.get(g.siklik, "")}'

    def _donem_tarihleri(self, bugun):
        if self.donem == 'onceki_ay':
            bas = bugun.replace(day=1) - relativedelta(months=1)
            return bas, bugun.replace(day=1) - timedelta(days=1)
        if self.donem == 'bu_ay':
            return bugun.replace(day=1), bugun
        if self.donem == 'onceki_ceyrek':
            ceyrek_bas = bugun.replace(month=(bugun.month - 1) // 3 * 3 + 1, day=1)
            return ceyrek_bas - relativedelta(months=3), ceyrek_bas - timedelta(days=1)
        if self.donem == 'onceki_yil':
            return bugun.replace(year=bugun.year - 1, month=1, day=1), bugun.replace(year=bugun.year - 1, month=12, day=31)
        return bugun.replace(month=1, day=1), bugun

    def _sonraki(self, tarih):
        return tarih + {'haftalik': relativedelta(weeks=1), 'aylik': relativedelta(months=1), 'ceyreklik': relativedelta(months=3),
                        'yillik': relativedelta(years=1)}[self.siklik]

    def _gonder(self):
        self.ensure_one()
        bugun = fields.Date.context_today(self)
        bas, bit = self._donem_tarihleri(bugun)
        secenekler = {'tarih_bas': fields.Date.to_string(bas), 'tarih_bit': fields.Date.to_string(bit), 'sifir_gizle': True,
                      'karsilastirma': {'tur': 'onceki', 'adet': 1} if self.karsilastir else {'tur': 'yok'}}
        rapor = self.rapor_id.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        if self.bicim == 'pdf':
            icerik, _t = self.env['ir.actions.report']._render_qweb_pdf('atlas_finansal.action_report_finansal', rapor.ids,
                                                                         data={'rapor_id': rapor.id, 'secenekler': secenekler})
            ad, tip = f'{rapor.name} {bit}.pdf', 'application/pdf'
        else:
            ad, icerik = rapor.xlsx_olustur(secenekler)
            tip = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ek = self.env['ir.attachment'].create({'name': ad, 'datas': base64.b64encode(icerik), 'mimetype': tip,
                                               'res_model': self._name, 'res_id': self.id})
        mail = self.env['mail.mail'].sudo().create({
            'subject': f'{rapor.name} — {bas.strftime("%d.%m.%Y")} / {bit.strftime("%d.%m.%Y")}',
            'body_html': f'<p>{self.company_id.name} {rapor.name} raporu ektedir.</p>'
                         f'<p>Dönem: {bas.strftime("%d.%m.%Y")} – {bit.strftime("%d.%m.%Y")}</p>',
            'recipient_ids': [(6, 0, self.alici_ids.ids)],
            'attachment_ids': [(4, ek.id)],
            'auto_delete': True,
        })
        self.write({'son_gonderim': fields.Datetime.now(), 'sonraki_tarih': self._sonraki(max(self.sonraki_tarih, bugun))})
        return mail

    def action_simdi_gonder(self):
        for g in self:
            g._gonder()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('Rapor e-posta kuyruğuna alındı.')}}

    @api.model
    def _cron_gonder(self):
        bugun = fields.Date.context_today(self)
        gonderimler = self.search([('sonraki_tarih', '<=', bugun)])
        self.env['ir.cron']._commit_progress(remaining=len(gonderimler))
        for g in gonderimler:
            try:
                with self.env.cr.savepoint():
                    g._gonder()
            except Exception:  # bir raporun hatası diğerlerini durdurmasın
                import logging
                logging.getLogger(__name__).exception('Finansal rapor gönderilemedi: %s', g.name)
            if not self.env['ir.cron']._commit_progress(1):
                break
