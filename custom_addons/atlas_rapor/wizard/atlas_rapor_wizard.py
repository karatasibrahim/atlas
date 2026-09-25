import io
from collections import defaultdict

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date, formatLang

from ..models.tdhp import tdhp_name

RAPOR_SELECTION = [
    ('mizan', 'Mizan'),
    ('muavin', 'Büyük Defter (Muavin)'),
    ('yevmiye', 'Yevmiye Defteri'),
    ('bilanco', 'Bilanço'),
    ('gelir', 'Gelir Tablosu'),
    ('yaslandirma', 'Cari Yaşlandırma'),
    ('kdv', 'KDV Özeti'),
]

# Gelir tablosu (Tek Düzen): (harf, başlık, ana hesap önekleri) veya (None, ara toplam başlığı, None)
GELIR_TABLOSU = [
    ('A', 'BRÜT SATIŞLAR', ('600', '601', '602')),
    ('B', 'SATIŞ İNDİRİMLERİ (-)', ('610', '611', '612')),
    (None, 'NET SATIŞLAR', None),
    ('D', 'SATIŞLARIN MALİYETİ (-)', ('620', '621', '622', '623')),
    (None, 'BRÜT SATIŞ KÂRI VEYA ZARARI', None),
    ('E', 'FAALİYET GİDERLERİ (-)', ('630', '631', '632')),
    (None, 'FAALİYET KÂRI VEYA ZARARI', None),
    ('F', 'DİĞER FAALİYETLERDEN OLAĞAN GELİR VE KÂRLAR', tuple(str(c) for c in range(640, 650))),
    ('G', 'DİĞER FAALİYETLERDEN OLAĞAN GİDER VE ZARARLAR (-)', tuple(str(c) for c in range(653, 660))),
    ('H', 'FİNANSMAN GİDERLERİ (-)', ('660', '661')),
    (None, 'OLAĞAN KÂR VEYA ZARAR', None),
    ('I', 'OLAĞANDIŞI GELİR VE KÂRLAR', ('671', '679')),
    ('J', 'OLAĞANDIŞI GİDER VE ZARARLAR (-)', ('680', '681', '689')),
    (None, 'DÖNEM KÂRI VEYA ZARARI', None),
    ('K', 'DÖNEM KÂRI VERGİ VE DİĞER YASAL YÜKÜMLÜLÜK KARŞILIKLARI (-)', ('691',)),
    (None, 'DÖNEM NET KÂRI VEYA ZARARI', None),
]
# 7/A maliyet hesaplarının yansıtılmamış bakiyelerinin gelir tablosundaki yeri
YANSITMA_7A = {'71': 'D', '72': 'D', '73': 'D', '74': 'D', '75': 'E', '76': 'E', '77': 'E', '78': 'H'}
YASLANDIRMA_ARALIK = [(None, 0, 'Vadesi Gelmemiş'), (1, 30, '1-30 Gün'), (31, 60, '31-60 Gün'),
                      (61, 90, '61-90 Gün'), (91, 120, '91-120 Gün'), (121, None, '120+ Gün')]


def col(label, kind='text', width=12):
    return {'label': label, 'type': kind, 'width': width}


