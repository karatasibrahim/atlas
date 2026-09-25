import hashlib
import io

from odoo import fields, models
from odoo.exceptions import UserError


class AtlasBankaEkstreImport(models.TransientModel):
    _name = 'atlas.banka.ekstre.import'
    _description = 'Banka Ekstresi İçe Aktar'

    journal_id = fields.Many2one('account.journal', string='Banka Hesabı', required=True,
                                 domain=[('type', '=', 'bank')])
    sablon_id = fields.Many2one('atlas.banka.ekstre.sablon', string='Şablon',
                                help='Boş bırakılırsa sütunlar başlıklardan otomatik algılanır.')
    file = fields.Binary(string='Excel Dosyası (.xlsx)', required=True)
    filename = fields.Char()
    oner = fields.Boolean(string='Eşleştirme Önerilerini Oluştur', default=True)

    def action_import(self):
        self.ensure_one()
        transactions = self.sablon_id._parse_rows(self._read_rows())
        if not transactions:
            raise UserError(self.env._('Ekstrede aktarılacak hareket bulunamadı.'))

        StLine = self.env['account.bank.statement.line']
        hashes = [self._hash(t) for t in transactions]
        existing = set(StLine.search([('journal_id', '=', self.journal_id.id),
                                      ('atlas_import_hash', 'in', hashes)]).mapped('atlas_import_hash'))
        new = [(t, h) for t, h in zip(transactions, hashes) if h not in existing]
        if not new:
            raise UserError(self.env._('Bu ekstredeki tüm hareketler daha önce aktarılmış.'))

        first, last = new[0][0], new[-1][0]
        statement_vals = {
            'name': f'{self.journal_id.code} {first["date"]:%d.%m.%Y} - {last["date"]:%d.%m.%Y}',
            'journal_id': self.journal_id.id,
            'line_ids': [fields.Command.create({
                'date': t['date'],
                'payment_ref': t['aciklama'] or t['referans'] or '/',
                'amount': t['amount'],
                'journal_id': self.journal_id.id,
                'atlas_referans': t['referans'],
                'atlas_ekstre_bakiye': t['bakiye'] or 0.0,
                'atlas_import_hash': h,
            }) for t, h in new],
        }
        if first['bakiye'] is not None and last['bakiye'] is not None:
            statement_vals['balance_start'] = first['bakiye'] - first['amount']
            statement_vals['balance_end_real'] = last['bakiye']
        statement = self.env['account.bank.statement'].create(statement_vals)
        if self.oner:
            statement.line_ids.action_atlas_oner()

        action = self.env['ir.actions.act_window']._for_xml_id('atlas_kasa_banka.action_atlas_banka_eslestirme')
        action['domain'] = [('statement_id', '=', statement.id)]
        action['display_name'] = self.env._('%(name)s — %(new)s hareket aktarıldı, %(skip)s tekrar atlandı',
                                            name=statement.name, new=len(new), skip=len(transactions) - len(new))
        return action

    def _read_rows(self):
        filename = self.filename or self.file.filename
        if filename and not filename.lower().endswith(('.xlsx', '.xlsm')):
            raise UserError(self.env._('Yalnızca .xlsx dosyaları desteklenir. Eski .xls dosyasını Excel\'de .xlsx olarak kaydedin.'))
        import openpyxl  # noqa: PLC0415

        try:
            workbook = openpyxl.load_workbook(io.BytesIO(self.file.content), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise UserError(self.env._('Excel dosyası okunamadı: %s', e)) from e
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]

    def _hash(self, transaction):
        key = '|'.join(str(v) for v in (
            self.journal_id.id, transaction['date'], f'{transaction["amount"]:.2f}',
            transaction['aciklama'], transaction['bakiye'], transaction['referans']))
        return hashlib.sha1(key.encode()).hexdigest()
