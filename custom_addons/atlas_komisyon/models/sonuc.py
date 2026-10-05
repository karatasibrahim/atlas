from odoo import fields, models


class AtlasKomisyonSonuc(models.Model):
    """Plan × temsilci/ekip × dönem komisyon sonucu (plan hesaplandıkça yeniden üretilir)."""
    _name = 'atlas.komisyon.sonuc'
    _description = 'Komisyon Sonucu'
    _order = 'donem_bas desc, plan_id, id'
    _rec_name = 'donem_adi'

    plan_id = fields.Many2one('atlas.komisyon.plan', string='Plan', required=True, ondelete='cascade', index=True)
    plan_tur = fields.Selection(related='plan_id.tur', string='Plan Türü')
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    user_id = fields.Many2one('res.users', string='Satış Temsilcisi', index=True)
    team_id = fields.Many2one('crm.team', string='Satış Ekibi', index=True)
    donem_bas = fields.Date(string='Dönem Başı', index=True)
    donem_bit = fields.Date(string='Dönem Sonu')
    donem_adi = fields.Char(string='Dönem')
    basari = fields.Monetary(string='Başarı', currency_field='currency_id', aggregator='sum')
    hedef = fields.Monetary(string='Hedef', currency_field='currency_id', aggregator='sum')
    gerceklesme = fields.Float(string='Gerçekleşme (%)', aggregator='avg', digits=(16, 1))
    komisyon = fields.Monetary(string='Komisyon', currency_field='currency_id', aggregator='sum')
    satir_ids = fields.One2many('atlas.komisyon.sonuc.satir', 'sonuc_id', string='Ayrıntı')

    def action_ayrinti(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.komisyon.sonuc.satir', 'name': self.env._('Komisyon Ayrıntısı'),
                'view_mode': 'list,pivot', 'domain': [('sonuc_id', '=', self.id)]}

    def action_yeniden_hesapla(self):
        self.plan_id._hesapla()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}


class AtlasKomisyonSonucSatir(models.Model):
    _name = 'atlas.komisyon.sonuc.satir'
    _description = 'Komisyon Sonucu Ayrıntısı'
    _order = 'tarih, id'

    sonuc_id = fields.Many2one('atlas.komisyon.sonuc', string='Sonuç', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one(related='sonuc_id.user_id', store=True)
    team_id = fields.Many2one(related='sonuc_id.team_id', store=True)
    kaynak = fields.Selection([('satis', 'Satış'), ('fatura', 'Fatura'), ('duzeltme', 'Düzeltme')], string='Kaynak')
    belge = fields.Char(string='Belge')
    res_model = fields.Char(string='Model')
    res_id = fields.Integer(string='Kayıt')
    tarih = fields.Date(string='Tarih')
    urun_id = fields.Many2one('product.product', string='Ürün')
    kural_id = fields.Many2one('atlas.komisyon.plan.basari', string='Kural', ondelete='set null')
    miktar = fields.Float(string='Miktar')
    currency_id = fields.Many2one(related='sonuc_id.currency_id')
    tutar = fields.Monetary(string='Tutar', currency_field='currency_id')
    oran = fields.Float(string='Oran', digits=(16, 4))
    katki = fields.Monetary(string='Katkı', currency_field='currency_id', aggregator='sum')

    def action_belge(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}
