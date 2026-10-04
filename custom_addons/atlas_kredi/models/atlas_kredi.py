from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.atlas_donem.models.tools import create_entry


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_kredi_kisa_hesap_id = fields.Many2one('account.account', string='Kısa Vadeli Banka Kredileri (300)')
    atlas_kredi_taksit_hesap_id = fields.Many2one('account.account', string='Uzun Vadeli Kredilerin Taksitleri (303)')
    atlas_kredi_uzun_hesap_id = fields.Many2one('account.account', string='Uzun Vadeli Banka Kredileri (400)')
    atlas_kredi_faiz_hesap_id = fields.Many2one('account.account', string='Finansman Giderleri (780)')

    @api.model
    def _atlas_kredi_hesaplari_kur(self):
        for company in self.search([('chart_template', '=', 'tr')]):
            company._atlas_kredi_hesaplari()

    def _atlas_kredi_hesaplari(self):
        self.ensure_one()
        Account = self.env['account.account'].with_company(self)
        root = [('company_ids', 'in', self.root_id.id)]

        def hesap(kod):
            return Account.search(root + [('code', '=', kod)], limit=1)

        uzun = hesap('400000')
        if uzun and uzun.account_type == 'liability_current':
            uzun.account_type = 'liability_non_current'  # l10n_tr şablonunda 400 kısa vadeli tanımlı
        vals = {}
        for alan, kod in (('atlas_kredi_kisa_hesap_id', '300000'), ('atlas_kredi_taksit_hesap_id', '303000'),
                          ('atlas_kredi_uzun_hesap_id', '400000'), ('atlas_kredi_faiz_hesap_id', '780000')):
            if not self[alan]:
                vals[alan] = hesap(kod).id
        if vals:
            self.write(vals)


