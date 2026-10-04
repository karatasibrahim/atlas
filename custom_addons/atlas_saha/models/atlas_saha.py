from urllib.parse import quote_plus

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class ProjectProject(models.Model):
    _inherit = 'project.project'

    atlas_saha = fields.Boolean(string='Saha Servisi', help='Görevler sahada yapılan servis işleridir: malzeme, kontrol listesi, imza, faturalama.')
    atlas_hizmet_urun_id = fields.Many2one('product.product', string='İşçilik Ürünü', domain=[('type', '=', 'service')],
                                           help='Harcanan süre bu hizmet ürünüyle faturalanır.')
    atlas_faturala = fields.Boolean(string='Tamamlanınca Faturala', default=True)
    atlas_imza_zorunlu = fields.Boolean(string='Müşteri İmzası Zorunlu', default=True)
    atlas_kontrol_sablon_ids = fields.One2many('atlas.saha.kontrol.sablon', 'project_id', string='Kontrol Listesi Şablonu')


class AtlasSahaKontrolSablon(models.Model):
    _name = 'atlas.saha.kontrol.sablon'
    _description = 'Saha Servisi Kontrol Listesi Şablonu'
    _order = 'sequence, id'

    project_id = fields.Many2one('project.project', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Kontrol', required=True)
    zorunlu = fields.Boolean(string='Zorunlu', default=True)


class AtlasSahaKontrol(models.Model):
    _name = 'atlas.saha.kontrol'
    _description = 'Saha Servisi Kontrol Maddesi'
    _order = 'sequence, id'

    task_id = fields.Many2one('project.task', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Kontrol', required=True)
    zorunlu = fields.Boolean(string='Zorunlu')
    yapildi = fields.Boolean(string='Yapıldı')
    aciklama = fields.Char(string='Not')


class AtlasSahaMalzeme(models.Model):
    _name = 'atlas.saha.malzeme'
    _description = 'Saha Servisi Kullanılan Malzeme'
    _order = 'id'

    task_id = fields.Many2one('project.task', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Ürün', required=True, domain=[('sale_ok', '=', True)])
    miktar = fields.Float(string='Miktar', default=1.0, digits='Product Unit', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='Birim')
    fiyat = fields.Float(string='Birim Fiyat', digits='Product Price', compute='_compute_fiyat', store=True, readonly=False)
    currency_id = fields.Many2one(related='task_id.company_id.currency_id')
    tutar = fields.Monetary(string='Tutar', compute='_compute_tutar', currency_field='currency_id')

    @api.depends('product_id')
    def _compute_fiyat(self):
        for satir in self:
            satir.fiyat = satir.product_id.lst_price

    @api.depends('miktar', 'fiyat')
    def _compute_tutar(self):
        for satir in self:
            satir.tutar = satir.miktar * satir.fiyat


class ProjectTask(models.Model):
    _inherit = 'project.task'

    atlas_saha = fields.Boolean(related='project_id.atlas_saha', store=True, string='Saha Görevi')
    atlas_malzeme_ids = fields.One2many('atlas.saha.malzeme', 'task_id', string='Malzemeler')
    atlas_kontrol_ids = fields.One2many('atlas.saha.kontrol', 'task_id', string='Kontrol Listesi')
    atlas_is_raporu = fields.Html(string='İş Raporu')
    atlas_imza = fields.Binary(string='Müşteri İmzası', copy=False, attachment=True)
    atlas_imzalayan = fields.Char(string='İmzalayan', copy=False)
    atlas_imza_tarihi = fields.Datetime(string='İmza Tarihi', copy=False, readonly=True)
    atlas_tamamlanma = fields.Datetime(string='Tamamlanma', copy=False, readonly=True)
    atlas_siparis_id = fields.Many2one('sale.order', string='Servis Siparişi', copy=False, readonly=True)
    atlas_fatura_durumu = fields.Selection(related='atlas_siparis_id.invoice_status', string='Fatura Durumu')
    atlas_adres = fields.Char(string='Adres', compute='_compute_atlas_adres')
    atlas_kontrol_ozet = fields.Char(string='Kontrol', compute='_compute_atlas_kontrol_ozet')

    @api.depends('partner_id')
    def _compute_atlas_adres(self):
        for task in self:
            adres = task.partner_id.contact_address or ''
            task.atlas_adres = ', '.join(s.strip() for s in adres.splitlines() if s.strip() and s.strip() != task.partner_id.name)

    @api.depends('atlas_kontrol_ids.yapildi')
    def _compute_atlas_kontrol_ozet(self):
        for task in self:
            toplam = len(task.atlas_kontrol_ids)
            task.atlas_kontrol_ozet = f'{len(task.atlas_kontrol_ids.filtered("yapildi"))}/{toplam}' if toplam else ''

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task in tasks.filtered(lambda t: t.atlas_saha and not t.atlas_kontrol_ids and t.project_id.atlas_kontrol_sablon_ids):
            task.atlas_kontrol_ids = [Command.create({'name': s.name, 'zorunlu': s.zorunlu, 'sequence': s.sequence})
                                      for s in task.project_id.atlas_kontrol_sablon_ids]
        return tasks

    def write(self, vals):
        if vals.get('atlas_imza'):
            vals.setdefault('atlas_imza_tarihi', fields.Datetime.now())
        return super().write(vals)

    def action_atlas_yol_tarifi(self):
        self.ensure_one()
        p = self.partner_id
        if p.partner_latitude or p.partner_longitude:
            hedef = f'{p.partner_latitude},{p.partner_longitude}'
        elif self.atlas_adres:
            hedef = quote_plus(self.atlas_adres)
        else:
            raise UserError(self.env._('Müşterinin adresi yok.'))
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': f'https://www.google.com/maps/dir/?api=1&destination={hedef}'}

    def _atlas_tamamlama_kontrol(self):
        self.ensure_one()
        if not self.atlas_saha:
            raise UserError(self.env._('%s bir saha servisi görevi değil.', self.name))
        if self.atlas_tamamlanma:
            raise UserError(self.env._('%s zaten tamamlandı.', self.name))
        eksik = self.atlas_kontrol_ids.filtered(lambda k: k.zorunlu and not k.yapildi)
        if eksik:
            raise UserError(self.env._('Tamamlanmamış zorunlu kontroller: %s', ', '.join(eksik.mapped('name'))))
        if self.project_id.atlas_imza_zorunlu and not self.atlas_imza:
            raise UserError(self.env._('Müşteri imzası alınmadan görev tamamlanamaz.'))
        if self.project_id.atlas_faturala:
            if not self.partner_id:
                raise UserError(self.env._('Faturalamak için müşteri seçin.'))
            if self.effective_hours and not self.project_id.atlas_hizmet_urun_id:
                raise UserError(self.env._('%s projesinde işçilik ürünü tanımlı değil.', self.project_id.name))

    def _atlas_siparis_olustur(self):
        """İşçilik (zaman kayıtları) ve malzemelerden sipariş; malzeme teslimatı doğrulanır, fatura taslağı oluşur."""
        self.ensure_one()
        iscilik = self.project_id.atlas_hizmet_urun_id if self.effective_hours else self.env['product.product']
        if not iscilik and not self.atlas_malzeme_ids:
            return self.env['sale.order']
        sirket = self.company_id or self.env.company
        # Teknisyenin satış/stok yetkisi olmayabilir: sipariş, çıkış ve fatura sistem adına oluşturulur
        siparis = self.env['sale.order'].sudo().create({
            'partner_id': self.partner_id.id, 'company_id': sirket.id,
            'origin': self.name, 'client_order_ref': self.name,
            'user_id': (self.project_id.user_id or self.env.user).id,
        })
        satirlar = []
        if iscilik:
            satirlar.append(Command.create({'product_id': iscilik.id, 'product_uom_qty': round(self.effective_hours, 2),
                                            'name': f'{iscilik.display_name} — {self.name}'}))
        for m in self.atlas_malzeme_ids:
            # malzeme fiyatı şirket para biriminde girilir; sipariş (fiyat listesi) para birimine çevrilir
            fiyat = sirket.currency_id._convert(m.fiyat, siparis.currency_id, sirket, siparis.date_order.date())
            satirlar.append(Command.create({'product_id': m.product_id.id, 'product_uom_qty': m.miktar, 'price_unit': fiyat}))
        siparis.order_line = satirlar
        siparis.action_confirm()
        for teslimat in siparis.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
            for hareket in teslimat.move_ids:
                hareket.quantity = hareket.product_uom_qty
            teslimat.with_context(skip_backorder=True, picking_ids_not_to_backorder=teslimat.ids).button_validate()
        if siparis.invoice_status == 'to invoice':
            siparis._create_invoices()
        return siparis.sudo(False)

    def action_atlas_tamamla(self):
        for task in self:
            task._atlas_tamamlama_kontrol()
            # Çalışan sayacı varsa önce süreyi yaz
            sayac = self.env['atlas.zaman.sayac'].search([('task_id', '=', task.id), ('user_id', '=', self.env.uid)], limit=1)
            if sayac:
                sayac.atlas_durdur()
            siparis = task._atlas_siparis_olustur() if task.project_id.atlas_faturala else self.env['sale.order']
            task.write({'atlas_tamamlanma': fields.Datetime.now(), 'atlas_siparis_id': siparis.id or False, 'state': '1_done'})
            rapor, _ = self.env['ir.actions.report']._render_qweb_pdf('atlas_saha.action_report_servis', task.ids)
            task.message_post(body=self.env._('Servis tamamlandı.'),
                              attachments=[(f'Servis Raporu - {task.name}.pdf', rapor)])
        return True

    def action_atlas_rapor_gonder(self):
        self.ensure_one()
        sablon = self.env.ref('atlas_saha.mail_template_servis_raporu')
        return {
            'type': 'ir.actions.act_window', 'res_model': 'mail.compose.message', 'view_mode': 'form', 'target': 'new',
            'context': {'default_model': 'project.task', 'default_res_ids': self.ids, 'default_template_id': sablon.id,
                        'default_composition_mode': 'comment', 'force_email': True},
        }

    def action_atlas_siparis(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'res_id': self.atlas_siparis_id.id, 'view_mode': 'form'}
