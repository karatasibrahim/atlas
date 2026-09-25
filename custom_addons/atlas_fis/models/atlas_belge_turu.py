from odoo import fields, models

# account.move.move_type -> belge türü kodu
MOVE_TYPE_BELGE = {
    'out_invoice': 'satis_fatura',
    'out_refund': 'satis_iade',
    'in_invoice': 'alis_fatura',
    'in_refund': 'alis_iade',
}

FIS_TURU_SELECTION = [
    ('mahsup', 'Mahsup'),
    ('tahsil', 'Tahsil'),
    ('tediye', 'Tediye'),
    ('acilis', 'Açılış'),
    ('kapanis', 'Kapanış'),
    ('dekont', 'Dekont'),
]


class AtlasBelgeTuru(models.Model):
    _name = 'atlas.belge.turu'
    _description = 'Belge Türü'
    _order = 'sequence, id'

    code = fields.Char(string='Kod', required=True, readonly=True)
    name = fields.Char(string='Belge Türü', required=True, translate=True)
    sequence = fields.Integer(default=10)

    _code_unique = models.Constraint('UNIQUE(code)', 'Belge türü kodu benzersiz olmalıdır.')
