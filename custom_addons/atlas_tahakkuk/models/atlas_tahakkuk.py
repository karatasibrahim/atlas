import calendar
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from odoo.addons.atlas_donem.models.tools import create_entry

# (kısa vadeli, uzun vadeli) erteleme hesapları
HESAPLAR = {'gider': ('180000', '280000'), 'gelir': ('380000', '480000')}
YENI_HESAPLAR = [('480000', 'GELECEK YILLARA AİT GELİRLER', 'liability_non_current')]


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_gag_hesap_id = fields.Many2one('account.account', string='Gelecek Aylara Ait Giderler (180)')
    atlas_gyag_hesap_id = fields.Many2one('account.account', string='Gelecek Yıllara Ait Giderler (280)')
    atlas_gaa_gelir_hesap_id = fields.Many2one('account.account', string='Gelecek Aylara Ait Gelirler (380)')
    atlas_gya_gelir_hesap_id = fields.Many2one('account.account', string='Gelecek Yıllara Ait Gelirler (480)')

    @api.model
    def _atlas_tahakkuk_hesaplari_kur(self):
        for company in self.search([('chart_template', '=', 'tr')]):
            company._atlas_tahakkuk_hesaplari()

    def _atlas_tahakkuk_hesaplari(self):
        self.ensure_one()
        Account = self.env['account.account'].with_company(self).with_context(lang='tr_TR')
        root = [('company_ids', 'in', self.root_id.id)]

        def hesap(kod):
            return Account.search(root + [('code', '=', kod)], limit=1)

        for kod, ad, tip in YENI_HESAPLAR:
            if not hesap(kod):
                Account.create({'code': kod, 'name': ad, 'account_type': tip, 'company_ids': [Command.link(self.root_id.id)]})
        vals = {}
        for alan, kod in (('atlas_gag_hesap_id', '180000'), ('atlas_gyag_hesap_id', '280000'),
                          ('atlas_gaa_gelir_hesap_id', '380000'), ('atlas_gya_gelir_hesap_id', '480000')):
            if not self[alan]:
                vals[alan] = hesap(kod).id
        if vals:
            self.write(vals)

    def _atlas_erteleme_hesaplari(self, tip):
        self.ensure_one()
        alanlar = ('atlas_gag_hesap_id', 'atlas_gyag_hesap_id') if tip == 'gider' else ('atlas_gaa_gelir_hesap_id', 'atlas_gya_gelir_hesap_id')
        if not all(self[a] for a in alanlar):
            self._atlas_tahakkuk_hesaplari()
        return self[alanlar[0]], self[alanlar[1]]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_gag_hesap_id = fields.Many2one(related='company_id.atlas_gag_hesap_id', readonly=False)
    atlas_gyag_hesap_id = fields.Many2one(related='company_id.atlas_gyag_hesap_id', readonly=False)
    atlas_gaa_gelir_hesap_id = fields.Many2one(related='company_id.atlas_gaa_gelir_hesap_id', readonly=False)
    atlas_gya_gelir_hesap_id = fields.Many2one(related='company_id.atlas_gya_gelir_hesap_id', readonly=False)


