from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_accounting_date(self, invoice_date, has_tax, lock_dates=None):
        """Türkiye: alış faturası belge (fatura) tarihiyle kaydedilir.

        Odoo, geçmiş tarihli alış faturalarını numara sırası bozulmasın diye bugüne/ay sonuna taşır.
        KDV dönemi ve yevmiye tarihi fatura tarihine bağlı olduğundan, kilitli dönem yoksa fatura
        tarihi korunur. Kilitli dönem varsa Odoo'nun kuralı geçerlidir.
        """
        if self.company_id.account_fiscal_country_id.code == 'TR' and not self.is_sale_document(include_receipts=True):
            lock_dates = lock_dates or self._get_violated_lock_dates(invoice_date, has_tax)
            if not lock_dates:
                return invoice_date
        return super()._get_accounting_date(invoice_date, has_tax, lock_dates=lock_dates)
