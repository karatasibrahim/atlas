import calendar
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import format_amount

from odoo.addons.atlas_rapor.wizard.atlas_rapor_wizard import col

AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
AY_ALANLARI = [f'ay{i:02d}' for i in range(1, 13)]
# Alacak bakiyeli (gelir) hesap grupları: gerçekleşen = -bakiye
ALACAK_ONEKLERI = ('60', '64', '67')


class AtlasButce(models.Model):
    _name = 'atlas.butce'
    _description = 'Bütçe'
    _inherit = ['mail.thread']
    _order = 'yil desc, name'

    name = fields.Char(string='Bütçe', required=True, tracking=True)
    yil = fields.Integer(string='Yıl', required=True, default=lambda self: fields.Date.context_today(self).year, tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analitik Hesap',
                                          help='Proje / departman bütçesi: yalnızca bu analitik hesaba dağıtılan hareketler sayılır.')
    durum = fields.Selection([('taslak', 'Taslak'), ('onaylandi', 'Onaylandı'), ('kapali', 'Kapalı')], string='Durum',
                             default='taslak', required=True, tracking=True)
    asim_kontrolu = fields.Selection([('yok', 'Kontrol yok'), ('uyari', 'Uyarı ver'), ('engelle', 'Engelle')],
                                     string='Aşım Kontrolü', default='uyari', required=True,
                                     help='Onaylı bütçede gider kalemi yıllık tutarı aşılırsa fatura / fiş onayında uyarır veya engeller.')
    satir_ids = fields.One2many('atlas.butce.satir', 'butce_id', string='Kalemler', copy=True)
    plan_toplam = fields.Monetary(string='Bütçe Toplamı', compute='_compute_toplamlar', currency_field='currency_id')
    gerceklesen_toplam = fields.Monetary(string='Gerçekleşen', compute='_compute_toplamlar', currency_field='currency_id')
    notlar = fields.Html(string='Notlar')
    kaynak_yil = fields.Integer(string='Kaynak Yıl', help='"Gerçekleşenden Doldur" için kullanılacak yıl (boşsa önceki yıl).')
    artis_orani = fields.Float(string='Artış Oranı (%)', help='Kaynak yılın gerçekleşenine eklenecek oran (enflasyon vb.).')

    _yil_aralik = models.Constraint('CHECK(yil BETWEEN 2000 AND 2100)', 'Geçersiz bütçe yılı.')

    @api.depends('satir_ids.toplam', 'satir_ids.gerceklesen')
    def _compute_toplamlar(self):
        for butce in self:
            butce.plan_toplam = sum(butce.satir_ids.mapped('toplam'))
            butce.gerceklesen_toplam = sum(butce.satir_ids.mapped('gerceklesen'))

    def action_onayla(self):
        for butce in self:
            if not butce.satir_ids:
                raise UserError(self.env._('%s bütçesinde kalem yok.', butce.name))
        self.write({'durum': 'onaylandi'})
        return True

    def action_taslak(self):
        self.write({'durum': 'taslak'})
        return True

    def action_kapat(self):
        self.write({'durum': 'kapali'})
        return True

    def action_sonraki_yil(self):
        self.ensure_one()
        yeni = self.copy({'name': self.name.replace(str(self.yil), str(self.yil + 1)) if str(self.yil) in self.name
                          else f'{self.name} ({self.yil + 1})', 'yil': self.yil + 1, 'durum': 'taslak'})
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.butce', 'res_id': yeni.id, 'view_mode': 'form'}

    def action_gerceklesenden_doldur(self):
        """Kaynak yılın aylık gerçekleşenini artış oranıyla plana yazar."""
        for butce in self:
            if butce.durum != 'taslak':
                raise UserError(self.env._('Yalnızca taslak bütçe doldurulabilir.'))
            kaynak = butce.kaynak_yil or butce.yil - 1
            carpan = 1 + (butce.artis_orani or 0.0) / 100.0
            for satir in butce.satir_ids:
                aylik = satir._gerceklesen_aylik(kaynak)
                satir.write({alan: butce.currency_id.round(aylik[i] * carpan) for i, alan in enumerate(AY_ALANLARI)})
        return True

    def action_rapor(self):
        self.ensure_one()
        wizard = self.env['atlas.rapor.wizard'].create({
            'rapor_turu': 'butce', 'butce_id': self.id, 'company_id': self.company_id.id,
            'date_from': date(self.yil, 1, 1), 'date_to': date(self.yil, 12, 31)})
        return wizard.action_html()


