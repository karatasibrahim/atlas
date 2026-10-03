"""Türkiye hesap planı / vergi şablonundaki (l10n_tr) bilinen hataların düzeltilmesi ve GİB kodları.

l10n_tr şablonunda: alış tevkifatı 391005'e, kira stopajı 191'e yazılıyor; bazı hesap ve vergi adları
bozuk çeviri veya İngilizce. Tek Düzen Hesap Planı'na göre düzeltmeler her modül güncellemesinde
(tekrar çalıştırılabilir şekilde) uygulanır.
"""
from odoo import api, fields, models
from odoo.fields import Command

# (kod, Türkçe ad, hesap türü) — beyanname ayrımı için 360 alt hesapları
YENI_HESAPLAR = [
    ('360001', 'SORUMLU SIFATIYLA ÖDENECEK KDV (KDV-2)', 'liability_current'),
    ('360002', 'GELİR VERGİSİ STOPAJI - KİRA (MUHTASAR)', 'liability_current'),
]
HESAP_ADLARI = {
    '391004': 'TEVKİF EDİLEN KDV (SATIŞ)',
    '391005': 'TEVKİFAT (ALIŞ) - KULLANILMIYOR, 360001',
    '111000': 'ÖZEL KESİM TAHVİL, SENET VE BONOLARI',
    '112000': 'KAMU KESİMİ TAHVİL, SENET VE BONOLARI',
    '221000': 'ALACAK SENETLERİ',
    '295000': 'PEŞİN ÖDENEN VERGİLER VE FONLAR',
    '540000': 'YASAL YEDEKLER',
    '612000': 'DİĞER İNDİRİMLER (-)',
    '671000': 'ÖNCEKİ DÖNEM GELİR VE KÂRLARI',
    '772000': 'GENEL YÖNETİM GİDERLERİ FARK HESABI',
}
TEVKIFAT_ORANLARI = ('2_10', '3_10', '4_10', '5_10', '7_10', '9_10', '10_10')
# Mali koşullar: (xml adı, ad, GİB kodu, hedef vergi tanımı)
MALI_KOSULLAR = [
    ('fp_ihracat', 'İhracat', '301'),
    ('fp_ihrac_kayitli', 'İhraç Kayıtlı Satış', '701'),
    ('fp_serbest_bolge', 'Serbest Bölge', '212'),
]


class AtlasGibKod(models.Model):
    _name = 'atlas.gib.kod'
    _description = 'GİB İstisna / Tevkifat Kodu'
    _order = 'tip, kod'
    _rec_names_search = ['kod', 'name']

    kod = fields.Char(string='Kod', required=True, index=True)
    name = fields.Char(string='Açıklama', required=True)
    tip = fields.Selection([('tevkifat', 'Tevkifat'), ('istisna', 'İstisna'), ('ihracat', 'İhracat İstisnası'),
                            ('ihrac_kayitli', 'İhraç Kayıtlı')], string='Tip', required=True)
    tevkifat_pay = fields.Integer(string='Tevkifat (x/10)', help='Tevkifat kodlarında KDV\'nin tevkif edilen onda biri.')
    active = fields.Boolean(default=True)

    _kod_unique = models.Constraint('UNIQUE(kod)', 'GİB kodu benzersiz olmalıdır.')

    @api.depends('kod', 'name')
    def _compute_display_name(self):
        for kod in self:
            kod.display_name = f'{kod.kod} - {kod.name}'


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    atlas_gib_kod_id = fields.Many2one('atlas.gib.kod', string='GİB İstisna / Tevkifat Kodu',
                                       help='e-Fatura\'da bu mali koşulla kesilen faturalara yazılacak kod.')


