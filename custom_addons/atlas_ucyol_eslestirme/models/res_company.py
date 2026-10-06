from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ucyol_fiyat_tolerans = fields.Float(string='Fiyat Toleransı (%)', default=0.0,
                                        help='Fatura birim fiyatı sipariş fiyatından bu orandan fazla saparsa istisna sayılır')
    ucyol_miktar_tolerans = fields.Float(string='Miktar Toleransı (%)', default=0.0,
                                         help='Faturalanan toplam miktar sipariş miktarını bu orandan fazla aşarsa istisna sayılır')
    ucyol_odeme_engeli = fields.Boolean(string='Ödenebilir Olmayan Faturaya Ödemeyi Engelle',
                                        help='Açıksa yalnız "Ödenebilir" ya da elle serbest bırakılmış tedarikçi faturalarına ödeme kaydedilir')
