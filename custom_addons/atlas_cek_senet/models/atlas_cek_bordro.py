from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .atlas_cek_islem import DURUM_SELECTION, ISLEM_SELECTION, ISLEMLER


class AtlasCekBordro(models.Model):
    """Çek/senet bordrosu: bir işlemde (giriş, ciro, tahsil...) birden çok evrak ve tek muhasebe fişi."""
    _name = 'atlas.cek.bordro'
    _description = 'Çek / Senet Bordrosu'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Bordro No', readonly=True, copy=False, default='/')
    islem = fields.Selection(ISLEM_SELECTION, string='İşlem', required=True, tracking=True)
    evrak_tipi = fields.Selection([('cek', 'Çek'), ('senet', 'Senet')], string='Evrak', required=True, default='cek')
    taraf = fields.Char(compute='_compute_islem_info')
    yeni_evrak = fields.Boolean(compute='_compute_islem_info')
    partner_gerekli = fields.Boolean(compute='_compute_islem_info')
    journal_turu = fields.Char(compute='_compute_islem_info')
    evrak_turu = fields.Char(compute='_compute_islem_info')

    date = fields.Date(string='Tarih', required=True, default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Cari', tracking=True,
                                 domain=[('parent_id', '=', False)])
    journal_id = fields.Many2one('account.journal', string='Kasa / Banka', check_company=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Para Birimi', required=True,
                                  default=lambda self: self.env.company.currency_id)
    aciklama = fields.Char(string='Açıklama')
    line_ids = fields.One2many('atlas.cek.bordro.line', 'bordro_id', string='Evraklar', copy=True)
    state = fields.Selection([('draft', 'Taslak'), ('posted', 'Onaylandı'), ('cancel', 'İptal')],
                             string='Durum', default='draft', required=True, readonly=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='Muhasebe Fişi', readonly=True, copy=False)

    uygun_cek_ids = fields.Many2many('atlas.cek', compute='_compute_uygun_cek_ids',
                                     help='Bu işleme konabilecek evraklar (tür, durum, para birimi).')
    toplam = fields.Monetary(string='Toplam', compute='_compute_toplam', store=True)
    adet = fields.Integer(string='Adet', compute='_compute_toplam', store=True)
    ortalama_vade = fields.Date(string='Ortalama Vade', compute='_compute_toplam', store=True,
                                help='Tutar ağırlıklı ortalama vade.')

    @api.depends('islem', 'evrak_tipi')
    def _compute_islem_info(self):
        for bordro in self:
            info = ISLEMLER.get(bordro.islem)
            bordro.taraf = info and info[1]
            bordro.yeni_evrak = bool(info and info[2])
            bordro.partner_gerekli = bool(info and info[5])
            bordro.journal_turu = info and info[6] or False
            bordro.evrak_turu = info and f'{info[1]}_{bordro.evrak_tipi}'

    @api.depends('islem', 'evrak_tipi', 'currency_id', 'company_id')
    def _compute_uygun_cek_ids(self):
        for bordro in self:
            info = ISLEMLER.get(bordro.islem)
            if not info or info[2]:
                bordro.uygun_cek_ids = False
                continue
            bordro.uygun_cek_ids = self.env['atlas.cek'].search([
                ('company_id', '=', bordro.company_id.id),
                ('evrak_turu', '=', bordro.evrak_turu),
                ('durum', 'in', info[3]),
                ('currency_id', '=', bordro.currency_id.id),
            ])

    @api.depends('line_ids.tutar', 'line_ids.vade')
    def _compute_toplam(self):
        for bordro in self:
            lines = bordro.line_ids.filtered(lambda l: l.vade and l.tutar)
            bordro.toplam = sum(bordro.line_ids.mapped('tutar'))
            bordro.adet = len(bordro.line_ids)
            total = sum(lines.mapped('tutar'))
            if total:
                base = min(lines.mapped('vade'))
                days = sum((l.vade - base).days * l.tutar for l in lines) / total
                bordro.ortalama_vade = base + timedelta(days=round(days))
            else:
                bordro.ortalama_vade = False

    @api.onchange('islem', 'evrak_tipi')
    def _onchange_islem(self):
        if not self.yeni_evrak:
            self.line_ids.filtered(lambda l: l.cek_id and l.cek_id.evrak_turu != self.evrak_turu).unlink()

    # -------------------------------------------------------------------------
    # Onay
    # -------------------------------------------------------------------------

    def action_post(self):
        for bordro in self:
            if bordro.state != 'draft':
                continue
            bordro._check_before_post()
            if bordro.yeni_evrak:
                bordro.line_ids._create_cek()
            move = bordro._create_move()
            bordro.write({'state': 'posted', 'move_id': move.id, 'name': move.name})
            bordro.line_ids.cek_id.invalidate_recordset(['durum'])
        return True

    def _check_before_post(self):
        self.ensure_one()
        label = dict(ISLEM_SELECTION)[self.islem]
        if not self.line_ids:
            raise UserError(self.env._('Bordroda evrak yok.'))
        if self.partner_gerekli and not self.partner_id:
            raise UserError(self.env._('%s için cari seçilmelidir.', label))
        if self.journal_turu == 'bank' and self.journal_id.type != 'bank':
            raise UserError(self.env._('%s için banka hesabı seçilmelidir.', label))
        if self.journal_turu == 'bank_cash' and self.journal_id.type not in ('bank', 'cash'):
            raise UserError(self.env._('%s için kasa veya banka seçilmelidir.', label))
        for line in self.line_ids:
            if self.yeni_evrak:
                if not (line.seri_no and line.vade and line.tutar > 0):
                    raise UserError(self.env._('Evrak no, vade ve tutar zorunludur.'))
                continue
            cek = line.cek_id
            if not cek:
                raise UserError(self.env._('Satırda evrak seçilmemiş.'))
            if cek.evrak_turu != self.evrak_turu:
                raise UserError(self.env._('%s bu bordroya uygun evrak türünde değil.', cek.display_name))
            if cek.durum not in ISLEMLER[self.islem][3]:
                raise UserError(self.env._(
                    '%(cek)s durumu "%(durum)s"; %(islem)s yapılamaz.',
                    cek=cek.display_name, durum=dict(DURUM_SELECTION).get(cek.durum), islem=label))
            if cek.currency_id != self.currency_id:
                raise UserError(self.env._('%s bordro para biriminde değil.', cek.display_name))
            if self.islem == 'tahsilden_al' or self.islem == 'tahsil' and cek.durum == 'tahsilde':
                if self.journal_id and cek.konum_journal_id and cek.konum_journal_id != self.journal_id \
                        and self.journal_id.type == 'bank':
                    raise UserError(self.env._('%(cek)s %(banka)s bankasında tahsilde.',
                                               cek=cek.display_name, banka=cek.konum_journal_id.name))
        duplicate = self.line_ids.cek_id.filtered(lambda c: len(self.line_ids.filtered(lambda l: l.cek_id == c)) > 1)
        if duplicate:
            raise UserError(self.env._('Aynı evrak bordroda birden fazla: %s', duplicate[0].display_name))

    def _create_move(self):
        self.ensure_one()
        lines = []
        for line in self.line_ids:
            cek = line.cek_id
            label = f'{dict(ISLEM_SELECTION)[self.islem]} - {cek.seri_no} ({cek.name}) vade {cek.vade:%d.%m.%Y}'
            debit, credit = self._line_accounts(cek)
            for (account, partner, bank_journal), sign in ((debit, 1), (credit, -1)):
                lines.append(self._move_line_vals(account, partner, sign * cek.tutar, label, cek.vade, bank_journal))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'atlas_fis_turu': 'cek_senet',
            'atlas_cek_bordro_id': self.id,
            'date': self.date,
            'ref': self.aciklama or dict(ISLEM_SELECTION)[self.islem],
            'company_id': self.company_id.id,
            'line_ids': [Command.create(vals) for vals in lines],
        })
        move.action_post()
        return move

    def _line_accounts(self, cek):
        """Evrak için (borç, alacak) tarafları: (hesap, cari, beklenen banka) üçlüleri."""
        islem = self.islem
        old = cek._account() if not self.yeni_evrak else None
        new_durum = ISLEMLER[islem][4]
        if islem == 'giris':
            return (cek._account('portfoy'), None, None), (self._partner_account(self.partner_id, 'alici'), self.partner_id, None)
        if islem == 'ciro':
            return (self._partner_account(self.partner_id, 'satici'), self.partner_id, None), (old, None, None)
        if islem in ('tahsile_ver', 'tahsilden_al', 'teminata_ver', 'teminattan_al'):
            return (cek._account(new_durum), None, None), (old, None, None)
        if islem == 'tahsil':
            return self._liquidity_side(), (old, None, None)
        if islem in ('karsiliksiz', 'musteriye_iade'):
            return (self._partner_account(cek.partner_id, 'alici'), cek.partner_id, None), (old, None, None)
        if islem == 'firma_cikis':
            return (self._partner_account(self.partner_id, 'satici'), self.partner_id, None), (cek._account(), None, None)
        if islem == 'firma_odeme':
            return (cek._account(), None, None), self._liquidity_side()
        if islem == 'firma_iade':
            return (cek._account(), None, None), (self._partner_account(cek.partner_id, 'satici'), cek.partner_id, None)
        raise UserError(self.env._('Tanımsız işlem: %s', islem))

    def _partner_account(self, partner, tipi):
        partner = partner.commercial_partner_id
        partner._atlas_add_cari_tipi(tipi)
        partner = partner.with_company(self.company_id)
        return partner.property_account_receivable_id if tipi == 'alici' else partner.property_account_payable_id

    def _liquidity_side(self):
        """Kasa: doğrudan kasa hesabı. Banka: transit hesap; banka ekstresi eşleştirmesiyle kapanır."""
        if self.journal_id.type == 'cash':
            return self.journal_id.default_account_id, None, None
        transit = self.company_id.transfer_account_id
        if not transit:
            raise UserError(self.env._('Şirkette transit hesap tanımlı değil.'))
        return transit, None, self.journal_id

    def _move_line_vals(self, account, partner, amount, label, maturity, bank_journal):
        if not account:
            raise UserError(self.env._('Çek/senet hesapları tanımlı değil (Muhasebe > Ayarlar).'))
        company_currency = self.company_id.currency_id
        balance = self.currency_id._convert(amount, company_currency, self.company_id, self.date)
        return {
            'account_id': account.id,
            'partner_id': partner.commercial_partner_id.id if partner else False,
            'name': label,
            'currency_id': self.currency_id.id,
            'amount_currency': amount,
            'balance': balance,
            'date_maturity': maturity,
            'atlas_banka_journal_id': bank_journal.id if bank_journal else False,
        }

    # -------------------------------------------------------------------------
    # İptal
    # -------------------------------------------------------------------------

    def action_cancel(self):
        for bordro in self.filtered(lambda b: b.state == 'posted'):
            for cek in bordro.line_ids.cek_id:
                later = cek.bordro_line_ids.bordro_id.filtered(
                    lambda b: b.state == 'posted' and b != bordro and (b.date, b.id) > (bordro.date, bordro.id))
                if later:
                    raise UserError(self.env._(
                        '%(cek)s için sonraki bordro (%(later)s) varken bu bordro iptal edilemez.',
                        cek=cek.display_name, later=later[0].name))
            if bordro.move_id:
                pending = bordro.move_id.line_ids.filtered('reconciled')
                if pending:
                    raise UserError(self.env._('Bordronun banka tarafı eşleştirilmiş; önce eşleştirmeyi geri alın.'))
                bordro.move_id.button_draft()
                bordro.move_id.button_cancel()
            bordro.state = 'cancel'
            bordro.line_ids.cek_id.invalidate_recordset(['durum'])
        self.filtered(lambda b: b.state == 'draft').state = 'cancel'
        return True

    def action_draft(self):
        self.filtered(lambda b: b.state == 'cancel' and not b.move_id).state = 'draft'

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(b.state == 'posted' for b in self):
            raise UserError(self.env._('Onaylı bordro silinemez; önce iptal edin.'))

    def action_open_move(self):
        self.ensure_one()
        return self.move_id._get_records_action()

    def action_print(self):
        return self.env.ref('atlas_cek_senet.action_report_atlas_cek_bordro').report_action(self)


