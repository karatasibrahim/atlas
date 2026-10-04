from odoo import fields, models


class AtlasKaliteEkip(models.Model):
    _name = 'atlas.kalite.ekip'
    _description = 'Kalite Ekibi'
    _order = 'sequence, id'

    name = fields.Char(string='Ekip', required=True)
    sequence = fields.Integer(default=10)
    user_ids = fields.Many2many('res.users', string='Üyeler')
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class AtlasKaliteEtiket(models.Model):
    _name = 'atlas.kalite.etiket'
    _description = 'Kalite Etiketi'

    name = fields.Char(string='Etiket', required=True)
    color = fields.Integer(string='Renk')


class AtlasKaliteNeden(models.Model):
    """Kök neden (6M: malzeme, makine, metot, insan, ölçüm, çevre)."""
    _name = 'atlas.kalite.neden'
    _description = 'Kök Neden'
    _order = 'name'

    name = fields.Char(string='Kök Neden', required=True)
    active = fields.Boolean(default=True)


class AtlasKaliteUyariAsama(models.Model):
    _name = 'atlas.kalite.uyari.asama'
    _description = 'Uygunsuzluk Aşaması'
    _order = 'sequence, id'

    name = fields.Char(string='Aşama', required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Kanban\'da Katla')
    kapali = fields.Boolean(string='Kapanış Aşaması', help='Bu aşamadaki uygunsuzluklar çözülmüş sayılır.')
