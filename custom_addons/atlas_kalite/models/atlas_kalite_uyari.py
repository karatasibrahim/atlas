from odoo import api, fields, models

ONCELIKLER = [('0', 'Normal'), ('1', 'Düşük'), ('2', 'Yüksek'), ('3', 'Acil')]


class AtlasKaliteUyari(models.Model):
    """Uygunsuzluk / kalite uyarısı ve DÖF (düzeltici - önleyici faaliyet)."""
    _name = 'atlas.kalite.uyari'
    _description = 'Uygunsuzluk (DÖF)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'oncelik desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Uygunsuzluk No', required=True, copy=False, readonly=True, default='/', index='trigram')
    baslik = fields.Char(string='Başlık', required=True, tracking=True)
    aciklama = fields.Html(string='Açıklama')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    asama_id = fields.Many2one('atlas.kalite.uyari.asama', string='Aşama', tracking=True, index=True, copy=False,
                               default=lambda self: self.env['atlas.kalite.uyari.asama'].search([], limit=1),
                               group_expand='_read_group_asama_ids')
    kapali = fields.Boolean(related='asama_id.kapali', store=True, string='Çözüldü')
    oncelik = fields.Selection(ONCELIKLER, string='Öncelik', default='0', tracking=True)
    etiket_ids = fields.Many2many('atlas.kalite.etiket', string='Etiketler')
    ekip_id = fields.Many2one('atlas.kalite.ekip', string='Kalite Ekibi', tracking=True)
    user_id = fields.Many2one('res.users', string='Sorumlu', tracking=True, default=lambda self: self.env.user)
    color = fields.Integer(string='Renk')

    # Kaynak
    kontrol_id = fields.Many2one('atlas.kalite.kontrol', string='Kalite Kontrolü', index=True, ondelete='set null')
    nokta_id = fields.Many2one('atlas.kalite.nokta', string='Kontrol Noktası')
    product_id = fields.Many2one('product.product', string='Ürün', index=True)
    lot_id = fields.Many2one('stock.lot', string='Lot / Seri')
    lot_name = fields.Char(string='Lot / Seri No')
    picking_id = fields.Many2one('stock.picking', string='Transfer', index=True)
    production_id = fields.Many2one('mrp.production', string='Üretim Emri', index=True)
    workorder_id = fields.Many2one('mrp.workorder', string='İş Emri')
    workcenter_id = fields.Many2one('mrp.workcenter', string='İş Merkezi')
    partner_id = fields.Many2one('res.partner', string='Tedarikçi / Müşteri', index=True)
    foto = fields.Image(string='Fotoğraf', max_width=1920, max_height=1920, attachment=True)

    # Analiz ve faaliyetler
    neden_id = fields.Many2one('atlas.kalite.neden', string='Kök Neden', tracking=True)
    kok_neden_analizi = fields.Html(string='Kök Neden Analizi')
    duzeltici_faaliyet = fields.Html(string='Düzeltici Faaliyet')
    onleyici_faaliyet = fields.Html(string='Önleyici Faaliyet')
    termin = fields.Date(string='Termin', tracking=True)
    kapanis_tarihi = fields.Datetime(string='Kapanış Tarihi', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('atlas.kalite.uyari') or '/'
        uyarilar = super().create(vals_list)
        for uyari in uyarilar.filtered(lambda u: u.ekip_id.user_ids):
            uyari.message_subscribe(partner_ids=uyari.ekip_id.user_ids.partner_id.ids)
        return uyarilar

    def write(self, vals):
        if 'asama_id' in vals:
            asama = self.env['atlas.kalite.uyari.asama'].browse(vals['asama_id'])
            vals['kapanis_tarihi'] = fields.Datetime.now() if asama.kapali else False
        return super().write(vals)

    @api.model
    def _read_group_asama_ids(self, stages, domain):
        return stages.search([])

    @api.depends('name', 'baslik')
    def _compute_display_name(self):
        for uyari in self:
            uyari.display_name = f'{uyari.name} {uyari.baslik or ""}'.strip()