class AtlasKredi(models.Model):
    _name = 'atlas.kredi'
    _description = 'Banka Kredisi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'kullanim_tarihi desc, id desc'

    name = fields.Char(string='Kredi No', required=True, copy=False, readonly=True, default='/')
    aciklama = fields.Char(string='Açıklama', tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    banka_journal_id = fields.Many2one('account.journal', string='Banka Hesabı', required=True,
                                       domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    partner_id = fields.Many2one('res.partner', string='Banka (Cari)')
    kullanim_tarihi = fields.Date(string='Kullanım Tarihi', required=True, default=fields.Date.context_today, tracking=True)
    tutar = fields.Monetary(string='Kredi Tutarı (Anapara)', required=True, tracking=True)
    masraf = fields.Monetary(string='Dosya Masrafı', help='Kullanımda bankanın kestiği masraf (780).')
    faiz_orani = fields.Float(string='Faiz Oranı (%)', required=True, digits=(16, 4), tracking=True)
    faiz_donemi = fields.Selection([('aylik', 'Aylık'), ('yillik', 'Yıllık')], string='Faiz Dönemi', required=True, default='aylik')
    bsmv_orani = fields.Float(string='BSMV (%)', default=5.0, help='Faiz üzerinden banka ve sigorta muameleleri vergisi.')
    kkdf_orani = fields.Float(string='KKDF (%)', default=0.0, help='Faiz üzerinden kaynak kullanımını destekleme fonu.')
    taksit_sayisi = fields.Integer(string='Taksit Sayısı', required=True, default=12)
    ilk_taksit_tarihi = fields.Date(string='İlk Taksit', compute='_compute_ilk_taksit', store=True, readonly=False, precompute=True)
    odeme_tipi = fields.Selection([('esit_taksit', 'Eşit taksitli'), ('esit_anapara', 'Eşit anaparalı'),
                                   ('balon', 'Anapara vade sonunda (balon)')], string='Geri Ödeme', required=True, default='esit_taksit')
    durum = fields.Selection([('taslak', 'Taslak'), ('aktif', 'Kullanıldı'), ('kapandi', 'Kapandı')], string='Durum',
                             default='taslak', required=True, tracking=True)
    taksit_ids = fields.One2many('atlas.kredi.taksit', 'kredi_id', string='Ödeme Planı', copy=False)
    move_ids = fields.One2many('account.move', 'atlas_kredi_id', string='Fişler')
    toplam_faiz = fields.Monetary(string='Toplam Faiz + Vergi', compute='_compute_ozet')
    toplam_odeme = fields.Monetary(string='Toplam Geri Ödeme', compute='_compute_ozet')
    kalan_anapara = fields.Monetary(string='Kalan Anapara', compute='_compute_ozet')
    sonraki_taksit_id = fields.Many2one('atlas.kredi.taksit', string='Sonraki Taksit', compute='_compute_ozet')
    kapama_tarihi = fields.Date(string='Kapama Tarihi')
    kapama_faiz = fields.Monetary(string='Kapama Faizi / Cezası')

    _tutar_pozitif = models.Constraint('CHECK(tutar > 0)', 'Kredi tutarı sıfırdan büyük olmalı.')
    _taksit_pozitif = models.Constraint('CHECK(taksit_sayisi > 0 AND taksit_sayisi <= 600)', 'Taksit sayısı 1-600 arasında olmalı.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.kredi') or '/'
        return super().create(vals_list)

    @api.depends('kullanim_tarihi')
    def _compute_ilk_taksit(self):
        for kredi in self:
            if kredi.kullanim_tarihi and not kredi.ilk_taksit_tarihi:
                kredi.ilk_taksit_tarihi = kredi.kullanim_tarihi + relativedelta(months=1)

    @api.depends('taksit_ids.anapara', 'taksit_ids.toplam', 'taksit_ids.durum')
    def _compute_ozet(self):
        for kredi in self:
            taksitler = kredi.taksit_ids
            kredi.toplam_faiz = sum(taksitler.mapped('faiz')) + sum(taksitler.mapped('bsmv')) + sum(taksitler.mapped('kkdf'))
            kredi.toplam_odeme = sum(taksitler.mapped('toplam'))
            odenmemis = taksitler.filtered(lambda t: t.durum != 'odendi')
            kredi.kalan_anapara = sum(odenmemis.mapped('anapara')) if taksitler else kredi.tutar
            kredi.sonraki_taksit_id = odenmemis.sorted('vade')[:1]

    @api.depends('name', 'aciklama')
    def _compute_display_name(self):
        for kredi in self:
            kredi.display_name = f'{kredi.name} {kredi.aciklama or ""}'.strip()

    # -------------------------------------------------------------------------
    # Ödeme planı
    # -------------------------------------------------------------------------

    def _aylik_oran(self):
        oran = (self.faiz_orani or 0.0) / 100.0
        return oran / 12.0 if self.faiz_donemi == 'yillik' else oran

    def _plan_hesapla(self):
        """[(vade, anapara, faiz, bsmv, kkdf)] — kuruş farkları son taksitte."""
        self.ensure_one()
        cur = self.currency_id
        n, r = self.taksit_sayisi, self._aylik_oran()
        vergi = (self.bsmv_orani + self.kkdf_orani) / 100.0
        brut = r * (1 + vergi)  # vergiler dahil efektif aylık oran
        if self.odeme_tipi == 'esit_taksit':
            taksit = self.tutar / n if not brut else self.tutar * brut / (1 - (1 + brut) ** -n)
        kalan, plan = self.tutar, []
        for i in range(n):
            faiz = cur.round(kalan * r)
            bsmv = cur.round(faiz * self.bsmv_orani / 100.0)
            kkdf = cur.round(faiz * self.kkdf_orani / 100.0)
            if i == n - 1:
                anapara = kalan
            elif self.odeme_tipi == 'esit_taksit':
                anapara = cur.round(taksit - faiz - bsmv - kkdf)
            elif self.odeme_tipi == 'esit_anapara':
                anapara = cur.round(self.tutar / n)
            else:
                anapara = 0.0
            kalan = cur.round(kalan - anapara)
            plan.append((self.ilk_taksit_tarihi + relativedelta(months=i), anapara, faiz, bsmv, kkdf))
        return plan

    def action_plan_olustur(self):
        for kredi in self:
            if kredi.durum != 'taslak':
                raise UserError(self.env._('Ödeme planı yalnızca taslak kredide yeniden hesaplanır.'))
            kredi.taksit_ids.unlink()
            kredi.taksit_ids = [Command.create({'no': i + 1, 'vade': vade, 'anapara': a, 'faiz': f, 'bsmv': b, 'kkdf': k})
                                for i, (vade, a, f, b, k) in enumerate(kredi._plan_hesapla())]
        return True

    # -------------------------------------------------------------------------
    # Muhasebe
    # -------------------------------------------------------------------------

    def _hesaplar(self):
        company = self.company_id
        if not (company.atlas_kredi_kisa_hesap_id and company.atlas_kredi_uzun_hesap_id and company.atlas_kredi_faiz_hesap_id):
            company._atlas_kredi_hesaplari()
        if not (company.atlas_kredi_kisa_hesap_id and company.atlas_kredi_uzun_hesap_id and company.atlas_kredi_faiz_hesap_id):
            raise UserError(self.env._('Kredi hesapları (300/303/400/780) tanımlı değil; muhasebe ayarlarından seçin.'))
        return company

    def _kisa_hesap(self):
        """Vadesi bir yılı aşan kredide kısa vadeli kısım 303'e, değilse 300'e."""
        company = self.company_id
        uzun_vadeli = self.taksit_ids and max(self.taksit_ids.mapped('vade')) > self.kullanim_tarihi + relativedelta(years=1)
        return (company.atlas_kredi_taksit_hesap_id or company.atlas_kredi_kisa_hesap_id) if uzun_vadeli else company.atlas_kredi_kisa_hesap_id

    def _uzun_vadeli_mi(self, vade):
        return vade.year > self.kullanim_tarihi.year + 1

    def _banka_satiri(self, tutar, isaret, ad):
        """Banka ayağı: bankada transit hesap (ekstreyle eşleşir), kasada doğrudan kasa hesabı."""
        journal = self.banka_journal_id
        if journal.type == 'cash':
            return {'account_id': journal.default_account_id.id, 'balance': isaret * tutar, 'name': ad}
        transit = self.company_id.transfer_account_id
        if not transit:
            raise UserError(self.env._('Şirkette transit hesap (Transit Fonlar) tanımlı değil.'))
        return {'account_id': transit.id, 'balance': isaret * tutar, 'name': ad, 'atlas_banka_journal_id': journal.id,
                'partner_id': self.partner_id.id}

    def _fis(self, tarih, satirlar, rol, ref, taksit=None):
        bugun = fields.Date.context_today(self)
        move = create_entry(self.env, self.company_id, tarih, ref, satirlar, post=False)
        move.write({'atlas_kredi_id': self.id, 'atlas_kredi_rol': rol, 'atlas_kredi_taksit_id': taksit.id if taksit else False,
                    'auto_post': 'at_date' if tarih > bugun else 'no'})
        if tarih <= bugun:
            move.action_post()
        return move

    def action_kullan(self):
        """Krediyi kullandır: kullanım, taksit ve yıl sonu virman fişlerini oluşturur."""
        for kredi in self:
            if kredi.durum != 'taslak':
                raise UserError(self.env._('%s zaten kullanıldı.', kredi.name))
            company = kredi._hesaplar()
            if not kredi.taksit_ids:
                kredi.action_plan_olustur()
            kisa_hesap, uzun_hesap, faiz_hesap = kredi._kisa_hesap(), company.atlas_kredi_uzun_hesap_id, company.atlas_kredi_faiz_hesap_id
            uzun = sum(t.anapara for t in kredi.taksit_ids if kredi._uzun_vadeli_mi(t.vade))
            kisa = kredi.tutar - uzun
            ad = kredi.display_name
            kredi._fis(kredi.kullanim_tarihi, [
                kredi._banka_satiri(kredi.tutar - kredi.masraf, 1, ad),
                {'account_id': faiz_hesap.id, 'balance': kredi.masraf, 'name': self.env._('Kredi dosya masrafı')},
                {'account_id': kisa_hesap.id, 'balance': -kisa, 'name': ad, 'partner_id': kredi.partner_id.id},
                {'account_id': uzun_hesap.id, 'balance': -uzun, 'name': ad, 'partner_id': kredi.partner_id.id},
            ], 'kullanim', self.env._('Kredi kullanımı: %s', ad))
            for yil in sorted({t.vade.year for t in kredi.taksit_ids if kredi._uzun_vadeli_mi(t.vade)}):
                tutar = sum(t.anapara for t in kredi.taksit_ids if t.vade.year == yil)
                kredi._fis(date(yil - 1, 12, 31), [
                    {'account_id': uzun_hesap.id, 'balance': tutar, 'name': ad},
                    {'account_id': kisa_hesap.id, 'balance': -tutar, 'name': ad},
                ], 'virman', self.env._('Kredi vade virmanı %(yil)s: %(ad)s', yil=yil, ad=ad))
            for taksit in kredi.taksit_ids:
                kredi._fis(taksit.vade, [
                    {'account_id': kisa_hesap.id, 'balance': taksit.anapara, 'name': ad, 'partner_id': kredi.partner_id.id},
                    {'account_id': faiz_hesap.id, 'balance': taksit.faiz + taksit.bsmv + taksit.kkdf,
                     'name': self.env._('%(ad)s faiz + BSMV/KKDF (%(no)s. taksit)', ad=ad, no=taksit.no)},
                    kredi._banka_satiri(taksit.toplam, -1, self.env._('%(ad)s %(no)s. taksit', ad=ad, no=taksit.no)),
                ], 'taksit', self.env._('Kredi taksiti %(no)s/%(n)s: %(ad)s', no=taksit.no, n=kredi.taksit_sayisi, ad=ad), taksit)
            kredi.durum = 'aktif'
        return True

    def action_erken_kapat(self):
        """Kalan anaparayı kapama tarihinde öder; gelecek taksit fişlerini siler."""
        for kredi in self:
            if kredi.durum != 'aktif':
                raise UserError(self.env._('Yalnızca kullanılmış kredi kapatılabilir.'))
            tarih = kredi.kapama_tarihi or fields.Date.context_today(self)
            acik = kredi.taksit_ids.filtered(lambda t: t.durum != 'odendi')
            if not acik:
                raise UserError(self.env._('Ödenmemiş taksit yok.'))
            company = kredi._hesaplar()
            kisa_hesap, uzun_hesap = kredi._kisa_hesap(), company.atlas_kredi_uzun_hesap_id
            gelecek = kredi.move_ids.filtered(lambda m: m.state == 'draft' and m.atlas_kredi_rol in ('taksit', 'virman'))
            # Taslak virmanlar silinince o tutarlar hâlâ 400'de; kapamada oradan düşülür
            uzunda = sum(m.amount_total for m in gelecek if m.atlas_kredi_rol == 'virman')
            gelecek.unlink()
            anapara = sum(acik.mapped('anapara'))
            ad = kredi.display_name
            kredi._fis(tarih, [
                {'account_id': kisa_hesap.id, 'balance': anapara - uzunda, 'name': ad, 'partner_id': kredi.partner_id.id},
                {'account_id': uzun_hesap.id, 'balance': uzunda, 'name': ad, 'partner_id': kredi.partner_id.id},
                {'account_id': company.atlas_kredi_faiz_hesap_id.id, 'balance': kredi.kapama_faiz, 'name': self.env._('Erken kapama faizi')},
                kredi._banka_satiri(anapara + kredi.kapama_faiz, -1, self.env._('%s erken kapama', ad)),
            ], 'kapama', self.env._('Kredi erken kapama: %s', ad))
            acik.write({'kapandi': True})
            kredi.durum = 'kapandi'
        return True

    def action_iptal(self):
        """Kullanılmış krediyi geri alır: taslak fişler silinir, onaylılar ters kayıtla iptal edilir."""
        for kredi in self:
            taslak = kredi.move_ids.filtered(lambda m: m.state == 'draft')
            onayli = kredi.move_ids.filtered(lambda m: m.state == 'posted' and not m.reversal_move_ids and not m.reversed_entry_id)
            taslak.unlink()
            if onayli:
                onayli._reverse_moves([{'date': fields.Date.context_today(self), 'ref': self.env._('İptal: %s', m.ref)} for m in onayli],
                                      cancel=True)
            kredi.move_ids.write({'atlas_kredi_id': False, 'atlas_kredi_taksit_id': False})
            kredi.taksit_ids.write({'kapandi': False})
            kredi.durum = 'taslak'
        return True

    def action_fisler(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'name': self.display_name,
                'view_mode': 'list,form', 'domain': [('atlas_kredi_id', '=', self.id)]}


class AtlasKrediTaksit(models.Model):
    _name = 'atlas.kredi.taksit'
    _description = 'Kredi Taksiti'
    _order = 'kredi_id, vade, no'

    kredi_id = fields.Many2one('atlas.kredi', string='Kredi', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='kredi_id.company_id', store=True)
    currency_id = fields.Many2one(related='kredi_id.currency_id')
    banka_journal_id = fields.Many2one(related='kredi_id.banka_journal_id', store=True, string='Banka')
    no = fields.Integer(string='No')
    vade = fields.Date(string='Vade', required=True, index=True)
    anapara = fields.Monetary(string='Anapara')
    faiz = fields.Monetary(string='Faiz')
    bsmv = fields.Monetary(string='BSMV')
    kkdf = fields.Monetary(string='KKDF')
    toplam = fields.Monetary(string='Taksit', compute='_compute_toplam', store=True)
    kalan_anapara = fields.Monetary(string='Kalan Anapara', compute='_compute_kalan')
    move_id = fields.Many2one('account.move', string='Fiş', compute='_compute_durum')
    kapandi = fields.Boolean(string='Erken Kapamayla Ödendi', copy=False)
    durum = fields.Selection([('planlandi', 'Planlandı'), ('odendi', 'Ödendi')], string='Durum', compute='_compute_durum', store=True)

    @api.depends('anapara', 'faiz', 'bsmv', 'kkdf')
    def _compute_toplam(self):
        for t in self:
            t.toplam = t.anapara + t.faiz + t.bsmv + t.kkdf

    def _compute_kalan(self):
        for kredi in self.kredi_id:
            kalan = kredi.tutar
            for t in kredi.taksit_ids.sorted(lambda x: (x.vade, x.no)):
                kalan -= t.anapara
                if t in self:
                    t.kalan_anapara = kalan
        for t in self - self.kredi_id.taksit_ids:
            t.kalan_anapara = 0.0

    @api.depends('kapandi', 'kredi_id.move_ids.state', 'kredi_id.move_ids.atlas_kredi_taksit_id')
    def _compute_durum(self):
        for t in self:
            move = t.kredi_id.move_ids.filtered(lambda m: m.atlas_kredi_taksit_id == t and not m.reversal_move_ids)[:1]
            t.move_id = move
            t.durum = 'odendi' if t.kapandi or move.state == 'posted' else 'planlandi'


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_kredi_id = fields.Many2one('atlas.kredi', string='Kredi', index='btree_not_null', copy=False, readonly=True)
    atlas_kredi_taksit_id = fields.Many2one('atlas.kredi.taksit', string='Kredi Taksiti', copy=False, readonly=True)
    atlas_kredi_rol = fields.Selection([('kullanim', 'Kullanım'), ('taksit', 'Taksit'), ('virman', 'Vade virmanı'),
                                        ('kapama', 'Erken kapama')], string='Kredi Fişi', copy=False, readonly=True)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_kredi_kisa_hesap_id = fields.Many2one(related='company_id.atlas_kredi_kisa_hesap_id', readonly=False)
    atlas_kredi_taksit_hesap_id = fields.Many2one(related='company_id.atlas_kredi_taksit_hesap_id', readonly=False)
    atlas_kredi_uzun_hesap_id = fields.Many2one(related='company_id.atlas_kredi_uzun_hesap_id', readonly=False)
    atlas_kredi_faiz_hesap_id = fields.Many2one(related='company_id.atlas_kredi_faiz_hesap_id', readonly=False)
