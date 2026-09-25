from odoo import fields, models


class AtlasBanka(models.Model):
    """Türkiye banka listesi; IBAN'daki EFT kodundan banka adını bulmak için."""
    _name = 'atlas.banka'
    _description = 'Banka'
    _order = 'name'

    name = fields.Char(string='Banka', required=True)
    eft_kodu = fields.Char(string='EFT Kodu', size=5, required=True, index=True,
                           help='Türk IBAN numarasındaki 5 haneli banka kodu (TRkk BBBBB ...).')
    bic = fields.Char(string='BIC / SWIFT')
    active = fields.Boolean(default=True)

    _eft_kodu_unique = models.Constraint('UNIQUE(eft_kodu)', 'Bu EFT kodu başka bir bankada tanımlı.')
