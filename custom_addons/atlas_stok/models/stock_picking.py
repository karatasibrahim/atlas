from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    atlas_seri_id = fields.Many2one(
        'atlas.seri', string='İrsaliye Serisi', index='btree_not_null', copy=False, check_company=True,
        compute='_compute_atlas_seri_id', store=True, readonly=False,
        domain="[('company_id', '=', company_id), ('belge_turu_ids.code', '=', 'irsaliye')]")
    atlas_irsaliye_no = fields.Char(string='İrsaliye No', copy=False, readonly=True, index='btree_not_null',
                                    help='Sevkiyat onaylanınca seriden verilir (GİB e-İrsaliye biçimi).')
    atlas_tedarikci_irsaliye_no = fields.Char(string='Tedarikçi İrsaliye No', copy=False,
                                              help='Mal kabulde tedarikçinin irsaliye numarası.')
    atlas_fiili_sevk_tarihi = fields.Datetime(string='Fiili Sevk Tarihi', copy=False)
    atlas_arac_plaka = fields.Char(string='Araç Plakası', copy=False)
    atlas_dorse_plaka = fields.Char(string='Dorse Plakası', copy=False)
    atlas_sofor_adi = fields.Char(string='Şoför Adı Soyadı', copy=False)
    atlas_sofor_tckn = fields.Char(string='Şoför TCKN', size=11, copy=False)

    _atlas_irsaliye_unique = models.UniqueIndex(
        '(company_id, atlas_irsaliye_no) WHERE atlas_irsaliye_no IS NOT NULL',
        'Bu irsaliye numarası zaten kullanılmış.',
    )

    @api.depends('picking_type_code', 'company_id')
    def _compute_atlas_seri_id(self):
        Seri = self.env['atlas.seri']
        for picking in self:
            if picking.atlas_irsaliye_no or picking.atlas_seri_id or picking.picking_type_code != 'outgoing':
                continue
            picking.atlas_seri_id = Seri._get_default('irsaliye', picking.company_id)

    def _action_done(self):
        res = super()._action_done()
        for picking in self.filtered(lambda p: p.picking_type_code == 'outgoing' and p.atlas_seri_id and not p.atlas_irsaliye_no):
            date = fields.Datetime.context_timestamp(picking, picking.date_done or fields.Datetime.now()).date()
            picking.write({
                'atlas_irsaliye_no': picking.atlas_seri_id._next_number(date),
                'atlas_fiili_sevk_tarihi': picking.atlas_fiili_sevk_tarihi or picking.date_done,
            })
        return res
