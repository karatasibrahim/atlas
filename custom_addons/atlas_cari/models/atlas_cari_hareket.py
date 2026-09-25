from odoo import fields, models, tools
from odoo.tools import SQL

HAREKET_TURU_SELECTION = [
    ('satis_fatura', 'Satış Faturası'),
    ('satis_iade', 'Satış İadesi'),
    ('alis_fatura', 'Alış Faturası'),
    ('alis_iade', 'Alış İadesi'),
    ('tahsilat', 'Tahsilat'),
    ('odeme', 'Ödeme'),
    ('banka', 'Banka Hareketi'),
    ('mahsup', 'Mahsup'),
]


class AtlasCariHareket(models.Model):
    """Cari hareketleri: onaylı fişlerdeki 120/320 (alacak/borç) satırları, cari bazında yürüyen bakiyeyle.

    Yürüyen bakiye, carinin şirketteki tüm hareketleri üzerinden hesaplanır; tarih filtresi
    uygulansa da her satırın bakiyesi o satıra kadarki gerçek bakiyedir.
    """
    _name = 'atlas.cari.hareket'
    _description = 'Cari Hareketi'
    _auto = False
    _order = 'date, move_id, id'
    _rec_name = 'move_name'
    _depends = {
        'account.move.line': [
            'account_id', 'partner_id', 'date', 'date_maturity', 'name', 'company_id', 'journal_id', 'move_id',
            'debit', 'credit', 'balance', 'amount_currency', 'currency_id', 'amount_residual', 'reconciled', 'parent_state',
        ],
        'account.move': ['name', 'ref', 'move_type', 'state', 'statement_line_id', 'origin_payment_id'],
        'account.payment': ['payment_type'],
        'res.partner': ['commercial_partner_id', 'ref'],
        'account.account': ['account_type'],
    }

    move_id = fields.Many2one('account.move', string='Fiş', readonly=True)
    move_name = fields.Char(string='Fiş No', readonly=True)
    date = fields.Date(string='Tarih', readonly=True)
    date_maturity = fields.Date(string='Vade', readonly=True)
    company_id = fields.Many2one('res.company', string='Şirket', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Yevmiye', readonly=True)
    account_id = fields.Many2one('account.account', string='Hesap', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cari', readonly=True)
    cari_kodu = fields.Char(string='Cari Kodu', readonly=True)
    hareket_turu = fields.Selection(HAREKET_TURU_SELECTION, string='Hareket Türü', readonly=True)
    evrak_no = fields.Char(string='Evrak No', readonly=True)
    aciklama = fields.Char(string='Açıklama', readonly=True)
    company_currency_id = fields.Many2one('res.currency', readonly=True)
    debit = fields.Monetary(string='Borç', readonly=True, currency_field='company_currency_id')
    credit = fields.Monetary(string='Alacak', readonly=True, currency_field='company_currency_id')
    balance = fields.Monetary(string='Tutar', readonly=True, currency_field='company_currency_id')
    bakiye = fields.Monetary(string='Bakiye', readonly=True, currency_field='company_currency_id', aggregator=None)
    currency_id = fields.Many2one('res.currency', string='Döviz', readonly=True)
    amount_currency = fields.Monetary(string='Döviz Tutarı', readonly=True, currency_field='currency_id')
    amount_residual = fields.Monetary(string='Açık Tutar', readonly=True, currency_field='company_currency_id')
    reconciled = fields.Boolean(string='Kapandı', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    aml.id,
                    aml.move_id,
                    move.name AS move_name,
                    aml.date,
                    aml.date_maturity,
                    aml.company_id,
                    aml.journal_id,
                    aml.account_id,
                    partner.commercial_partner_id AS partner_id,
                    commercial.ref AS cari_kodu,
                    %(hareket_turu)s AS hareket_turu,
                    move.ref AS evrak_no,
                    aml.name AS aciklama,
                    aml.company_currency_id,
                    aml.debit,
                    aml.credit,
                    aml.balance,
                    SUM(aml.balance) OVER (
                        PARTITION BY aml.company_id, partner.commercial_partner_id
                        ORDER BY aml.date, aml.move_id, aml.id
                    ) AS bakiye,
                    aml.currency_id,
                    aml.amount_currency,
                    aml.amount_residual,
                    aml.reconciled
                FROM account_move_line aml
                JOIN account_move move ON move.id = aml.move_id
                JOIN account_account account ON account.id = aml.account_id
                JOIN res_partner partner ON partner.id = aml.partner_id
                JOIN res_partner commercial ON commercial.id = partner.commercial_partner_id
                LEFT JOIN account_payment payment ON payment.id = move.origin_payment_id
                WHERE aml.parent_state = 'posted'
                  AND account.account_type IN ('asset_receivable', 'liability_payable')
            )
        """, table=SQL.identifier(self._table), hareket_turu=self._hareket_turu_sql()))

    def _hareket_turu_sql(self):
        """Hareket türü ifadesi; alt modüller (ör. fiş türleri) başa WHEN ekleyerek genişletir."""
        return SQL("CASE %s END", self._hareket_turu_when_sql())

    def _hareket_turu_when_sql(self):
        return SQL("""
            WHEN move.move_type IN ('out_invoice', 'out_receipt') THEN 'satis_fatura'
            WHEN move.move_type = 'out_refund' THEN 'satis_iade'
            WHEN move.move_type IN ('in_invoice', 'in_receipt') THEN 'alis_fatura'
            WHEN move.move_type = 'in_refund' THEN 'alis_iade'
            WHEN payment.payment_type = 'inbound' THEN 'tahsilat'
            WHEN payment.payment_type = 'outbound' THEN 'odeme'
            WHEN move.statement_line_id IS NOT NULL THEN 'banka'
            ELSE 'mahsup'
        """)

    def action_open_move(self):
        self.ensure_one()
        return self.move_id._get_records_action()