class AtlasRaporWizard(models.TransientModel):
    _name = 'atlas.rapor.wizard'
    _description = 'Muhasebe Raporu'

    rapor_turu = fields.Selection(RAPOR_SELECTION, string='Rapor', required=True, default='mizan')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Başlangıç', default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(string='Bitiş', required=True, default=fields.Date.context_today)
    seviye = fields.Selection([('1', 'Sınıf (1 hane)'), ('2', 'Grup (2 hane)'), ('3', 'Ana Hesap (3 hane)'),
                               ('detay', 'Detay (alt hesaplar)')], string='Seviye', default='3')
    hesap_baslangic = fields.Char(string='Hesap Kodundan', help='ör. 100 veya 120-00')
    hesap_bitis = fields.Char(string='Hesap Koduna', help='ör. 399')
    partner_ids = fields.Many2many('res.partner', string='Cariler')
    sadece_hareketli = fields.Boolean(string='Bakiyesi / Hareketi Olmayanları Gizle', default=True)
    taslak_dahil = fields.Boolean(string='Taslak Fişleri Dahil Et')
    kapanis_haric = fields.Boolean(
        string='Kapanış Fişlerini Hariç Tut', default=True,
        help='Rapor dönemindeki kapanış fişleri (gelir tablosu ve bilanço kapanışı) dikkate alınmaz; kapanış öncesi '
             'durum raporlanır. Önceki yılların kapanış fişleri devir için her zaman dahildir.')
    cari_tipi = fields.Selection([('alici', 'Alıcılar (120)'), ('satici', 'Satıcılar (320)')],
                                 string='Cari Tipi', default='alici')
    yansitma_dahil = fields.Boolean(
        string='Yansıtılmamış 7/A Maliyet Hesaplarını Dahil Et', default=True,
        help='Dönem sonu yansıtma kayıtları yapılmadıysa 7xx gider hesapları gelir tablosunda ilgili 6xx satırına eklenir.')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.rapor_turu not in ('bilanco', 'yaslandirma') and wizard.date_from and wizard.date_from > wizard.date_to:
                raise UserError(self.env._('Başlangıç tarihi bitiş tarihinden sonra olamaz.'))

    # -------------------------------------------------------------------------
    # Ortak yardımcılar
    # -------------------------------------------------------------------------

    def _base_domain(self):
        states = ('posted', 'draft') if self.taslak_dahil else ('posted',)
        domain = [('company_id', '=', self.company_id.id), ('parent_state', 'in', states), ('account_id', '!=', False)]
        if self.kapanis_haric and self.rapor_turu in ('mizan', 'bilanco', 'gelir', 'kdv'):
            # Yalnızca raporlanan döneme ait kapanış fişleri hariç; önceki yılların kapanışı devir için gereklidir
            cutoff = self.date_to.replace(month=1, day=1) if self.rapor_turu == 'bilanco' else self.date_from
            domain += ['|', ('move_id.atlas_fis_turu', '!=', 'kapanis'), ('date', '<', cutoff)]
        return domain

    def _code_in_range(self, code):
        start, end = (self.hesap_baslangic or '').strip(), (self.hesap_bitis or '').strip()
        if start and code[:len(start)] < start:
            return False
        if end and code[:len(end)] > end:
            return False
        return True

    def _account_totals(self, domain):
        """{hesap: (borç, alacak)}"""
        return {
            account: (debit, credit)
            for account, debit, credit in self.env['account.move.line']._read_group(
                self._base_domain() + domain, ['account_id'], ['debit:sum', 'credit:sum'])
        }

    def _period_label(self):
        if self.rapor_turu in ('bilanco', 'yaslandirma'):
            return f'{format_date(self.env, self.date_to)} tarihi itibarıyla'
        return f'{format_date(self.env, self.date_from)} - {format_date(self.env, self.date_to)}'

    @staticmethod
    def _row(cells, style='detail', level=0):
        return {'cells': cells, 'style': style, 'level': level}

    def _ba(self, amount):
        if self.company_id.currency_id.is_zero(amount):
            return ''
        return 'B' if amount > 0 else 'A'

    def _require_date_from(self):
        if not self.date_from:
            raise UserError(self.env._('Başlangıç tarihi gereklidir.'))

    # -------------------------------------------------------------------------
    # Rapor verisi
    # -------------------------------------------------------------------------

    def _get_report(self):
        self.ensure_one()
        data = getattr(self, f'_report_{self.rapor_turu}')()
        data.setdefault('title', dict(RAPOR_SELECTION)[self.rapor_turu])
        data.setdefault('subtitle', self._period_label())
        data['company'] = self.company_id
        data['currency'] = self.company_id.currency_id
        for row in data['rows']:
            row['display'] = [self._format_cell(cell, data['columns'][i]['type'] if i < len(data['columns']) else 'text')
                              for i, cell in enumerate(row['cells'])]
        return data

    def _format_cell(self, value, kind):
        if value is None or value is False or value == '':
            return ''
        if kind == 'money' and isinstance(value, (int, float)):
            return formatLang(self.env, value, digits=self.company_id.currency_id.decimal_places)
        if hasattr(value, 'year'):
            return format_date(self.env, value)
        if kind == 'number' and isinstance(value, float):
            return formatLang(self.env, value, digits=2).rstrip('0').rstrip(',.')
        return str(value)

    def _prefix_names(self):
        """3 haneli ana hesap -> sistemdeki ilk hesabın adı (TDHP şablonunda Türkçesi olmayanlar için)."""
        names = {}
        accounts = self.env['account.account'].with_company(self.company_id).search(
            [('company_ids', 'in', self.company_id.root_id.id)])
        for account in accounts.sorted('code'):
            names.setdefault((account.code or '')[:3], account.name)
        return names

    def _report_mizan(self):
        self._require_date_from()
        devir = self._account_totals([('date', '<', self.date_from)])
        donem = self._account_totals([('date', '>=', self.date_from), ('date', '<=', self.date_to)])
        accounts = self.env['account.account'].browse({a.id for a in (*devir, *donem)}).with_company(self.company_id)

        def key_of(code):
            return code if self.seviye == 'detay' else code[:int(self.seviye)]

        groups = defaultdict(lambda: [0.0] * 4)
        detail_parent = {}
        names = {}
        prefix_names = self._prefix_names()
        for account in accounts.sorted('code'):
            code = account.code or ''
            if not self._code_in_range(code):
                continue
            db, da = devir.get(account, (0.0, 0.0))
            pb, pa = donem.get(account, (0.0, 0.0))
            key = key_of(code)
            values = groups[key]
            for i, v in enumerate((db, da, pb, pa)):
                values[i] += v
            names[key] = account.name if self.seviye == 'detay' else tdhp_name(key, prefix_names.get(key))
            if self.seviye == 'detay':
                detail_parent[key] = code[:3]

        currency = self.company_id.currency_id
        rows, totals = [], [0.0] * 8
        parent_totals = defaultdict(lambda: [0.0] * 4)
        for key, values in groups.items():
            if self.seviye == 'detay':
                for i in range(4):
                    parent_totals[detail_parent[key]][i] += values[i]

        def make_cells(code, name, values):
            db, da, pb, pa = values
            tb, ta = db + pb, da + pa
            bakiye = tb - ta
            return [code, name, db, da, pb, pa, tb, ta, max(bakiye, 0.0), max(-bakiye, 0.0)]

        last_parent = None
        for key in sorted(groups):
            values = groups[key]
            cells = make_cells(key, names[key], values)
            if self.sadece_hareketli and all(currency.is_zero(v) for v in cells[2:]):
                continue
            if self.seviye == 'detay' and detail_parent[key] != last_parent:
                last_parent = detail_parent[key]
                rows.append(self._row(make_cells(last_parent, tdhp_name(last_parent, prefix_names.get(last_parent)), parent_totals[last_parent]), 'group'))
            rows.append(self._row(cells, 'detail', 1 if self.seviye == 'detay' else 0))
            for i in range(8):
                totals[i] += cells[2 + i]
        rows.append(self._row(['', 'GENEL TOPLAM'] + totals, 'total'))
        money = lambda label: col(label, 'money', 13)  # noqa: E731
        return {
            'columns': [col('Hesap Kodu', 'text', 13), col('Hesap Adı', 'text', 34), money('Devir Borç'), money('Devir Alacak'),
                        money('Dönem Borç'), money('Dönem Alacak'), money('Toplam Borç'), money('Toplam Alacak'),
                        money('Borç Bakiye'), money('Alacak Bakiye')],
            'rows': rows,
            'landscape': True,
            'indent_col': 1,
        }

    def _report_muavin(self):
        self._require_date_from()
        Line = self.env['account.move.line']
        extra = [('partner_id', 'child_of', self.partner_ids.ids)] if self.partner_ids else []
        devir = self._account_totals([('date', '<', self.date_from)] + extra)
        lines = Line.search(self._base_domain() + extra + [('date', '>=', self.date_from), ('date', '<=', self.date_to)],
                            order='date, move_name, id')
        by_account = lines.grouped('account_id')
        accounts = (self.env['account.account'].browse({a.id for a in devir}) | lines.account_id).with_company(self.company_id)
        currency = self.company_id.currency_id
        rows = []
        grand_debit = grand_credit = 0.0
        for account in accounts.sorted('code'):
            if not self._code_in_range(account.code or ''):
                continue
            db, da = devir.get(account, (0.0, 0.0))
            account_lines = by_account.get(account, Line)
            if self.sadece_hareketli and not account_lines and currency.is_zero(db - da):
                continue
            rows.append(self._row([f'{account.code}  {account.name}'], 'section'))
            balance = db - da
            rows.append(self._row(['', '', '', 'DEVİR', '', db, da, abs(balance), self._ba(balance)], 'group'))
            for line in account_lines:
                balance += line.debit - line.credit
                partner = line.partner_id.commercial_partner_id
                rows.append(self._row([
                    line.date, line.move_name, line.move_id.ref or '', line.name or '',
                    f'{partner.ref or ""} {partner.name}'.strip() if partner else '',
                    line.debit, line.credit, abs(balance), self._ba(balance)]))
            period_debit, period_credit = sum(account_lines.mapped('debit')), sum(account_lines.mapped('credit'))
            grand_debit += period_debit
            grand_credit += period_credit
            rows.append(self._row(['', '', '', 'HESAP TOPLAMI', '', db + period_debit, da + period_credit, abs(balance), self._ba(balance)], 'total'))
        rows.append(self._row(['', '', '', 'DÖNEM HAREKET TOPLAMI', '', grand_debit, grand_credit, '', ''], 'total'))
        return {
            'columns': [col('Tarih', 'date', 11), col('Fiş No', 'text', 17), col('Evrak No', 'text', 14), col('Açıklama', 'text', 34),
                        col('Cari', 'text', 24), col('Borç', 'money', 13), col('Alacak', 'money', 13), col('Bakiye', 'money', 13), col('B/A', 'text', 4)],
            'rows': rows,
            'landscape': True,
        }

    def _report_yevmiye(self):
        self._require_date_from()
        Move = self.env['account.move']
        states = ('posted', 'draft') if self.taslak_dahil else ('posted',)
        moves = Move.search([('company_id', '=', self.company_id.id), ('state', 'in', states),
                             ('date', '>=', self.date_from), ('date', '<=', self.date_to)], order='date, name, id')
        # Kesin madde no yoksa: mali yıl başından itibaren sıra
        year_start = self.date_from.replace(month=1, day=1)
        madde = Move.search_count([('company_id', '=', self.company_id.id), ('state', 'in', states),
                                   ('date', '>=', year_start), ('date', '<', self.date_from)])
        rows = []
        prefix_names = self._prefix_names()
        total_debit = total_credit = 0.0
        for move in moves:
            madde += 1
            no = move.atlas_yevmiye_no or madde
            rows.append(self._row([no, move.date, f'{move.name}  {move.ref or ""}'.strip(), '', '', '', ''], 'section'))
            for side, field in (('debit', 'debit'), ('credit', 'credit')):
                side_lines = move.line_ids.filtered(lambda l: l[field] and l.account_id).with_company(self.company_id)
                for main_code, group in side_lines.grouped(lambda l: (l.account_id.code or '')[:3]).items():
                    amount = sum(group.mapped(field))
                    rows.append(self._row(['', '', f'{main_code}  {tdhp_name(main_code, prefix_names.get(main_code))}', '',
                                           amount if side == 'debit' else '', amount if side == 'credit' else ''], 'group',
                                          0 if side == 'debit' else 2))
                    for line in group:
                        label = f'{line.account_id.code}  {line.account_id.name}'
                        if line.name:
                            label += f' — {line.name}'
                        rows.append(self._row(['', '', label, line[field], '', ''], 'detail', 1 if side == 'debit' else 3))
            move_debit = sum(move.line_ids.mapped('debit'))
            move_credit = sum(move.line_ids.mapped('credit'))
            total_debit += move_debit
            total_credit += move_credit
        rows.append(self._row(['', '', 'GENEL TOPLAM', '', total_debit, total_credit], 'total'))
        return {
            'columns': [col('Madde', 'text', 7), col('Tarih', 'date', 11), col('Hesap / Açıklama', 'text', 60),
                        col('Detay', 'money', 14), col('Borç', 'money', 14), col('Alacak', 'money', 14)],
            'rows': rows,
            'landscape': False,
            'indent_col': 2,
        }

    def _main_account_balances(self, domain):
        """{3 haneli ana hesap: bakiye (borç - alacak)}"""
        result = defaultdict(float)
        for account, (debit, credit) in self._account_totals(domain).items():
            code = account.with_company(self.company_id).code or ''
            result[code[:3]] += debit - credit
        return result

    def _report_bilanco(self):
        balances = self._main_account_balances([('date', '<=', self.date_to)])
        currency = self.company_id.currency_id
        net_result = -sum(v for k, v in balances.items() if k[:1] in ('6', '7'))
        prefix_names = self._prefix_names()
        rows = []
        side_totals = {}
        for side, title, classes, sign in (('aktif', 'AKTİF (VARLIKLAR)', '12', 1), ('pasif', 'PASİF (KAYNAKLAR)', '345', -1)):
            rows.append(self._row(['', title, ''], 'section'))
            side_total = 0.0
            for cls in classes:
                cls_codes = sorted(k for k in balances if k[:1] == cls)
                cls_total = sign * sum(balances[k] for k in cls_codes) + (net_result if cls == '5' else 0.0)
                rows.append(self._row([cls, tdhp_name(cls), cls_total], 'group'))
                groups = sorted({k[:2] for k in cls_codes} | ({'59'} if cls == '5' and not currency.is_zero(net_result) else set()))
                for grp in groups:
                    grp_codes = [k for k in cls_codes if k[:2] == grp]
                    grp_total = sign * sum(balances[k] for k in grp_codes) + (net_result if grp == '59' else 0.0)
                    if self.sadece_hareketli and currency.is_zero(grp_total):
                        continue
                    rows.append(self._row([grp, tdhp_name(grp), grp_total], 'group', 1))
                    if self.seviye in ('3', 'detay'):
                        for code in grp_codes:
                            amount = sign * balances[code]
                            if not (self.sadece_hareketli and currency.is_zero(amount)):
                                rows.append(self._row([code, tdhp_name(code, prefix_names.get(code)), amount], 'detail', 2))
                        if grp == '59' and not currency.is_zero(net_result):
                            label = 'DÖNEM NET KÂRI' if net_result > 0 else 'DÖNEM NET ZARARI (-)'
                            rows.append(self._row(['590' if net_result > 0 else '591', f'{label} (kapanmamış sonuç hesapları)', net_result], 'detail', 2))
                side_total += cls_total
            rows.append(self._row(['', f'{title} TOPLAMI', side_total], 'total'))
            side_totals[side] = side_total
        fark = side_totals['aktif'] - side_totals['pasif']
        subtitle = self._period_label()
        if not currency.is_zero(fark):
            subtitle += f' — UYARI: aktif/pasif farkı {fark:,.2f}'
        return {
            'columns': [col('Kod', 'text', 8), col('Hesap', 'text', 60), col('Tutar', 'money', 18)],
            'rows': rows,
            'subtitle': subtitle,
            'landscape': False,
            'indent_col': 1,
        }

    def _report_gelir(self):
        self._require_date_from()
        balances = self._main_account_balances([('date', '>=', self.date_from), ('date', '<=', self.date_to)])
        currency = self.company_id.currency_id
        section_of = {}
        for letter, _title, prefixes in GELIR_TABLOSU:
            for prefix in prefixes or ():
                section_of[prefix] = letter
        section_codes = defaultdict(list)
        for code in balances:
            if code in section_of:
                section_codes[section_of[code]].append(code)
            elif self.yansitma_dahil and code[:2] in YANSITMA_7A:
                section_codes[YANSITMA_7A[code[:2]]].append(code)

        rows, running = [], 0.0
        prefix_names = self._prefix_names()
        for letter, title, prefixes in GELIR_TABLOSU:
            if letter is None:
                rows.append(self._row(['', title, running], 'total'))
                continue
            codes = sorted(section_codes.get(letter, []))
            amount = -sum(balances[c] for c in codes)
            running += amount
            rows.append(self._row([letter, title, amount], 'group'))
            for code in codes:
                value = -balances[code]
                if not (self.sadece_hareketli and currency.is_zero(value)):
                    suffix = ' (yansıtılmamış)' if code[:1] == '7' else ''
                    rows.append(self._row([code, tdhp_name(code, prefix_names.get(code)) + suffix, value], 'detail', 1))
        return {
            'columns': [col('', 'text', 6), col('Açıklama', 'text', 66), col('Tutar', 'money', 18)],
            'rows': rows,
            'landscape': False,
            'indent_col': 1,
        }

    def _report_yaslandirma(self):
        account_type = 'asset_receivable' if self.cari_tipi == 'alici' else 'liability_payable'
        sign = 1 if self.cari_tipi == 'alici' else -1
        domain = [('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
                  ('account_id.account_type', '=', account_type), ('reconciled', '=', False),
                  ('amount_residual', '!=', 0), ('date', '<=', self.date_to)]
        if self.partner_ids:
            domain.append(('partner_id', 'child_of', self.partner_ids.ids))
        lines = self.env['account.move.line'].search(domain)
        buckets = defaultdict(lambda: [0.0] * len(YASLANDIRMA_ARALIK))
        for line in lines:
            days = (self.date_to - (line.date_maturity or line.date)).days
            for index, (low, high, _label) in enumerate(YASLANDIRMA_ARALIK):
                if (low is None and days < 1) or (low is not None and days >= low and (high is None or days <= high)):
                    buckets[line.partner_id.commercial_partner_id][index] += sign * line.amount_residual
                    break
        rows, totals = [], [0.0] * (len(YASLANDIRMA_ARALIK) + 1)
        for partner in sorted(buckets, key=lambda p: (p.ref or '', p.name or '')):
            values = buckets[partner]
            total = sum(values)
            if self.company_id.currency_id.is_zero(total) and self.sadece_hareketli:
                continue
            rows.append(self._row([partner.ref or '', partner.name] + values + [total]))
            for i, v in enumerate(values + [total]):
                totals[i] += v
        rows.append(self._row(['', 'TOPLAM'] + totals, 'total'))
        return {
            'title': f'Cari Yaşlandırma — {dict(self._fields["cari_tipi"].selection)[self.cari_tipi]}',
            'columns': [col('Cari Kodu', 'text', 13), col('Cari Adı', 'text', 32)]
                       + [col(label, 'money', 13) for _l, _h, label in YASLANDIRMA_ARALIK] + [col('Toplam', 'money', 14)],
            'rows': rows,
            'landscape': True,
        }

    def _report_kdv(self):
        self._require_date_from()
        Line = self.env['account.move.line']
        domain = self._base_domain() + [('date', '>=', self.date_from), ('date', '<=', self.date_to)]
        tax_amounts = {tax: balance for tax, balance in Line._read_group(
            domain + [('tax_line_id', '!=', False)], ['tax_line_id'], ['balance:sum'])}
        base_amounts = {tax: balance for tax, balance in Line._read_group(
            domain + [('tax_ids', '!=', False)], ['tax_ids'], ['balance:sum'])}
        taxes = self.env['account.tax'].browse({t.id for t in (*tax_amounts, *base_amounts)})
        rows = []
        results = {}
        for use, title, sign in (('sale', 'SATIŞLAR — HESAPLANAN VERGİLER', -1), ('purchase', 'ALIŞLAR — İNDİRİLECEK VERGİLER', 1)):
            rows.append(self._row([title, '', '', ''], 'section'))
            base_total = tax_total = 0.0
            for tax in taxes.filtered(lambda t: t.type_tax_use == use).sorted(lambda t: (t.tax_group_id.name or '', t.amount)):
                base = sign * base_amounts.get(tax, 0.0)
                amount = sign * tax_amounts.get(tax, 0.0)
                rows.append(self._row([tax.name, tax.amount, base, amount]))
                base_total += base
                tax_total += amount
            rows.append(self._row(['Toplam', '', base_total, tax_total], 'total'))
            results[use] = tax_total
        fark = results['sale'] - results['purchase']
        rows.append(self._row(['ÖDENECEK VERGİ' if fark > 0 else 'DEVREDEN VERGİ', '', '', abs(fark)], 'total'))
        return {
            'columns': [col('Vergi', 'text', 40), col('Oran %', 'number', 9), col('Matrah', 'money', 16), col('Vergi Tutarı', 'money', 16)],
            'rows': rows,
            'landscape': False,
        }

    # -------------------------------------------------------------------------
    # Çıktılar
    # -------------------------------------------------------------------------

    def action_html(self):
        return self.env.ref('atlas_rapor.action_report_atlas_rapor_html').report_action(self)

    def action_pdf(self):
        self.ensure_one()
        report = 'atlas_rapor.action_report_atlas_rapor_pdf_landscape' if self._get_report().get('landscape') \
            else 'atlas_rapor.action_report_atlas_rapor_pdf'
        return self.env.ref(report).report_action(self)

    def action_xlsx(self):
        self.ensure_one()
        data = self._get_report()
        attachment = self.env['ir.attachment'].create({
            'name': f'{data["title"]} {self.date_to:%d.%m.%Y}.xlsx',
            'raw': self._build_xlsx(data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'download'}

    def _build_xlsx(self, data):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(data['title'][:31])
        base = {'font_size': 10}
        formats = {}
        for style in ('detail', 'group', 'total', 'section'):
            extra = {'bold': style != 'detail'}
            if style == 'section':
                extra['bg_color'] = '#D9E1F2'
            if style == 'total':
                extra['top'] = 1
            formats[style] = {
                'text': workbook.add_format({**base, **extra}),
                'money': workbook.add_format({**base, **extra, 'num_format': '#,##0.00'}),
                'number': workbook.add_format({**base, **extra, 'num_format': '0.##'}),
                'date': workbook.add_format({**base, **extra, 'num_format': 'dd.mm.yyyy'}),
            }
        header = workbook.add_format({'bold': True, 'bg_color': '#BDD7EE', 'border': 1, 'font_size': 10})
        sheet.write(0, 0, f'{data["company"].name} — {data["title"]}', workbook.add_format({'bold': True, 'font_size': 13}))
        sheet.write(1, 0, data['subtitle'])
        for index, column in enumerate(data['columns']):
            sheet.set_column(index, index, column['width'])
            sheet.write(3, index, column['label'], header)
        row_index = 4
        for row in data['rows']:
            for index, value in enumerate(row['cells']):
                kind = data['columns'][index]['type'] if index < len(data['columns']) else 'text'
                fmt = formats[row['style']][kind if kind in ('money', 'number', 'date') else 'text']
                if value in (None, '') or value is False:
                    sheet.write_blank(row_index, index, None, fmt)
                elif kind == 'date' and hasattr(value, 'year'):
                    sheet.write_datetime(row_index, index, fields.Datetime.to_datetime(value), fmt)
                elif isinstance(value, (int, float)) and kind in ('money', 'number'):
                    sheet.write_number(row_index, index, value, fmt)
                else:
                    text = str(value)
                    if index == data.get('indent_col'):
                        text = '    ' * row['level'] + text
                    sheet.write(row_index, index, text, fmt)
            row_index += 1
        workbook.close()
        return output.getvalue()
