from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AtlasCariGrup(models.Model):
    _name = 'atlas.cari.grup'
    _description = 'Cari Grubu'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='Grup Kodu', size=2, required=True,
                       help='Cari kodunun orta bölümü: 120-GG-NNNN')
    name = fields.Char(string='Grup Adı', required=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('UNIQUE(code)', 'Bu grup kodu zaten kullanılıyor.')

    @api.constrains('code')
    def _check_code(self):
        for grup in self:
            if not (len(grup.code) == 2 and grup.code.isdigit()):
                raise ValidationError(self.env._('Grup kodu 2 haneli sayı olmalıdır (örn. 00, 01).'))

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for grup in self:
            grup.display_name = f'{grup.code} - {grup.name}'


class AtlasCariBolge(models.Model):
    _name = 'atlas.cari.bolge'
    _description = 'Cari Bölgesi'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='Bölge Kodu', required=True)
    name = fields.Char(string='Bölge Adı', required=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('UNIQUE(code)', 'Bu bölge kodu zaten kullanılıyor.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for bolge in self:
            bolge.display_name = f'{bolge.code} - {bolge.name}'


class AtlasCariOzelKod(models.Model):
    _name = 'atlas.cari.ozel.kod'
    _description = 'Cari Özel Kodu'
    _order = 'sira, code'
    _rec_names_search = ['code', 'name']

    sira = fields.Selection([('1', 'Özel Kod 1'), ('2', 'Özel Kod 2')], string='Özel Kod', required=True, default='1')
    code = fields.Char(string='Kod', required=True)
    name = fields.Char(string='Açıklama', required=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('UNIQUE(sira, code)', 'Bu özel kod zaten tanımlı.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for kod in self:
            kod.display_name = f'{kod.code} - {kod.name}'
