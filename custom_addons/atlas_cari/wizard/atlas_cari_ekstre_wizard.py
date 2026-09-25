import io

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date


class AtlasCariEkstreWizard(models.TransientModel):
    _name = 'atlas.cari.ekstre.wizard'
    _description = 'Cari Ekstre'

    partner_ids = fields.Many2many(
        'res.partner', string='Cariler', required=True,
        domain=[('atlas_cari_tipi', '!=', False)],
    )
    date_from = fields.Date(
        string='Başlangıç Tarihi', required=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
    )
    date_to = fields.Date(string='Bitiş Tarihi', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    show_currency = fields.Boolean(string='Döviz Tutarlarını Göster')
    hide_empty = fields.Boolean(string='Hareketsiz Carileri Gösterme', default=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(self.env._('Başlangıç tarihi bitiş tarihinden sonra olamaz.'))

    # -------------------------------------------------------------------------
    # Veri
    # -------------------------------------------------------------------------

    def _get_ekstre_data(self):
        """Her cari için devir, dönem hareketleri (yürüyen bakiyeli) ve toplamları döndürür."""
        self.ensure_one()
        Hareket = self.env['atlas.cari.hareket']
        partners = self.partner_ids.commercial_partner_id.sorted(lambda p: (p.ref or '', p.name or ''))
        base_domain = [('company_id', '=', self.company_id.id)]

        devir_by_partner = {
            partner.id: balance
            for partner, balance in Hareket._read_group(
                base_domain + [('partner_id', 'in', partners.ids), ('date', '<', self.date_from)],
                ['partner_id'], ['balance:sum'],
            )
        }
        lines_by_partner = Hareket.search(
            base_domain + [('partner_id', 'in', partners.ids),
                           ('date', '>=', self.date_from), ('date', '<=', self.date_to)],
        ).grouped('partner_id')

        turu_labels = dict(Hareket._fields['hareket_turu'].selection)
        result = []
        for partner in partners:
            devir = devir_by_partner.get(partner.id, 0.0)
            hareketler = lines_by_partner.get(partner, Hareket)
            if self.hide_empty and not hareketler and not self.company_id.currency_id.round(devir):
                continue
            running = devir
            lines = []
            for h in hareketler:
                running += h.balance
                lines.append({
                    'date': h.date,
                    'move_name': h.move_name,
                    'evrak_no': h.evrak_no or '',
                    'hareket_turu': turu_labels.get(h.hareket_turu, ''),
                    'aciklama': h.aciklama or '',
                    'date_maturity': h.date_maturity,
                    'debit': h.debit,
                    'credit': h.credit,
                    'bakiye': running,
                    'currency': h.currency_id if h.currency_id != h.company_currency_id else False,
                    'amount_currency': h.amount_currency,
                })
            result.append({
                'partner': partner,
                'devir': devir,
                'lines': lines,
                'total_debit': sum(hareketler.mapped('debit')),
                'total_credit': sum(hareketler.mapped('credit')),
                'kapanis': running,
            })
        return result

    def _ba(self, amount):
        """Bakiye yönü: B (borçlu) / A (alacaklı)."""
        currency = self.company_id.currency_id or self.env.company.currency_id
        if currency.is_zero(amount):
            return ''
        return 'B' if amount > 0 else 'A'

    # -------------------------------------------------------------------------
    # Çıktılar
    # -------------------------------------------------------------------------

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('atlas_cari.action_report_atlas_cari_ekstre').report_action(self)

    def action_print_html(self):
        self.ensure_one()
        return self.env.ref('atlas_cari.action_report_atlas_cari_ekstre_html').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        content = self._build_xlsx()
        filename = f'Cari_Ekstre_{self.date_from:%d%m%Y}_{self.date_to:%d%m%Y}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'raw': content,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'download',
        }

    def _build_xlsx(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Cari Ekstre')
        bold = workbook.add_format({'bold': True})
        title = workbook.add_format({'bold': True, 'font_size': 13})
        header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
        money = workbook.add_format({'num_format': '#,##0.00'})
        money_bold = workbook.add_format({'num_format': '#,##0.00', 'bold': True, 'top': 1})
        date_fmt = workbook.add_format({'num_format': 'dd.mm.yyyy'})

        columns = ['Tarih', 'Fiş No', 'Evrak No', 'Hareket Türü', 'Açıklama', 'Vade', 'Borç', 'Alacak', 'Bakiye', 'B/A']
        if self.show_currency:
            columns += ['Döviz Tutarı', 'Döviz']
        widths = [11, 18, 16, 16, 40, 11, 14, 14, 14, 5, 14, 7]
        for col, width in enumerate(widths[:len(columns)]):
            sheet.set_column(col, col, width)

        row = 0
        sheet.write(row, 0, f'{self.company_id.name} - Cari Hesap Ekstresi', title)
        row += 1
        sheet.write(row, 0, f'{format_date(self.env, self.date_from)} - {format_date(self.env, self.date_to)}')
        row += 2

        for data in self._get_ekstre_data():
            partner = data['partner']
            sheet.write(row, 0, f'{partner.ref or ""}  {partner.name}', bold)
            if partner.vat:
                sheet.write(row, 4, f'VKN/TCKN: {partner.vat}')
            row += 1
            for col, name in enumerate(columns):
                sheet.write(row, col, name, header)
            row += 1
            sheet.write(row, 4, 'DEVİR', bold)
            sheet.write_number(row, 8, abs(data['devir']), money)
            sheet.write(row, 9, self._ba(data['devir']))
            row += 1
            for line in data['lines']:
                sheet.write_datetime(row, 0, fields.Datetime.to_datetime(line['date']), date_fmt)
                sheet.write(row, 1, line['move_name'] or '')
                sheet.write(row, 2, line['evrak_no'])
                sheet.write(row, 3, line['hareket_turu'])
                sheet.write(row, 4, line['aciklama'])
                if line['date_maturity']:
                    sheet.write_datetime(row, 5, fields.Datetime.to_datetime(line['date_maturity']), date_fmt)
                sheet.write_number(row, 6, line['debit'], money)
                sheet.write_number(row, 7, line['credit'], money)
                sheet.write_number(row, 8, abs(line['bakiye']), money)
                sheet.write(row, 9, self._ba(line['bakiye']))
                if self.show_currency and line['currency']:
                    sheet.write_number(row, 10, line['amount_currency'], money)
                    sheet.write(row, 11, line['currency'].name)
                row += 1
            sheet.write(row, 4, 'TOPLAM', bold)
            sheet.write_number(row, 6, data['total_debit'], money_bold)
            sheet.write_number(row, 7, data['total_credit'], money_bold)
            sheet.write_number(row, 8, abs(data['kapanis']), money_bold)
            sheet.write(row, 9, self._ba(data['kapanis']), bold)
            row += 3

        workbook.close()
        return output.getvalue()
