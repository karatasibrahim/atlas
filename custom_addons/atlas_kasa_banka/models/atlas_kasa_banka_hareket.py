from odoo import fields, models, tools
from odoo.tools import SQL

HAREKET_TURU_SELECTION = [
    ('tahsil', 'Tahsil Fişi'),
    ('tediye', 'Tediye Fişi'),
    ('tahsilat', 'Tahsilat'),
    ('odeme', 'Ödeme'),
    ('ekstre', 'Banka Ekstresi'),
    ('virman', 'Virman'),
    ('acilis', 'Açılış'),
    ('mahsup', 'Mahsup / Diğer'),
]


class AtlasKasaBankaHareket(models.Model):
    """Kasa ve banka hesaplarının onaylı hareketleri; hesabın kendi para biriminde yürüyen bakiyeyle."""
    _name = 'atlas.kasa.banka.hareket'
    _description = 'Kasa / Banka Hareketi'
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
        'account.journal': ['type', 'default_account_id', 'currency_id'],
    }

    journal_id = fields.Many2one('account.journal', string='Kasa / Banka', readonly=True)
    journal_type = fields.Selection([('cash', 'Kasa'), ('bank', 'Banka')], string='Tür', readonly=True)
    account_id = fields.Many2one('account.account', string='Hesap', readonly=True)
    company_id = fields.Many2one('res.company', string='Şirket', readonly=True)
    move_id = fields.Many2one('account.move', string='Fiş', readonly=True)
    move_name = fields.Char(string='Fiş No', readonly=True)
    date = fields.Date(string='Tarih', readonly=True)
    evrak_no = fields.Char(string='Evrak No', readonly=True)
    aciklama = fields.Char(string='Açıklama', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cari', readonly=True)
    hareket_turu = fields.Selection(HAREKET_TURU_SELECTION, string='Hareket Türü', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Para Birimi', readonly=True)
    giris = fields.Monetary(string='Giriş', readonly=True, currency_field='currency_id')
    cikis = fields.Monetary(string='Çıkış', readonly=True, currency_field='currency_id')
    tutar = fields.Monetary(string='Tutar', readonly=True, currency_field='currency_id')
    bakiye = fields.Monetary(string='Bakiye', readonly=True, currency_field='currency_id', aggregator=None)
    company_currency_id = fields.Many2one('res.currency', readonly=True)
    tutar_tl = fields.Monetary(string='TL Karşılığı', readonly=True, currency_field='company_currency_id')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                WITH liquidity AS (
                    SELECT DISTINCT ON (default_account_id) id AS journal_id, type, default_account_id, currency_id
                      FROM account_journal
                     WHERE type IN ('cash', 'bank') AND default_account_id IS NOT NULL
                  ORDER BY default_account_id, id
                ), lines AS (
                    SELECT aml.*,
                           liq.journal_id AS liquidity_journal_id,
                           liq.type AS liquidity_type,
                           COALESCE(liq.currency_id, aml.company_currency_id) AS hesap_currency_id,
                           CASE WHEN liq.currency_id IS NOT NULL AND liq.currency_id != aml.company_currency_id
                                THEN aml.amount_currency ELSE aml.balance END AS hesap_tutar
                      FROM account_move_line aml
                      JOIN liquidity liq ON liq.default_account_id = aml.account_id
                     WHERE aml.parent_state = 'posted'
                )
                SELECT
                    l.id,
                    l.liquidity_journal_id AS journal_id,
                    l.liquidity_type AS journal_type,
                    l.account_id,
                    l.company_id,
                    l.move_id,
                    move.name AS move_name,
                    l.date,
                    move.ref AS evrak_no,
                    l.name AS aciklama,
                    l.partner_id,
                    %(hareket_turu)s AS hareket_turu,
                    l.hesap_currency_id AS currency_id,
                    GREATEST(l.hesap_tutar, 0) AS giris,
                    GREATEST(-l.hesap_tutar, 0) AS cikis,
                    l.hesap_tutar AS tutar,
                    SUM(l.hesap_tutar) OVER (
                        PARTITION BY l.company_id, l.account_id ORDER BY l.date, l.move_id, l.id
                    ) AS bakiye,
                    l.company_currency_id,
                    l.balance AS tutar_tl
                FROM lines l
                JOIN account_move move ON move.id = l.move_id
                LEFT JOIN account_payment payment ON payment.id = move.origin_payment_id
            )
        """, table=SQL.identifier(self._table), hareket_turu=SQL("CASE %s END", self._hareket_turu_when_sql())))

    def _hareket_turu_when_sql(self):
        """Hareket türü CASE koşulları; alt modüller başa WHEN ekleyerek genişletir."""
        return SQL("""
            WHEN move.atlas_fis_turu IN ('tahsil', 'tediye', 'virman', 'acilis') THEN move.atlas_fis_turu
            WHEN payment.payment_type = 'inbound' THEN 'tahsilat'
            WHEN payment.payment_type = 'outbound' THEN 'odeme'
            WHEN move.statement_line_id IS NOT NULL THEN 'ekstre'
            ELSE 'mahsup'
        """)

    def action_open_move(self):
        self.ensure_one()
        return self.move_id._get_records_action()
