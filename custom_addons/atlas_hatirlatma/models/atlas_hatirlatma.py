from collections import defaultdict

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_date


def _bool_arama(operator, value):
    """Boolean hesaplanmış alan araması: Odoo 20 '=' True'yu 'in' [True] olarak da iletebilir."""
    if operator in ('in', 'not in'):
        degerler = {value} if isinstance(value, (bool, int, str)) or value is None else set(value)
        sonuc = True in degerler
        return sonuc if operator == 'in' else not sonuc
    if operator in ('=', '!='):
        return bool(value) if operator == '=' else not bool(value)
    raise ValueError(operator)


class AtlasHatirlatmaSeviye(models.Model):
    _name = 'atlas.hatirlatma.seviye'
    _description = 'Ödeme Hatırlatma Seviyesi'
    _order = 'gun, id'

    name = fields.Char(string='Seviye', required=True)
    gun = fields.Integer(string='Vadeden Sonra (gün)', required=True,
                         help='Fatura vadesinden bu kadar gün geçince bu seviye uygulanır.')
    company_id = fields.Many2one('res.company', string='Şirket', help='Boşsa tüm şirketlerde geçerli.')
    eposta = fields.Boolean(string='E-posta Gönder', default=True)
    mektup = fields.Boolean(string='Mektup (PDF) Ekle')
    gorev = fields.Boolean(string='Sorumluya Görev Aç')
    gorev_ozet = fields.Char(string='Görev', default='Müşteriyi arayın')
    otomatik = fields.Boolean(string='Otomatik Gönder', help='Günlük görev bu seviyeye gelen carilere hatırlatmayı kendisi gönderir.')
    konu = fields.Char(string='E-posta Konusu', default='Vadesi geçmiş ödeme hatırlatması')
    mesaj = fields.Html(string='Mesaj', help='Kullanılabilir alanlar: {cari}, {tutar}, {gun}, {sirket}')
    active = fields.Boolean(default=True)

    _gun_uniq = models.UniqueIndex('(gun, company_id)', 'Aynı gün sayısıyla iki seviye olamaz.')

    @api.model
    def _seviyeler(self, company):
        return self.search([('company_id', 'in', (False, company.id))], order='gun')


