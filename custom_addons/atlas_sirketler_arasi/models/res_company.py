from odoo import api, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    sa_fatura = fields.Boolean(string='Faturaları Senkronize Et',
                               help='Grup şirketinin bu şirkete kestiği fatura / iade onaylanınca burada karşılık belgesi oluşur')
    sa_fatura_durum = fields.Selection([('taslak', 'Taslak'), ('onayli', 'Onaylı')], string='Oluşan Faturalar', default='taslak')
    sa_satis_olustur = fields.Boolean(string='Satış Siparişi Oluştur',
                                      help='Grup şirketi bu şirketten satın alma siparişi onaylayınca burada satış siparişi oluşur')
    sa_satin_alma_olustur = fields.Boolean(string='Satın Alma Siparişi Oluştur',
                                           help='Grup şirketi bu şirkete satış siparişi onaylayınca burada satın alma siparişi oluşur')
    sa_otomatik_onay = fields.Boolean(string='Oluşan Siparişleri Onayla')
    sa_depo_id = fields.Many2one('stock.warehouse', string='Şirketler Arası Depo', domain="[('company_id', '=', id)]")
    sa_kullanici_id = fields.Many2one('res.users', string='Belgeleri Oluşturan', domain="[('share', '=', False)]",
                                      help='Boşsa yönetici (OdooBot) adına oluşturulur')

    @api.model
    def _sa_hedef(self, partner, kaynak_sirket):
        """Ortak bir grup şirketine mi kesildi? Ortağın ticari kişisine bağlı şirket (kaynak şirketin kendisi değil)."""
        if not partner:
            return self.browse()
        ticari = partner.commercial_partner_id
        hedef = self.sudo().search([('partner_id', '=', ticari.id)], limit=1)
        return hedef if hedef and hedef != kaynak_sirket else self.browse()

    def _sa_ortam(self):
        """Hedef şirkette belge oluşturma ortamı (seçilen kullanıcı ya da yönetici, yalnız o şirket)."""
        self.ensure_one()
        kullanici = self.sa_kullanici_id
        if kullanici and self not in kullanici.company_ids:
            raise UserError(self.env._('%(kullanici)s kullanıcısının %(sirket)s şirketine erişimi yok.', kullanici=kullanici.name, sirket=self.name))
        env = self.env(user=kullanici.id) if kullanici else self.env
        return env['res.company'].browse(self.id).sudo(not kullanici).with_context(
            allowed_company_ids=[self.id], default_company_id=self.id, atlas_sa_olusturuldu=True).with_company(self).env

    def _sa_depo(self, env):
        """Şirketler arası belgeler için depo: ayardaki, yoksa şirketin ilk deposu; hiç yoksa oluşturulur."""
        self.ensure_one()
        depo = self.sa_depo_id or env['stock.warehouse'].search([('company_id', '=', self.id)], limit=1)
        if not depo:
            kod = (''.join(c for c in (self.name or '').upper() if c.isalnum())[:5]) or f'SA{self.id}'
            depo = env['stock.warehouse'].sudo().create({'name': self.name, 'code': kod, 'company_id': self.id})
        return depo

    def _sa_vergiler(self, kaynak_vergiler, urun, tip):
        """Kaynak satırın vergilerinin hedef şirketteki karşılığı: önce ürünün vergileri, yoksa aynı oran ve türdeki vergi."""
        self.ensure_one()
        Vergi = self.env['account.tax'].sudo()
        if urun:
            urun_vergileri = (urun.supplier_taxes_id if tip == 'purchase' else urun.taxes_id).sudo().filtered(lambda v: v.company_id == self)
            if urun_vergileri:
                return urun_vergileri
        sonuc = Vergi
        for v in kaynak_vergiler:
            sonuc |= Vergi.search([('company_id', '=', self.id), ('type_tax_use', '=', tip), ('amount', '=', v.amount),
                                   ('amount_type', '=', v.amount_type), ('price_include', '=', v.price_include)], limit=1)
        return sonuc


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sa_fatura = fields.Boolean(related='company_id.sa_fatura', readonly=False)
    sa_fatura_durum = fields.Selection(related='company_id.sa_fatura_durum', readonly=False)
    sa_satis_olustur = fields.Boolean(related='company_id.sa_satis_olustur', readonly=False)
    sa_satin_alma_olustur = fields.Boolean(related='company_id.sa_satin_alma_olustur', readonly=False)
    sa_otomatik_onay = fields.Boolean(related='company_id.sa_otomatik_onay', readonly=False)
    sa_depo_id = fields.Many2one(related='company_id.sa_depo_id', readonly=False)
    sa_kullanici_id = fields.Many2one(related='company_id.sa_kullanici_id', readonly=False)