class AtlasButceSatir(models.Model):
    _name = 'atlas.butce.satir'
    _description = 'Bütçe Kalemi'
    _order = 'butce_id, sequence, hesap_kodu'

    butce_id = fields.Many2one('atlas.butce', string='Bütçe', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='butce_id.company_id', store=True)
    currency_id = fields.Many2one(related='butce_id.currency_id')
    sequence = fields.Integer(default=10)
    hesap_kodu = fields.Char(string='Hesap Kodu', required=True, help='Hesap kodu veya öneki (ör. 770, 770001, 60).')
    name = fields.Char(string='Kalem', compute='_compute_name', store=True, readonly=False, precompute=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analitik Hesap',
                                          help='Boşsa bütçenin analitik hesabı kullanılır.')
    yon = fields.Selection([('borc', 'Gider / Borç'), ('alacak', 'Gelir / Alacak')], string='Yön',
                           compute='_compute_yon', store=True, readonly=False, required=True, precompute=True)
    ay01 = fields.Monetary(string='Oca', currency_field='currency_id')
    ay02 = fields.Monetary(string='Şub', currency_field='currency_id')
    ay03 = fields.Monetary(string='Mar', currency_field='currency_id')
    ay04 = fields.Monetary(string='Nis', currency_field='currency_id')
    ay05 = fields.Monetary(string='May', currency_field='currency_id')
    ay06 = fields.Monetary(string='Haz', currency_field='currency_id')
    ay07 = fields.Monetary(string='Tem', currency_field='currency_id')
    ay08 = fields.Monetary(string='Ağu', currency_field='currency_id')
    ay09 = fields.Monetary(string='Eyl', currency_field='currency_id')
    ay10 = fields.Monetary(string='Eki', currency_field='currency_id')
    ay11 = fields.Monetary(string='Kas', currency_field='currency_id')
    ay12 = fields.Monetary(string='Ara', currency_field='currency_id')
    toplam = fields.Monetary(string='Yıllık Bütçe', compute='_compute_toplam', store=True, currency_field='currency_id')
    gerceklesen = fields.Monetary(string='Gerçekleşen', compute='_compute_gerceklesen', currency_field='currency_id')
    fark = fields.Monetary(string='Kalan / Fark', compute='_compute_gerceklesen', currency_field='currency_id')
    oran = fields.Float(string='Gerçekleşme (%)', compute='_compute_gerceklesen')

    @api.constrains('hesap_kodu')
    def _check_hesap_kodu(self):
        for satir in self:
            if not (satir.hesap_kodu or '').isdigit():
                raise ValidationError(self.env._('Hesap kodu yalnızca rakamlardan oluşmalı: %s', satir.hesap_kodu))

    @api.depends('hesap_kodu', 'butce_id.company_id')
    def _compute_name(self):
        for satir in self:
            if satir.name or not satir.hesap_kodu:
                continue
            company = satir.butce_id.company_id or self.env.company
            hesap = self.env['account.account'].with_company(company).search(
                [('company_ids', 'in', company.root_id.id), ('code', '=like', satir.hesap_kodu + '%')], order='code', limit=1)
            satir.name = hesap.name if hesap else satir.hesap_kodu

    @api.depends('hesap_kodu')
    def _compute_yon(self):
        for satir in self:
            satir.yon = 'alacak' if (satir.hesap_kodu or '').startswith(ALACAK_ONEKLERI) else 'borc'

    @api.depends(*AY_ALANLARI)
    def _compute_toplam(self):
        for satir in self:
            satir.toplam = sum(satir[a] for a in AY_ALANLARI)

    def _analitik(self):
        return self.analytic_account_id or self.butce_id.analytic_account_id

    def _domain(self, date_from, date_to):
        self.ensure_one()
        domain = [('company_id', '=', self.butce_id.company_id.id), ('parent_state', '=', 'posted'),
                  ('account_id.code', '=like', self.hesap_kodu + '%'),
                  ('date', '>=', date_from), ('date', '<=', date_to),
                  ('move_id.atlas_fis_turu', 'not in', ['kapanis'])]
        if self._analitik():
            domain.append(('analytic_distribution', 'in', self._analitik().ids))
        return domain

    def _isaret(self):
        return -1 if self.yon == 'alacak' else 1

    def _gerceklesen_tutar(self, date_from, date_to):
        self.ensure_one()
        veri = self.env['account.move.line']._read_group(self._domain(date_from, date_to), [], ['balance:sum'])
        return self._isaret() * (veri[0][0] or 0.0)

    def _gerceklesen_aylik(self, yil=None):
        self.ensure_one()
        yil = yil or self.butce_id.yil
        veri = self.env['account.move.line']._read_group(
            self._domain(date(yil, 1, 1), date(yil, 12, 31)), ['date:month'], ['balance:sum'])
        aylik = [0.0] * 12
        for ay, tutar in veri:
            aylik[ay.month - 1] += self._isaret() * tutar
        return aylik

    def _plan(self, date_from, date_to):
        """Tarih aralığına düşen ayların plan toplamı."""
        self.ensure_one()
        yil = self.butce_id.yil
        return sum(self[AY_ALANLARI[m - 1]] for m in range(1, 13)
                   if date(yil, m, 1) <= date_to and date(yil, m, calendar.monthrange(yil, m)[1]) >= date_from)

    @api.depends('toplam', 'hesap_kodu', 'yon', 'analytic_account_id', 'butce_id.yil')
    def _compute_gerceklesen(self):
        for satir in self:
            if not satir.hesap_kodu or not satir.butce_id.yil or not satir.butce_id.company_id:
                satir.gerceklesen = satir.fark = satir.oran = 0.0
                continue
            yil = satir.butce_id.yil
            satir.gerceklesen = satir._gerceklesen_tutar(date(yil, 1, 1), date(yil, 12, 31))
            satir.fark = satir.toplam - satir.gerceklesen
            satir.oran = 100.0 * satir.gerceklesen / satir.toplam if satir.toplam else 0.0


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._atlas_butce_kontrol()
        return posted

    def _atlas_butce_kontrol(self):
        Satir = self.env['atlas.butce.satir']
        for move in self:
            satirlar = Satir.search([('butce_id.durum', '=', 'onaylandi'), ('butce_id.yil', '=', move.date.year),
                                     ('company_id', '=', move.company_id.id), ('yon', '=', 'borc'),
                                     ('butce_id.asim_kontrolu', '!=', 'yok')])
            if not satirlar:
                continue
            ilgili = Satir
            for line in move.line_ids.filtered(lambda l: l.balance > 0):
                kod = line.account_id.code or ''
                for satir in satirlar.filtered(lambda s: kod.startswith(s.hesap_kodu)):
                    analitik = satir._analitik()
                    if analitik and str(analitik.id) not in (line.analytic_distribution or {}):
                        continue
                    ilgili |= satir
            for satir in ilgili:
                yil = satir.butce_id.yil
                gerceklesen = satir._gerceklesen_tutar(date(yil, 1, 1), date(yil, 12, 31))
                if satir.currency_id.compare_amounts(gerceklesen, satir.toplam) <= 0:
                    continue
                mesaj = self.env._(
                    'Bütçe aşımı: %(butce)s / %(kalem)s (%(kod)s) — yıllık bütçe %(plan)s, gerçekleşen %(gercek)s.',
                    butce=satir.butce_id.name, kalem=satir.name, kod=satir.hesap_kodu,
                    plan=format_amount(self.env, satir.toplam, satir.currency_id),
                    gercek=format_amount(self.env, gerceklesen, satir.currency_id))
                if satir.butce_id.asim_kontrolu == 'engelle':
                    raise UserError(mesaj)
                move.message_post(body=mesaj)