class AtlasHatirlatmaGecmis(models.Model):
    _name = 'atlas.hatirlatma.gecmis'
    _description = 'Ödeme Hatırlatma Geçmişi'
    _order = 'tarih desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Cari', required=True, index=True, ondelete='cascade')
    seviye_id = fields.Many2one('atlas.hatirlatma.seviye', string='Seviye', ondelete='set null')
    tarih = fields.Datetime(string='Tarih', default=fields.Datetime.now, required=True)
    user_id = fields.Many2one('res.users', string='Gönderen', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    tutar = fields.Monetary(string='Gecikmiş Tutar', currency_field='currency_id')
    kanal = fields.Char(string='Kanal')
    line_ids = fields.Many2many('account.move.line', string='Hatırlatılan Kalemler')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    atlas_hatirlatma_seviye_id = fields.Many2one('atlas.hatirlatma.seviye', string='Son Hatırlatma Seviyesi', copy=False, readonly=True)
    atlas_hatirlatma_tarih = fields.Date(string='Son Hatırlatma', copy=False, readonly=True)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    atlas_hatirlatma_durdur = fields.Boolean(string='Hatırlatma Gönderme', company_dependent=True,
                                             help='Bu cariye ödeme hatırlatması gönderilmez (ör. yapılandırma görüşmesi sürüyor).')
    atlas_tahsilat_sorumlusu_id = fields.Many2one('res.users', string='Tahsilat Sorumlusu', company_dependent=True)
    atlas_gecikmis_tutar = fields.Monetary(string='Gecikmiş Tutar', compute='_compute_atlas_hatirlatma', currency_field='atlas_hatirlatma_currency_id')
    atlas_hatirlatma_currency_id = fields.Many2one('res.currency', compute='_compute_atlas_hatirlatma')
    atlas_en_eski_gecikme = fields.Integer(string='En Eski Gecikme (gün)', compute='_compute_atlas_hatirlatma')
    atlas_sonraki_seviye_id = fields.Many2one('atlas.hatirlatma.seviye', string='Sıradaki Hatırlatma', compute='_compute_atlas_hatirlatma')
    atlas_son_hatirlatma = fields.Datetime(string='Son Hatırlatma', compute='_compute_atlas_hatirlatma')
    atlas_hatirlatma_gerekli = fields.Boolean(string='Hatırlatma Gerekli', compute='_compute_atlas_hatirlatma',
                                              search='_search_atlas_hatirlatma_gerekli')
    atlas_gecikmis_var = fields.Boolean(string='Gecikmiş Alacak Var', compute='_compute_atlas_hatirlatma',
                                        search='_search_atlas_gecikmis_var')
    atlas_hatirlatma_gecmis_ids = fields.One2many('atlas.hatirlatma.gecmis', 'partner_id', string='Hatırlatma Geçmişi')

    # -------------------------------------------------------------------------
    # Gecikmiş kalemler
    # -------------------------------------------------------------------------

    @api.model
    def _atlas_gecikmis_domain(self, company):
        return [('company_id', '=', company.id), ('parent_state', '=', 'posted'),
                ('account_id.account_type', '=', 'asset_receivable'), ('reconciled', '=', False),
                ('amount_residual', '>', 0), ('date_maturity', '<', fields.Date.context_today(self))]

    @api.model
    def _atlas_gecikmis_gruplu(self, company, partners=None):
        domain = self._atlas_gecikmis_domain(company)
        if partners is not None:
            domain.append(('partner_id.commercial_partner_id', 'in', partners.commercial_partner_id.ids))
        gruplu = defaultdict(lambda: self.env['account.move.line'])
        for line in self.env['account.move.line'].search(domain, order='date_maturity'):
            gruplu[line.partner_id.commercial_partner_id] |= line
        return gruplu

    @api.model
    def _atlas_uygun_seviye(self, line, seviyeler, bugun):
        gecikme = (bugun - line.date_maturity).days
        uygun = seviyeler.filtered(lambda s: s.gun <= gecikme)
        return uygun[-1:] if uygun else seviyeler.browse()

    def _atlas_bekleyen(self, company=None, gruplu=None):
        """{partner: (bekleyen satırlar, uygulanacak seviye)} — hatırlatılacak cariler."""
        company = company or self.env.company
        gruplu = gruplu if gruplu is not None else self._atlas_gecikmis_gruplu(company, self)
        seviyeler = self.env['atlas.hatirlatma.seviye']._seviyeler(company)
        bugun = fields.Date.context_today(self)
        sonuc = {}
        for partner, lines in gruplu.items():
            if partner.with_company(company).atlas_hatirlatma_durdur:
                continue
            bekleyen, seviye = self.env['account.move.line'], seviyeler.browse()
            for line in lines:
                uygun = self._atlas_uygun_seviye(line, seviyeler, bugun)
                if uygun and (not line.atlas_hatirlatma_seviye_id or uygun.gun > line.atlas_hatirlatma_seviye_id.gun):
                    bekleyen |= line
                    if not seviye or uygun.gun > seviye.gun:
                        seviye = uygun
            if bekleyen:
                sonuc[partner] = (bekleyen, seviye)
        return sonuc

    def _compute_atlas_hatirlatma(self):
        company = self.env.company
        ticari = self.commercial_partner_id
        gruplu = self._atlas_gecikmis_gruplu(company, ticari)
        bekleyen = ticari._atlas_bekleyen(company, gruplu)
        bugun = fields.Date.context_today(self)
        son = dict(self.env['atlas.hatirlatma.gecmis']._read_group(
            [('partner_id', 'in', ticari.ids), ('company_id', '=', company.id)], ['partner_id'], ['tarih:max']))
        for partner in self:
            ticari_p = partner.commercial_partner_id
            lines = gruplu.get(ticari_p, self.env['account.move.line'])
            partner.atlas_hatirlatma_currency_id = company.currency_id
            partner.atlas_gecikmis_tutar = sum(lines.mapped('amount_residual'))
            partner.atlas_gecikmis_var = bool(lines)
            partner.atlas_en_eski_gecikme = max(((bugun - l.date_maturity).days for l in lines), default=0)
            partner.atlas_sonraki_seviye_id = bekleyen[ticari_p][1] if ticari_p in bekleyen else False
            partner.atlas_hatirlatma_gerekli = ticari_p in bekleyen
            partner.atlas_son_hatirlatma = son.get(ticari_p, False)

    def _search_atlas_hatirlatma_gerekli(self, operator, value):
        ids = [p.id for p in self.browse()._atlas_bekleyen(self.env.company, self._atlas_gecikmis_gruplu(self.env.company))]
        return [('id', 'in' if _bool_arama(operator, value) else 'not in', ids)]

    def _search_atlas_gecikmis_var(self, operator, value):
        ids = [p.id for p in self._atlas_gecikmis_gruplu(self.env.company)]
        return [('id', 'in' if _bool_arama(operator, value) else 'not in', ids)]

    # -------------------------------------------------------------------------
    # Gönderim
    # -------------------------------------------------------------------------

    def _atlas_rapor_satirlari(self):
        """Mektup ve e-postadaki gecikmiş kalem tablosu."""
        self.ensure_one()
        company = self.env.company
        bugun = fields.Date.context_today(self)
        lines = self._atlas_gecikmis_gruplu(company, self).get(self.commercial_partner_id, self.env['account.move.line'])
        return [{
            'belge': l.move_id.name, 'tarih': format_date(self.env, l.date), 'vade': format_date(self.env, l.date_maturity),
            'gecikme': (bugun - l.date_maturity).days,
            'tutar': format_amount(self.env, l.balance, company.currency_id),
            'kalan': format_amount(self.env, l.amount_residual, company.currency_id),
        } for l in lines]

    def _atlas_hatirlatma_rapor(self):
        self.ensure_one()
        company = self.env.company
        lines = self._atlas_gecikmis_gruplu(company, self).get(self.commercial_partner_id, self.env['account.move.line'])
        return {'satirlar': self._atlas_rapor_satirlari(),
                'toplam': format_amount(self.env, sum(lines.mapped('amount_residual')), company.currency_id),
                'bankalar': [(j.bank_name or j.name, j.bank_account_number) for j in self.env['account.journal'].search(
                    [('type', '=', 'bank'), ('company_id', '=', company.id), ('bank_account_number', '!=', False)])]}

    def _atlas_mesaj(self, seviye, tutar, gun):
        self.ensure_one()
        degerler = defaultdict(str, cari=escape(self.name), sirket=escape(self.env.company.name),
                               tutar=format_amount(self.env, tutar, self.env.company.currency_id), gun=gun)
        govde = str(seviye.mesaj or '').format_map(degerler) if seviye.mesaj else ''
        satirlar = ''.join(
            f'<tr><td>{escape(s["belge"])}</td><td>{s["vade"]}</td><td style="text-align:right">{s["gecikme"]}</td>'
            f'<td style="text-align:right">{s["kalan"]}</td></tr>' for s in self._atlas_rapor_satirlari())
        tablo = ('<table border="1" cellpadding="4" style="border-collapse:collapse">'
                 '<tr><th>Belge</th><th>Vade</th><th>Gecikme (gün)</th><th>Kalan</th></tr>' + satirlar + '</table>')
        return Markup(govde + tablo)

    def _atlas_hatirlatma_gonder(self, bekleyen):
        """bekleyen: {partner: (satırlar, seviye)}"""
        company = self.env.company
        rapor = self.env.ref('atlas_hatirlatma.action_report_hatirlatma')
        bugun = fields.Date.context_today(self)
        gonderilen = self.browse()
        for partner, (lines, seviye) in bekleyen.items():
            tutar = sum(self._atlas_gecikmis_gruplu(company, partner).get(partner, lines).mapped('amount_residual'))
            gun = max((bugun - l.date_maturity).days for l in lines)
            kanallar = []
            if seviye.eposta:
                if not partner.email:
                    partner.message_post(body=self.env._('%s gönderilemedi: e-posta adresi yok.', seviye.name))
                else:
                    ekler = []
                    if seviye.mektup:
                        pdf, _tip = self.env['ir.actions.report']._render_qweb_pdf(rapor, partner.ids)
                        ekler.append((f'Odeme_Hatirlatma_{partner.ref or partner.id}.pdf', pdf))
                    partner.message_post(body=partner._atlas_mesaj(seviye, tutar, gun), subject=seviye.konu or seviye.name,
                                         partner_ids=partner.ids, attachments=ekler,
                                         message_type='comment', subtype_xmlid='mail.mt_comment')
                    kanallar.append(self.env._('e-posta'))
            elif seviye.mektup:
                kanallar.append(self.env._('mektup'))
            if seviye.gorev:
                sorumlu = partner.with_company(company).atlas_tahsilat_sorumlusu_id or self.env.user
                partner.activity_schedule('mail.mail_activity_data_todo', user_id=sorumlu.id,
                                          summary=f'{seviye.name}: {seviye.gorev_ozet or ""}',
                                          note=self.env._('Gecikmiş alacak: %s', format_amount(self.env, tutar, company.currency_id)))
                kanallar.append(self.env._('görev'))
            # Her kalem kendi gecikmesine uyan seviyeyle işaretlenir (yeni seviyeye gelince tekrar hatırlatılır)
            seviyeler = self.env['atlas.hatirlatma.seviye']._seviyeler(company)
            for line in lines:
                line.write({'atlas_hatirlatma_seviye_id': self._atlas_uygun_seviye(line, seviyeler, bugun).id,
                            'atlas_hatirlatma_tarih': bugun})
            self.env['atlas.hatirlatma.gecmis'].create({
                'partner_id': partner.id, 'seviye_id': seviye.id, 'company_id': company.id, 'tutar': tutar,
                'kanal': ', '.join(kanallar), 'line_ids': [(6, 0, lines.ids)]})
            gonderilen |= partner
        return gonderilen

    def action_atlas_hatirlatma_gonder(self):
        bekleyen = self.commercial_partner_id._atlas_bekleyen(self.env.company)
        if not bekleyen:
            raise UserError(self.env._('Seçili carilerde hatırlatılacak gecikmiş alacak yok.'))
        gonderilen = self._atlas_hatirlatma_gonder(bekleyen)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'message': self.env._('%s cariye ödeme hatırlatması gönderildi.', len(gonderilen)), 'type': 'success',
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def action_atlas_hatirlatma_mektup(self):
        return self.env.ref('atlas_hatirlatma.action_report_hatirlatma').report_action(self.commercial_partner_id)

    def action_atlas_gecikmis_kalemler(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move.line', 'name': self.env._('Gecikmiş Alacaklar'),
                'view_mode': 'list', 'domain': self._atlas_gecikmis_domain(self.env.company)
                + [('partner_id.commercial_partner_id', '=', self.commercial_partner_id.id)]}

    @api.model
    def _cron_atlas_hatirlatma(self):
        for company in self.env['res.company'].search([]):
            Partner = self.with_company(company)
            bekleyen = Partner.browse()._atlas_bekleyen(company, Partner._atlas_gecikmis_gruplu(company))
            otomatik = {p: v for p, v in bekleyen.items() if v[1].otomatik}
            if otomatik:
                Partner._atlas_hatirlatma_gonder(otomatik)
