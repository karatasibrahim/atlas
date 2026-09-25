from odoo import fields, models

# (şirket alanı, hesap kodu, hesap adı, mevcut değilse oluşturulsun mu)
CEK_ACCOUNTS = [
    ('atlas_cek_portfoy_account_id', '101000', 'ALINAN ÇEKLER', False),
    ('atlas_cek_tahsil_account_id', '101001', 'Tahsile Verilen Çekler', True),
    ('atlas_cek_teminat_account_id', '101002', 'Teminata Verilen Çekler', True),
    ('atlas_senet_portfoy_account_id', '121000', 'ALACAK SENETLERİ', False),
    ('atlas_senet_tahsil_account_id', '121001', 'Tahsile Verilen Senetler', True),
    ('atlas_senet_teminat_account_id', '121002', 'Teminata Verilen Senetler', True),
    ('atlas_firma_cek_account_id', '103000', 'VERİLEN ÇEKLER VE ÖDEME EMİRLERİ (-)', False),
    ('atlas_firma_senet_account_id', '321000', 'BORÇ SENETLERİ', False),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_cek_portfoy_account_id = fields.Many2one('account.account', string='Portföydeki Çekler')
    atlas_cek_tahsil_account_id = fields.Many2one('account.account', string='Tahsile Verilen Çekler')
    atlas_cek_teminat_account_id = fields.Many2one('account.account', string='Teminata Verilen Çekler')
    atlas_senet_portfoy_account_id = fields.Many2one('account.account', string='Portföydeki Senetler')
    atlas_senet_tahsil_account_id = fields.Many2one('account.account', string='Tahsile Verilen Senetler')
    atlas_senet_teminat_account_id = fields.Many2one('account.account', string='Teminata Verilen Senetler')
    atlas_firma_cek_account_id = fields.Many2one('account.account', string='Verilen Çekler')
    atlas_firma_senet_account_id = fields.Many2one('account.account', string='Borç Senetleri')

    def _atlas_setup_cek_accounts(self):
        """TDHP'deki çek/senet hesaplarını bağlar, tahsil/teminat alt hesaplarını açar."""
        for company in self:
            Account = self.env['account.account'].with_company(company).sudo()
            for field_name, code, name, create in CEK_ACCOUNTS:
                if company[field_name]:
                    continue
                account = Account.search([('code', '=', code), ('company_ids', 'in', company.root_id.id)], limit=1)
                if not account and create:
                    parent = Account.search([('code', '=', code[:3] + '000'), ('company_ids', 'in', company.root_id.id)], limit=1)
                    account = Account.create({
                        'code': code,
                        'name': name,
                        'account_type': parent.account_type or 'asset_current',
                        'company_ids': [fields.Command.set(company.root_id.ids)],
                    })
                company[field_name] = account

    def _atlas_cek_account(self, evrak_turu, durum):
        """Evrak türü ve durumuna göre bulunduğu hesap."""
        self.ensure_one()
        if evrak_turu == 'firma_cek':
            return self.atlas_firma_cek_account_id
        if evrak_turu == 'firma_senet':
            return self.atlas_firma_senet_account_id
        prefix = 'atlas_cek' if evrak_turu == 'musteri_cek' else 'atlas_senet'
        suffix = {'tahsilde': 'tahsil', 'teminatta': 'teminat'}.get(durum, 'portfoy')
        return self[f'{prefix}_{suffix}_account_id']


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_cek_portfoy_account_id = fields.Many2one(related='company_id.atlas_cek_portfoy_account_id', readonly=False)
    atlas_cek_tahsil_account_id = fields.Many2one(related='company_id.atlas_cek_tahsil_account_id', readonly=False)
    atlas_cek_teminat_account_id = fields.Many2one(related='company_id.atlas_cek_teminat_account_id', readonly=False)
    atlas_senet_portfoy_account_id = fields.Many2one(related='company_id.atlas_senet_portfoy_account_id', readonly=False)
    atlas_senet_tahsil_account_id = fields.Many2one(related='company_id.atlas_senet_tahsil_account_id', readonly=False)
    atlas_senet_teminat_account_id = fields.Many2one(related='company_id.atlas_senet_teminat_account_id', readonly=False)
    atlas_firma_cek_account_id = fields.Many2one(related='company_id.atlas_firma_cek_account_id', readonly=False)
    atlas_firma_senet_account_id = fields.Many2one(related='company_id.atlas_firma_senet_account_id', readonly=False)
