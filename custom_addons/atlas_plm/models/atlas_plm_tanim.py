from odoo import api, fields, models

ONAY_TIPLERI = [
    ('zorunlu', 'Zorunlu onay'),
    ('istege_bagli', 'İsteğe bağlı onay'),
    ('yorum', 'Yalnızca yorum'),
]


class AtlasPlmTip(models.Model):
    _name = 'atlas.plm.tip'
    _description = 'ECO Tipi'
    _order = 'sequence, id'

    name = fields.Char(string='Tip', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Renk')
    eco_ids = fields.One2many('atlas.plm.eco', 'tip_id', string='Değişiklikler')
    eco_acik_sayisi = fields.Integer(compute='_compute_sayilar', string='Açık Değişiklik')
    eco_onay_bekleyen = fields.Integer(compute='_compute_sayilar', string='Onayımı Bekleyen')

    def _compute_sayilar(self):
        Eco = self.env['atlas.plm.eco']
        acik = dict(Eco._read_group([('tip_id', 'in', self.ids), ('durum', 'in', ('taslak', 'islemde'))], ['tip_id'], ['__count']))
        bekleyen = dict(Eco._read_group([('tip_id', 'in', self.ids), ('onayimi_bekliyor', '=', True)], ['tip_id'], ['__count']))
        for tip in self:
            tip.eco_acik_sayisi = acik.get(tip, 0)
            tip.eco_onay_bekleyen = bekleyen.get(tip, 0)

    def action_ecolar(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('atlas_plm.action_atlas_plm_eco')
        action['domain'] = [('tip_id', '=', self.id)]
        action['context'] = {'default_tip_id': self.id}
        return action

    def action_yeni_eco(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.plm.eco', 'view_mode': 'form',
                'context': {'default_tip_id': self.id}, 'target': 'current'}


class AtlasPlmAsama(models.Model):
    _name = 'atlas.plm.asama'
    _description = 'ECO Aşaması'
    _order = 'sequence, id'

    name = fields.Char(string='Aşama', required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Kanban\'da Katla')
    son_asama = fields.Boolean(string='Uygulama Aşaması',
                               help='Değişiklik bu aşamaya geldiğinde reçete revizyonu uygulanır (yürürlük tarihi ileriyse o tarihte).')
    tip_ids = fields.Many2many('atlas.plm.tip', string='Tipler', help='Boşsa tüm tiplerde kullanılır.')
    onay_sablon_ids = fields.One2many('atlas.plm.onay.sablon', 'asama_id', string='Onaylar')


class AtlasPlmEtiket(models.Model):
    _name = 'atlas.plm.etiket'
    _description = 'ECO Etiketi'

    name = fields.Char(string='Etiket', required=True)
    color = fields.Integer(string='Renk')


class AtlasPlmOnaySablon(models.Model):
    """Aşamadan çıkmadan önce alınması gereken onay."""
    _name = 'atlas.plm.onay.sablon'
    _description = 'ECO Onay Şablonu'
    _order = 'sequence, id'

    name = fields.Char(string='Onay', required=True)
    sequence = fields.Integer(default=10)
    asama_id = fields.Many2one('atlas.plm.asama', string='Aşama', required=True, ondelete='cascade')
    onay_tipi = fields.Selection(ONAY_TIPLERI, string='Onay Tipi', required=True, default='zorunlu')
    user_ids = fields.Many2many('res.users', string='Onaylayacaklar',
                                help='Boşsa PLM yöneticileri onay verebilir.')

    def _onaylayabilir(self, user):
        self.ensure_one()
        if self.user_ids:
            return user in self.user_ids
        return user.has_group('atlas_plm.group_plm_manager')

    def _bildirilecekler(self):
        self.ensure_one()
        return self.user_ids or self.env.ref('atlas_plm.group_plm_manager').user_ids.filtered(lambda u: not u.share and u.active and u.id != self.env.ref('base.user_root').id)