class AtlasCekBordroLine(models.Model):
    _name = 'atlas.cek.bordro.line'
    _description = 'Çek / Senet Bordro Satırı'
    _order = 'bordro_id, sequence, id'

    bordro_id = fields.Many2one('atlas.cek.bordro', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    cek_id = fields.Many2one('atlas.cek', string='Evrak', index=True, ondelete='restrict')
    company_id = fields.Many2one(related='bordro_id.company_id', store=True)
    currency_id = fields.Many2one(related='bordro_id.currency_id')

    # Yeni evrak (giriş / firma çıkışı) bilgileri; diğer işlemlerde seçilen evraktan gelir
    seri_no = fields.Char(string='Çek / Senet No', compute='_compute_from_cek', store=True, readonly=False)
    vade = fields.Date(string='Vade', compute='_compute_from_cek', store=True, readonly=False)
    tutar = fields.Monetary(string='Tutar', compute='_compute_from_cek', store=True, readonly=False)
    banka_id = fields.Many2one('atlas.banka', string='Banka', compute='_compute_from_cek', store=True, readonly=False)
    sube = fields.Char(string='Şube')
    hesap_no = fields.Char(string='Hesap No')
    kesideci = fields.Char(string='Keşideci / Borçlu', compute='_compute_from_cek', store=True, readonly=False)
    kesideci_vkn = fields.Char(string='Keşideci VKN/TCKN')

    @api.depends('cek_id')
    def _compute_from_cek(self):
        for line in self.filtered('cek_id'):
            cek = line.cek_id
            line.seri_no, line.vade, line.tutar = cek.seri_no, cek.vade, cek.tutar
            line.banka_id, line.kesideci = cek.banka_id, cek.kesideci

    def _create_cek(self):
        for line in self.filtered(lambda l: not l.cek_id):
            bordro = line.bordro_id
            line.cek_id = self.env['atlas.cek'].create({
                'evrak_turu': bordro.evrak_turu,
                'seri_no': line.seri_no,
                'vade': line.vade,
                'tutar': line.tutar,
                'currency_id': bordro.currency_id.id,
                'company_id': bordro.company_id.id,
                'partner_id': bordro.partner_id.commercial_partner_id.id,
                'banka_id': line.banka_id.id,
                'sube': line.sube,
                'hesap_no': line.hesap_no,
                'kesideci': line.kesideci or (bordro.partner_id.name if bordro.taraf == 'musteri' else bordro.company_id.name),
                'kesideci_vkn': line.kesideci_vkn,
            })
