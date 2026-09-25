from odoo import fields, models
from odoo.tools import SQL


class AtlasCariHareket(models.Model):
    _inherit = 'atlas.cari.hareket'

    hareket_turu = fields.Selection(selection_add=[('cek_senet', 'Çek / Senet')])

    def _hareket_turu_when_sql(self):
        return SQL("WHEN move.atlas_fis_turu = 'cek_senet' THEN 'cek_senet' %s", super()._hareket_turu_when_sql())


class AtlasKasaBankaHareket(models.Model):
    _inherit = 'atlas.kasa.banka.hareket'

    hareket_turu = fields.Selection(selection_add=[('cek_senet', 'Çek / Senet')])

    def _hareket_turu_when_sql(self):
        return SQL("WHEN move.atlas_fis_turu = 'cek_senet' THEN 'cek_senet' %s", super()._hareket_turu_when_sql())