class AccountTax(models.Model):
    _inherit = 'account.tax'

    atlas_gib_kod_id = fields.Many2one('atlas.gib.kod', string='GİB Kodu')


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _atlas_apply_tr_fixes_all(self):
        for company in self.search([('chart_template', '=', 'tr')]):
            company._atlas_apply_tr_fixes()

    def _atlas_tr_ref(self, name):
        return self.env['account.chart.template'].with_company(self).ref(name, raise_if_not_found=False)

    def _atlas_apply_tr_fixes(self):
        self.ensure_one()
        company = self.with_company(self)
        Account = self.env['account.account'].with_company(company).with_context(lang='tr_TR')
        root = [('company_ids', 'in', company.root_id.id)]

        def account(code):
            return Account.search(root + [('code', '=', code)], limit=1)

        for code, name, account_type in YENI_HESAPLAR:
            if not account(code):
                Account.create({'code': code, 'name': name, 'account_type': account_type,
                                'company_ids': [Command.link(company.root_id.id)]})
        for code, name in HESAP_ADLARI.items():
            acc = account(code)
            if acc and acc.name != name:
                acc.name = name

        def set_tax_account(tax, acc):
            lines = tax.repartition_line_ids.filtered(lambda l: l.repartition_type == 'tax')
            if acc and lines and any(l.account_id != acc for l in lines):
                lines.account_id = acc

        Tax = self.env['account.tax'].with_context(lang='tr_TR', active_test=False)
        kdv2, kira = account('360001'), account('360002')
        for oran in TEVKIFAT_ORANLARI:
            pay = oran.split('_')[0]
            purchase_sub = self._atlas_tr_ref(f'tr_p_wh_20_{oran}')
            if purchase_sub:
                set_tax_account(purchase_sub, kdv2)
                purchase_sub.name = f'Sorumlu Sıfatıyla KDV {pay}/10 (alış)'
            sale_sub = self._atlas_tr_ref(f'tr_wh_20_{oran}')
            if sale_sub:
                sale_sub.name = f'Tevkif Edilen KDV {pay}/10 (satış)'
            for xml, label in ((f'tr_s_wh_20_{oran}', 'Satış'), (f'tr_p_vat_wh_20_{oran}', 'Alış')):
                group = self._atlas_tr_ref(xml)
                if group:
                    group.name = f'{label} KDV %20 Tevkifatlı {pay}/10'
                    group.atlas_gib_kod_id = False
        rent = self._atlas_tr_ref('tr_pr_wh_20')
        if rent:
            set_tax_account(rent, kira)
            rent.name = 'Kira Stopajı %20 (Muhtasar)'
        export_cancel = self._atlas_tr_ref('tr_wh_s_20')
        if export_cancel:
            export_cancel.name = 'İhraç Kayıtlı KDV (tahsil edilmeyen) %20'
        for xml, name in (('tr_s_st_0948', 'Damga Vergisi %0,948 (satış)'), ('tr_s_st_0759', 'Damga Vergisi %0,759 (satış)'),
                          ('tr_s_st_0189', 'Damga Vergisi %0,189 (satış)'), ('tr_p_st_0948', 'Damga Vergisi %0,948 (alış)'),
                          ('tr_p_st_0759', 'Damga Vergisi %0,759 (alış)'), ('tr_p_st_0189', 'Damga Vergisi %0,189 (alış)'),
                          ('tr_s_0_ex', 'KDV %0 İstisna (satış)'), ('tr_p_0', 'KDV %0 (alış)')):
            tax = self._atlas_tr_ref(xml)
            if tax:
                tax.name = name
        self._atlas_setup_export_positions()

        vals = {
            'display_invoice_amount_total_words': True,
            'display_invoice_tax_company_currency': True,
        }
        for field_name, code in (('account_discount_income_allocation_id', '611000'),
                                 ('account_production_wip_account_id', '151000')):
            if field_name in self._fields and not self[field_name]:
                vals[field_name] = account(code).id
        self.write({k: v for k, v in vals.items() if k in self._fields})

        # Ürünsüz alış satırları (hizmet/gider) 150 İlk Madde yerine 770'e; ürünlü satırlar kategori hesabını kullanır
        gider = account('770000')
        for journal in self.env['account.journal'].search([('company_id', '=', self.id), ('type', '=', 'purchase')]):
            if gider and journal.default_account_id == account('150000'):
                journal.default_account_id = gider

    def _atlas_setup_export_positions(self):
        """İhracat, ihraç kayıtlı ve serbest bölge mali koşulları; %20/%10/%1 satış KDV'si yerine geçen vergilerle."""
        self.ensure_one()
        Tax = self.env['account.tax'].with_context(lang='tr_TR', active_test=False)
        FP = self.env['account.fiscal.position'].with_context(lang='tr_TR')
        sale_taxes = Tax.browse([t.id for t in (self._atlas_tr_ref('tr_s_20'), self._atlas_tr_ref('tr_s_10'),
                                                self._atlas_tr_ref('tr_s_1')) if t])
        zero = self._atlas_tr_ref('tr_s_0_ex')
        export_cancel = self._atlas_tr_ref('tr_wh_s_20')
        s20 = self._atlas_tr_ref('tr_s_20')
        if not (sale_taxes and zero):
            return
        country = self.env.ref('base.tr')
        for xml_name, name, gib in MALI_KOSULLAR:
            gib_kod = self.env.ref(f'atlas_muhasebe_base.gib_{gib}')
            imd = self.env['ir.model.data'].search([('module', '=', 'atlas_muhasebe_base'),
                                                    ('name', '=', f'{self.id}_{xml_name}')], limit=1)
            position = FP.browse(imd.res_id).exists() if imd else FP
            if not position:
                position = FP.create({'name': name, 'company_id': self.id, 'country_id': country.id,
                                      'atlas_gib_kod_id': gib_kod.id, 'sequence': 50})
                self.env['ir.model.data'].create({'module': 'atlas_muhasebe_base', 'name': f'{self.id}_{xml_name}',
                                                  'model': 'account.fiscal.position', 'res_id': position.id, 'noupdate': True})
            tax_name = f'KDV %0 - {name} ({gib})'
            if xml_name == 'fp_ihrac_kayitli' and s20 and export_cancel:
                tax_name = f'KDV %20 - {name} ({gib}, tahsil edilmeyen)'
            dest = Tax.search([('company_id', '=', self.id), ('name', '=', tax_name)], limit=1)
            if not dest:
                if xml_name == 'fp_ihrac_kayitli' and s20 and export_cancel:
                    dest = Tax.create({'name': tax_name, 'company_id': self.id, 'type_tax_use': 'sale',
                                       'amount_type': 'group', 'amount': 0, 'tax_group_id': s20.tax_group_id.id,
                                       'children_tax_ids': [Command.set([s20.id, export_cancel.id])],
                                       'country_id': country.id})
                else:
                    dest = zero.copy({'name': tax_name})
            dest.write({'atlas_gib_kod_id': gib_kod.id,
                        'fiscal_position_ids': [Command.set(position.ids)],
                        'original_tax_ids': [Command.set(sale_taxes.ids)]})
