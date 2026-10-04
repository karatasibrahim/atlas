from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

BIRIMLER = [('gun', 'Gün'), ('hafta', 'Hafta'), ('ay', 'Ay'), ('yil', 'Yıl')]
DURUMLAR = [('devam', 'Devam ediyor'), ('durduruldu', 'Durduruldu'), ('kapandi', 'Kapandı'), ('yenilendi', 'Yenilendi')]


class AtlasAbonelikPlan(models.Model):
    _name = 'atlas.abonelik.plan'
    _description = 'Abonelik Planı'
    _order = 'sequence, id'

    name = fields.Char(string='Plan', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    aralik = fields.Integer(string='Her', required=True, default=1)
    birim = fields.Selection(BIRIMLER, string='Periyot', required=True, default='ay')
    taahhut_aralik = fields.Integer(string='Taahhüt Süresi', help='Boş/0 ise süresiz (kapatılana kadar).')
    taahhut_birim = fields.Selection(BIRIMLER, string='Taahhüt Birimi', default='ay')
    otomatik_onay = fields.Boolean(string='Faturayı Otomatik Onayla', default=True)
    company_id = fields.Many2one('res.company', string='Şirket')

    _aralik_pozitif = models.Constraint('CHECK(aralik > 0)', 'Periyot sıfırdan büyük olmalı.')

    def _delta(self, sayi=1):
        self.ensure_one()
        n = self.aralik * sayi
        return {'gun': relativedelta(days=n), 'hafta': relativedelta(weeks=n), 'ay': relativedelta(months=n),
                'yil': relativedelta(years=n)}[self.birim]

    def _aylik_carpan(self):
        """Dönem tutarını aylık eşdeğerine çeviren çarpan (MRR)."""
        self.ensure_one()
        return {'gun': 365.0 / 12, 'hafta': 52.0 / 12, 'ay': 1.0, 'yil': 1.0 / 12}[self.birim] / self.aralik

    def _taahhut_delta(self):
        self.ensure_one()
        if not self.taahhut_aralik:
            return None
        n = self.taahhut_aralik
        return {'gun': relativedelta(days=n), 'hafta': relativedelta(weeks=n), 'ay': relativedelta(months=n),
                'yil': relativedelta(years=n)}[self.taahhut_birim or 'ay']


class AtlasAbonelikKapanis(models.Model):
    _name = 'atlas.abonelik.kapanis'
    _description = 'Abonelik Kapanış Nedeni'
    _order = 'sequence, id'

    name = fields.Char(string='Neden', required=True)
    sequence = fields.Integer(default=10)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    atlas_plan_id = fields.Many2one('atlas.abonelik.plan', string='Abonelik Planı', tracking=True,
                                    help='Seçilirse sipariş abonelik olarak dönemsel faturalanır.')
    atlas_abonelik_durum = fields.Selection(DURUMLAR, string='Abonelik Durumu', tracking=True, copy=False, index=True)
    atlas_baslangic = fields.Date(string='Abonelik Başlangıcı', copy=False)
    atlas_sonraki_fatura = fields.Date(string='Sonraki Fatura', copy=False, index=True)
    atlas_bitis = fields.Date(string='Bitiş', copy=False, help='Taahhüt sonu. Boşsa süresiz.')
    atlas_kapanis_id = fields.Many2one('atlas.abonelik.kapanis', string='Kapanış Nedeni', copy=False, tracking=True)
    atlas_kapanis_notu = fields.Text(string='Kapanış Notu', copy=False)
    atlas_mrr = fields.Monetary(string='MRR', compute='_compute_atlas_mrr', store=True, currency_field='currency_id',
                                help='Aylık yinelenen gelir (vergi hariç).')
    atlas_arr = fields.Monetary(string='ARR', compute='_compute_atlas_mrr', store=True, currency_field='currency_id')
    atlas_abonelik_fatura_ids = fields.One2many('account.move', 'atlas_abonelik_id', string='Abonelik Faturaları')
    atlas_abonelik_fatura_sayisi = fields.Integer(compute='_compute_atlas_abonelik_fatura_sayisi')
    atlas_onceki_id = fields.Many2one('sale.order', string='Önceki Dönem', copy=False, readonly=True)
    atlas_yenileme_id = fields.Many2one('sale.order', string='Yenileme', copy=False, readonly=True)

    @api.depends('atlas_plan_id', 'amount_untaxed', 'atlas_abonelik_durum')
    def _compute_atlas_mrr(self):
        for order in self:
            if order.atlas_plan_id and order.atlas_abonelik_durum == 'devam':
                order.atlas_mrr = order.currency_id.round(order.amount_untaxed * order.atlas_plan_id._aylik_carpan())
            else:
                order.atlas_mrr = 0.0
            order.atlas_arr = order.atlas_mrr * 12

    def _compute_atlas_abonelik_fatura_sayisi(self):
        for order in self:
            order.atlas_abonelik_fatura_sayisi = len(order.atlas_abonelik_fatura_ids)

    # -------------------------------------------------------------------------
    # Yaşam döngüsü
    # -------------------------------------------------------------------------

    def action_confirm(self):
        res = super().action_confirm()
        for order in self.filtered('atlas_plan_id'):
            if order.atlas_abonelik_durum:
                continue
            baslangic = order.atlas_baslangic or fields.Date.context_today(order)
            vals = {'atlas_abonelik_durum': 'devam', 'atlas_baslangic': baslangic, 'atlas_sonraki_fatura': baslangic}
            taahhut = order.atlas_plan_id._taahhut_delta()
            if taahhut and not order.atlas_bitis:
                vals['atlas_bitis'] = baslangic + taahhut - timedelta(days=1)
            order.write(vals)
        return res

    def _get_invoiceable_lines(self, final=False):
        # Abonelikler standart "Fatura Oluştur" ile değil, dönem faturasıyla faturalanır
        if self.atlas_plan_id and self.atlas_abonelik_durum:
            return self.env['sale.order.line']
        return super()._get_invoiceable_lines(final)

    def _atlas_donem(self):
        self.ensure_one()
        bas = self.atlas_sonraki_fatura
        return bas, bas + self.atlas_plan_id._delta() - timedelta(days=1)

    def _atlas_fatura_olustur(self):
        """Bir dönemlik fatura; sonraki fatura tarihini ilerletir."""
        self.ensure_one()
        bas, bit = self._atlas_donem()
        donem = f'{bas:%d.%m.%Y} - {bit:%d.%m.%Y}'
        satirlar = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id and l.product_uom_qty):
            satirlar.append(Command.create({
                'product_id': line.product_id.id, 'name': f'{line.name}\n{self.env._("Dönem")}: {donem}',
                'quantity': line.product_uom_qty, 'product_uom_id': line.product_uom_id.id,
                'price_unit': line.price_unit, 'discount': line.discount, 'tax_ids': [Command.set(line.tax_ids.ids)],
                'analytic_distribution': line.analytic_distribution,
            }))
        if not satirlar:
            raise UserError(self.env._('%s aboneliğinde faturalanacak satır yok.', self.name))
        vals = self._prepare_invoice()
        vals.update({'invoice_line_ids': satirlar, 'invoice_date': bas, 'atlas_abonelik_id': self.id,
                     'ref': f'{self.client_order_ref or self.name} ({donem})'})
        fatura = self.env['account.move'].with_company(self.company_id).create(vals)
        if self.atlas_plan_id.otomatik_onay:
            fatura.action_post()
        sonraki = bas + self.atlas_plan_id._delta()
        yeni = {'atlas_sonraki_fatura': sonraki}
        if self.atlas_bitis and sonraki > self.atlas_bitis:
            yeni['atlas_abonelik_durum'] = 'kapandi'
        self.write(yeni)
        self.message_post(body=self.env._('Dönem faturası oluşturuldu: %(fatura)s (%(donem)s).', fatura=fatura.name or '/', donem=donem))
        return fatura

    def action_atlas_faturala(self):
        faturalar = self.env['account.move']
        for order in self:
            if order.atlas_abonelik_durum != 'devam':
                raise UserError(self.env._('%s aktif bir abonelik değil.', order.name))
            faturalar |= order._atlas_fatura_olustur()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'view_mode': 'list,form',
                'domain': [('id', 'in', faturalar.ids)], 'name': self.env._('Abonelik Faturaları')}

    @api.model
    def _cron_atlas_abonelik(self):
        bugun = fields.Date.context_today(self)
        for order in self.search([('atlas_abonelik_durum', '=', 'devam'), ('atlas_sonraki_fatura', '<=', bugun)]):
            try:
                with self.env.cr.savepoint():
                    # Birden fazla dönem geride kaldıysa hepsi faturalanır
                    while order.atlas_abonelik_durum == 'devam' and order.atlas_sonraki_fatura <= bugun:
                        order._atlas_fatura_olustur()
            except UserError as hata:
                order.message_post(body=self.env._('Otomatik faturalama başarısız: %s', hata))

    def action_atlas_durdur(self):
        self.filtered(lambda o: o.atlas_abonelik_durum == 'devam').write({'atlas_abonelik_durum': 'durduruldu'})
        return True

    def action_atlas_devam(self):
        for order in self.filtered(lambda o: o.atlas_abonelik_durum == 'durduruldu'):
            bugun = fields.Date.context_today(order)
            vals = {'atlas_abonelik_durum': 'devam'}
            if order.atlas_sonraki_fatura and order.atlas_sonraki_fatura < bugun:
                vals['atlas_sonraki_fatura'] = bugun  # durdurulan dönemler faturalanmaz
            order.write(vals)
        return True

    def action_atlas_kapat(self):
        for order in self:
            if not order.atlas_kapanis_id:
                raise UserError(self.env._('%s için kapanış nedeni seçin.', order.name))
        self.write({'atlas_abonelik_durum': 'kapandi'})
        return True

    def action_atlas_yenile(self):
        """Taahhüt sonunda yeni dönem aboneliği (aynı satırlar) oluşturur."""
        self.ensure_one()
        if not self.atlas_bitis:
            raise UserError(self.env._('Süresiz abonelik yenilenmez; satırları güncelleyerek devam ettirin.'))
        baslangic = self.atlas_bitis + timedelta(days=1)
        yeni = self.copy({'atlas_baslangic': baslangic, 'atlas_onceki_id': self.id, 'origin': self.name,
                          'date_order': fields.Datetime.now()})
        self.write({'atlas_yenileme_id': yeni.id, 'atlas_abonelik_durum': 'yenilendi'})
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'res_id': yeni.id, 'view_mode': 'form'}

    def action_atlas_abonelik_faturalari(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'view_mode': 'list,form',
                'domain': [('atlas_abonelik_id', '=', self.id)], 'name': self.env._('Abonelik Faturaları')}


class AccountMove(models.Model):
    _inherit = 'account.move'

    atlas_abonelik_id = fields.Many2one('sale.order', string='Abonelik', index='btree_not_null', copy=False, readonly=True)