class AtlasRaporWizard(models.TransientModel):
    _inherit = 'atlas.rapor.wizard'

    rapor_turu = fields.Selection(selection_add=[('butce', 'Bütçe - Gerçekleşen')], ondelete={'butce': 'cascade'})
    butce_id = fields.Many2one('atlas.butce', string='Bütçe')

    def _period_label(self):
        if self.rapor_turu == 'butce':
            return f'{self.butce_id.name} — ' + super()._period_label()
        return super()._period_label()

    def _report_butce(self):
        self._require_date_from()
        butce = self.butce_id
        if not butce:
            raise UserError(self.env._('Bir bütçe seçin.'))
        if self.date_from.year != butce.yil or self.date_to.year != butce.yil:
            raise UserError(self.env._('Tarih aralığı bütçe yılı (%s) içinde olmalı.', butce.yil))
        rows, toplam = [], {'borc': [0.0, 0.0], 'alacak': [0.0, 0.0]}
        for yon, baslik in (('alacak', 'GELİRLER'), ('borc', 'GİDERLER')):
            satirlar = butce.satir_ids.filtered(lambda s: s.yon == yon)
            if not satirlar:
                continue
            rows.append(self._row(['', baslik, None, None, None, None], 'group'))
            for satir in satirlar:
                plan = satir._plan(self.date_from, self.date_to)
                gercek = satir._gerceklesen_tutar(self.date_from, self.date_to)
                if self.sadece_hareketli and not plan and not gercek:
                    continue
                toplam[yon][0] += plan
                toplam[yon][1] += gercek
                rows.append(self._row([satir.hesap_kodu, satir.name, plan, gercek, gercek - plan,
                                       round(100.0 * gercek / plan, 1) if plan else None]))
            p, g = toplam[yon]
            rows.append(self._row(['', f'TOPLAM {baslik}', p, g, g - p, round(100.0 * g / p, 1) if p else None], 'total'))
        if toplam['alacak'][0] or toplam['alacak'][1]:
            p = toplam['alacak'][0] - toplam['borc'][0]
            g = toplam['alacak'][1] - toplam['borc'][1]
            rows.append(self._row(['', 'NET (GELİR - GİDER)', p, g, g - p, None], 'total'))
        return {
            'title': 'Bütçe - Gerçekleşen',
            'columns': [col('Hesap', 'text', 12), col('Kalem', 'text', 36), col('Bütçe', 'money', 15),
                        col('Gerçekleşen', 'money', 15), col('Fark', 'money', 15), col('Gerçekleşme %', 'number', 12)],
            'rows': rows,
        }
