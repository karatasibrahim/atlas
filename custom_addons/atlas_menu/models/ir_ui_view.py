import logging

from odoo import models
from odoo.tools import sql

_logger = logging.getLogger(__name__)


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _register_hook(self):
        """website modülü ir_ui_view.visibility kolonunu NOT NULL yapar ama veritabanı varsayılanı koymaz.
        website'a bağlı olmayan bir modül güncellenirken (website henüz yüklenmeden) yeni görünüm eklenirse
        kayıt "null value in column visibility" hatasıyla düşer. Kolona veritabanı varsayılanı verilir."""
        super()._register_hook()
        cr = self.env.cr
        if sql.column_exists(cr, 'ir_ui_view', 'visibility'):
            cr.execute("""SELECT column_default FROM information_schema.columns
                           WHERE table_name = 'ir_ui_view' AND column_name = 'visibility'""")
            if not (cr.fetchone() or [None])[0]:
                cr.execute("ALTER TABLE ir_ui_view ALTER COLUMN visibility SET DEFAULT 'public'")
                _logger.info('ir_ui_view.visibility kolonuna varsayılan değer verildi')
