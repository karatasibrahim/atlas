from markupsafe import Markup

from odoo import models

SYSTEM_FONT_STYLE = '<style>* { font-family: Arial, Helvetica, "DejaVu Sans", sans-serif !important; }</style>'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _prepare_wkhtmltopdf_html(self, html, report_model=False):
        """`atlas.report_system_font` açıksa PDF'lerde web yazı tipi yerine sistem yazı tipi kullanılır.

        macOS'ta (Rosetta ile çalışan) wkhtmltopdf, indirilen web yazı tiplerini (Lato) zaman zaman
        bozuk gömüyor; sistem yazı tipiyle çıktı kararlı. Linux sunucularda bu ayara gerek yoktur.
        """
        result = super()._prepare_wkhtmltopdf_html(html, report_model=report_model)
        if not result or not self.env['ir.config_parameter'].sudo().get_bool('atlas.report_system_font'):
            return result
        bodies, res_ids, header, footer, specific_paperformat_args = result

        def inject(content):
            if content and '</head>' in content:
                return Markup(str(content).replace('</head>', f'{SYSTEM_FONT_STYLE}</head>', 1))
            return content

        bodies = [{**body, 'body': inject(body['body'])} if isinstance(body, dict) else inject(body) for body in bodies]
        return bodies, res_ids, inject(header), inject(footer), specific_paperformat_args
