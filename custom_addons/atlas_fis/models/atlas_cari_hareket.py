from odoo import fields, models
from odoo.tools import SQL


class AtlasCariHareket(models.Model):
    _inherit = 'atlas.cari.hareket'

    hareket_turu = fields.Selection(selection_add=[
        ('fis_tahsil', 'Tahsil Fişi'),
        ('fis_tediye', 'Tediye Fişi'),
        ('fis_dekont', 'Dekont'),
        ('fis_acilis', 'Açılış Fişi'),
        ('fis_kapanis', 'Kapanış Fişi'),
    ])

    def _hareket_turu_when_sql(self):
        return SQL("""
            WHEN move.atlas_fis_turu IN ('tahsil', 'tediye', 'dekont', 'acilis', 'kapanis')
                THEN 'fis_' || move.atlas_fis_turu
            %s
        """, super()._hareket_turu_when_sql())
