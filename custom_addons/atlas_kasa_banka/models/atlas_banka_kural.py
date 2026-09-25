from odoo import api, fields, models

from .atlas_banka_ekstre_sablon import normalize_text

# Kurulumda oluşturulan örnek kurallar: (anahtar kelime, yön, hesap kodu)
DEFAULT_RULES = [
    ('MASRAF', 'cikis', '653000'),
    ('KOMİSYON', 'cikis', '653000'),
    ('ÜCRET', 'cikis', '653000'),
    ('BSMV', 'cikis', '653000'),
    ('FAİZ', 'giris', '642000'),
]


class AtlasBankaKural(models.Model):
    """Banka ekstre satırı açıklamasında anahtar kelime geçerse önerilecek karşı hesap/cari."""
    _name = 'atlas.banka.kural'
    _description = 'Banka Eşleştirme Kuralı'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string='Anahtar Kelime', required=True,
                       help='Açıklamada geçen metin (büyük/küçük harf ve Türkçe karakter duyarsız).')
    yon = fields.Selection([('her_ikisi', 'Giriş ve Çıkış'), ('giris', 'Giriş'), ('cikis', 'Çıkış')],
                           string='Yön', default='her_ikisi', required=True)
    journal_id = fields.Many2one('account.journal', string='Banka', domain=[('type', '=', 'bank')],
                                 help='Boşsa tüm banka hesaplarında geçerli.')
    account_id = fields.Many2one('account.account', string='Karşı Hesap', required=True, check_company=True)
    partner_id = fields.Many2one('res.partner', string='Cari')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)

    def _match(self, st_line, text):
        self.ensure_one()
        if self.journal_id and self.journal_id != st_line.journal_id:
            return False
        if self.yon == 'giris' and st_line.amount < 0 or self.yon == 'cikis' and st_line.amount > 0:
            return False
        return normalize_text(self.name) in text

    @api.model
    def _atlas_create_default_rules(self, company):
        if self.with_context(active_test=False).search_count([('company_id', '=', company.id)]):
            return self
        Account = self.env['account.account'].with_company(company)
        vals_list = []
        for sequence, (keyword, yon, code) in enumerate(DEFAULT_RULES, start=1):
            account = Account.search([('code', '=', code), ('company_ids', 'in', company.id)], limit=1)
            if account:
                vals_list.append({'name': keyword, 'yon': yon, 'account_id': account.id,
                                  'company_id': company.id, 'sequence': sequence * 10})
        return self.create(vals_list)