class AtlasTahakkuk(models.Model):
    """Ertelenmiş gider / gelir planı: bir tutarın hizmet süresine aylık dağıtılması."""
    _name = 'atlas.tahakkuk'
    _description = 'Gelecek Aylara Ait Gider / Gelir'
    _inherit = ['mail.thread']
    _order = 'tarih desc, id desc'

    name = fields.Char(string='Açıklama', required=True)
    tip = fields.Selection([('gider', 'Gelecek aylara ait gider'), ('gelir', 'Gelecek aylara ait gelir')],
                           string='Tip', required=True, default='gider')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    move_line_id = fields.Many2one('account.move.line', string='Fatura Satırı', index=True, ondelete='cascade', readonly=True)
    kaynak_move_id = fields.Many2one(related='move_line_id.move_id', store=True, string='Fatura')
    partner_id = fields.Many2one('res.partner', string='Cari')
    hesap_id = fields.Many2one('account.account', string='Gider / Gelir Hesabı', required=True,
                               help='Tutarın şu an kayıtlı olduğu ve aylık tanınacağı hesap (ör. 770, 600).')
    analytic_distribution = fields.Json(string='Analitik Dağılım')
    tutar = fields.Monetary(string='Tutar', required=True, currency_field='currency_id')
    tarih = fields.Date(string='Erteleme Tarihi', required=True, default=fields.Date.context_today)
    bas = fields.Date(string='Başlangıç', required=True)
    bit = fields.Date(string='Bitiş', required=True)
    kisa_hesap_id = fields.Many2one('account.account', string='Kısa Vadeli Hesap', compute='_compute_hesaplar', store=True, readonly=False)
    uzun_hesap_id = fields.Many2one('account.account', string='Uzun Vadeli Hesap', compute='_compute_hesaplar', store=True, readonly=False)
    move_ids = fields.One2many('account.move', 'atlas_tahakkuk_id', string='Fişler')
    durum = fields.Selection([('taslak', 'Taslak'), ('devam', 'Devam ediyor'), ('bitti', 'Tamamlandı')],
                             string='Durum', compute='_compute_durum', store=True)
    taninan = fields.Monetary(string='Tanınan', compute='_compute_durum', store=True, currency_field='currency_id')
    kalan = fields.Monetary(string='Kalan', compute='_compute_durum', store=True, currency_field='currency_id')

    _tarih_sirasi = models.Constraint('CHECK(bit >= bas)', 'Bitiş tarihi başlangıçtan önce olamaz.')
    _tutar_pozitif = models.Constraint('CHECK(tutar > 0)', 'Tutar sıfırdan büyük olmalı.')

    @api.depends('tip', 'company_id')
    def _compute_hesaplar(self):
        for t in self:
            t.kisa_hesap_id, t.uzun_hesap_id = t.company_id._atlas_erteleme_hesaplari(t.tip)

    @api.depends('move_ids.state', 'move_ids.atlas_tahakkuk_rol', 'tutar')
    def _compute_durum(self):
        for t in self:
            tanima = t.move_ids.filtered(lambda m: m.atlas_tahakkuk_rol == 'tanima')
            taninan = sum(m.amount_total for m in tanima if m.state == 'posted')
            t.taninan = taninan
            t.kalan = t.tutar - taninan if t.move_ids else t.tutar
            if not t.move_ids:
                t.durum = 'taslak'
            elif tanima and all(m.state == 'posted' for m in tanima):
                t.durum = 'bitti'
            else:
                t.durum = 'devam'

    # -------------------------------------------------------------------------
    # Plan
    # -------------------------------------------------------------------------

    def _aylik_plan(self):
        """[(tanıma tarihi, tutar)] — ay ay, gün oranına göre; kuruş farkı son aya."""
        self.ensure_one()
        currency = self.currency_id
        toplam_gun = (self.bit - self.bas).days + 1
        dilimler = []
        yil, ay = self.bas.year, self.bas.month
        while date(yil, ay, 1) <= self.bit:
            ay_sonu = date(yil, ay, calendar.monthrange(yil, ay)[1])
            d_bas, d_bit = max(self.bas, date(yil, ay, 1)), min(self.bit, ay_sonu)
            dilimler.append((d_bit, (d_bit - d_bas).days + 1))
            yil, ay = (yil + 1, 1) if ay == 12 else (yil, ay + 1)
        plan, dagitilan = [], 0.0
        for i, (tarih, gun) in enumerate(dilimler):
            tutar = self.tutar - dagitilan if i == len(dilimler) - 1 else currency.round(self.tutar * gun / toplam_gun)
            dagitilan += tutar
            plan.append((tarih, tutar))
        return plan

    def _uzun_vadeli_mi(self, tanima_tarihi):
        """Erteleme yılının ertesi yıl sonundan sonra tanınacak tutar uzun vadelidir (280/480)."""
        return tanima_tarihi.year > self.tarih.year + 1

    def action_onayla(self):
        for t in self:
            if t.move_ids:
                raise UserError(self.env._('%s için fişler zaten oluşturuldu.', t.name))
            t._fisleri_olustur()
        return True

    def _satir(self, hesap, tutar, isaret, analitik=False):
        """isaret: +1 borç, -1 alacak."""
        vals = {'account_id': hesap.id, 'balance': isaret * tutar, 'name': self.name, 'partner_id': self.partner_id.id}
        if analitik and self.analytic_distribution:
            vals['analytic_distribution'] = self.analytic_distribution
        return vals

    def _fis(self, tarih, satirlar, rol, ref):
        bugun = fields.Date.context_today(self)
        move = create_entry(self.env, self.company_id, tarih, ref, satirlar, post=False)
        move.write({'atlas_tahakkuk_id': self.id, 'atlas_tahakkuk_rol': rol,
                    'auto_post': 'at_date' if tarih > bugun else 'no'})
        if tarih <= bugun:
            move.action_post()
        return move

    def _fisleri_olustur(self):
        self.ensure_one()
        if not self.kisa_hesap_id or not self.uzun_hesap_id:
            raise UserError(self.env._('Erteleme hesapları (180/280, 380/480) tanımlı değil; muhasebe ayarlarından seçin.'))
        if self.bas < self.tarih.replace(day=1):
            raise UserError(self.env._('%s: hizmet başlangıcı erteleme tarihinin ayından önce olamaz.', self.name))
        plan = self._aylik_plan()
        uzun = sum(tutar for tarih, tutar in plan if self._uzun_vadeli_mi(tarih))
        kisa = self.tutar - uzun
        gider = self.tip == 'gider'
        e = 1 if gider else -1  # gider: erteleme hesabı borç; gelir: alacak
        ref = self.env._('Erteleme: %s', self.name)
        self._fis(self.tarih, [
            self._satir(self.kisa_hesap_id, kisa, e),
            self._satir(self.uzun_hesap_id, uzun, e),
            self._satir(self.hesap_id, self.tutar, -e, analitik=True),
        ], 'erteleme', ref)
        # Yıl sonu virmanları: ertesi yıl tanınacak uzun vadeli kısım kısa vadeye
        yillar = sorted({tarih.year for tarih, _t in plan if self._uzun_vadeli_mi(tarih)})
        for yil in yillar:
            tutar = sum(t for tarih, t in plan if tarih.year == yil)
            self._fis(date(yil - 1, 12, 31), [
                self._satir(self.kisa_hesap_id, tutar, e),
                self._satir(self.uzun_hesap_id, tutar, -e),
            ], 'virman', self.env._('Vade virmanı %(yil)s: %(ad)s', yil=yil, ad=self.name))
        for tarih, tutar in plan:
            self._fis(tarih, [
                self._satir(self.hesap_id, tutar, e, analitik=True),
                self._satir(self.kisa_hesap_id, tutar, -e),
            ], 'tanima', self.env._('Tahakkuk %(ay)s: %(ad)s', ay=tarih.strftime('%m/%Y'), ad=self.name))

    def _fisleri_geri_al(self):
        """Taslak (henüz tarihi gelmemiş) fişleri siler, onaylı fişleri ters kayıtla iptal eder."""
        for t in self:
            fisler = t.move_ids.filtered(lambda m: m.atlas_tahakkuk_rol and not m.reversed_entry_id)
            taslak = fisler.filtered(lambda m: m.state == 'draft')
            onayli = fisler.filtered(lambda m: m.state == 'posted' and not m.reversal_move_ids)
            taslak.unlink()
            if onayli:
                bugun = fields.Date.context_today(self)
                onayli._reverse_moves([{'date': max(m.date, bugun) if m.date > bugun else bugun,
                                        'ref': self.env._('İptal: %s', m.ref or m.name)} for m in onayli], cancel=True)
        return True

    def action_geri_al(self):
        """Planı iptal eder: fişler geri alınır, plan yeniden onaylanabilir."""
        self._fisleri_geri_al()
        self.move_ids.write({'atlas_tahakkuk_id': False})
        return True

    def unlink(self):
        self._fisleri_geri_al()
        self.move_ids.write({'atlas_tahakkuk_id': False})
        return super().unlink()

    def action_fisler(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'name': self.name,
                'view_mode': 'list,form', 'domain': [('atlas_tahakkuk_id', '=', self.id)]}


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_tahakkuk_id = fields.Many2one('atlas.tahakkuk', string='Erteleme Planı', index='btree_not_null', copy=False, readonly=True)
    atlas_tahakkuk_rol = fields.Selection([('erteleme', 'Erteleme'), ('virman', 'Vade virmanı'), ('tanima', 'Aylık tahakkuk')],
                                          string='Erteleme Fişi Türü', copy=False, readonly=True)
    atlas_tahakkuk_ids = fields.One2many('atlas.tahakkuk', 'kaynak_move_id', string='Ertelemeler')
    atlas_tahakkuk_sayisi = fields.Integer(compute='_compute_atlas_tahakkuk_sayisi')

    def _compute_atlas_tahakkuk_sayisi(self):
        for move in self:
            move.atlas_tahakkuk_sayisi = len(move.atlas_tahakkuk_ids)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.is_invoice(include_receipts=False)):
            move._atlas_ertelemeleri_olustur()
        return posted

    def _atlas_ertelemeleri_olustur(self):
        self.ensure_one()
        tip = 'gider' if self.is_purchase_document() else 'gelir'
        Tahakkuk = self.env['atlas.tahakkuk']
        for line in self.invoice_line_ids.filtered(lambda l: l.atlas_ertele_bas and l.atlas_ertele_bit and l.display_type == 'product'):
            if line.atlas_tahakkuk_ids:
                continue
            # Satırın gider (borç) / gelir (alacak) yönündeki tutarı; iade faturasında ters
            tutar = line.balance if tip == 'gider' else -line.balance
            if self.currency_id.is_zero(tutar) or tutar < 0:
                continue
            tahakkuk = Tahakkuk.create({
                'name': f'{self.name} - {line.name or line.product_id.display_name or ""}'.strip(' -'),
                'tip': tip, 'company_id': self.company_id.id, 'move_line_id': line.id,
                'partner_id': self.commercial_partner_id.id, 'hesap_id': line.account_id.id,
                'analytic_distribution': line.analytic_distribution, 'tutar': tutar,
                'tarih': self.date, 'bas': line.atlas_ertele_bas, 'bit': line.atlas_ertele_bit,
            })
            tahakkuk._fisleri_olustur()

    def button_draft(self):
        tahakkuklar = self.filtered(lambda m: m.is_invoice(include_receipts=False)).atlas_tahakkuk_ids
        res = super().button_draft()
        tahakkuklar.unlink()
        return res

    def action_atlas_tahakkuklar(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.tahakkuk', 'name': self.env._('Ertelemeler'),
                'view_mode': 'list,form', 'domain': [('kaynak_move_id', '=', self.id)]}


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    atlas_ertele_bas = fields.Date(string='Hizmet Başlangıcı', copy=False,
                                   help='Doldurulursa satır tutarı hizmet süresine göre aylara dağıtılır (180/380).')
    atlas_ertele_bit = fields.Date(string='Hizmet Bitişi', copy=False)
    atlas_tahakkuk_ids = fields.One2many('atlas.tahakkuk', 'move_line_id', string='Ertelemeler')

    @api.constrains('atlas_ertele_bas', 'atlas_ertele_bit')
    def _check_atlas_ertele(self):
        for line in self:
            if bool(line.atlas_ertele_bas) != bool(line.atlas_ertele_bit):
                raise ValidationError(self.env._('Hizmet başlangıç ve bitiş tarihleri birlikte girilmeli.'))
            if line.atlas_ertele_bas and line.atlas_ertele_bit < line.atlas_ertele_bas:
                raise ValidationError(self.env._('Hizmet bitişi başlangıçtan önce olamaz.'))
