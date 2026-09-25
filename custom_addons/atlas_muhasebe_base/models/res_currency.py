import logging
from datetime import datetime, timedelta

import requests
from lxml import etree

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TCMB_TODAY_URL = 'https://www.tcmb.gov.tr/kurlar/today.xml'
TCMB_DATE_URL = 'https://www.tcmb.gov.tr/kurlar/{d:%Y%m}/{d:%d%m%Y}.xml'
TCMB_TIMEOUT = 20

# company.atlas_tcmb_rate_type -> (TCMB XML etiketi, res.currency.rate alanı)
TCMB_RATE_TYPES = {
    'forex_buying': ('ForexBuying', 'atlas_forex_buying'),
    'forex_selling': ('ForexSelling', 'atlas_forex_selling'),
    'banknote_buying': ('BanknoteBuying', 'atlas_banknote_buying'),
    'banknote_selling': ('BanknoteSelling', 'atlas_banknote_selling'),
}


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _atlas_tcmb_parse(self, content):
        """TCMB bülten XML'ini ayrıştırır.

        :return: (bülten tarihi, {döviz kodu: {kur tipi: 1 birim dövizin TL karşılığı}})
        """
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(content, parser=parser)
        bulletin_date = datetime.strptime(root.get('Date'), '%m/%d/%Y').date()
        values = {}
        for node in root.iter('Currency'):
            unit = float(node.findtext('Unit') or 1)
            rates = {}
            for rate_type, (tag, _field) in TCMB_RATE_TYPES.items():
                text = (node.findtext(tag) or '').strip()
                if text:
                    rates[rate_type] = float(text) / unit
            if rates:
                values[node.get('CurrencyCode')] = rates
        return bulletin_date, values

    @api.model
    def _atlas_tcmb_fetch(self, date=None):
        """Belirtilen günün TCMB bültenini (verilmezse son bülteni) getirir.

        :return: bülten yayımlanmamışsa (tatil/hafta sonu) None, aksi halde _atlas_tcmb_parse sonucu
        """
        url = TCMB_DATE_URL.format(d=date) if date else TCMB_TODAY_URL
        try:
            response = requests.get(url, timeout=TCMB_TIMEOUT)
        except requests.RequestException as e:
            raise UserError(self.env._('TCMB sunucusuna bağlanılamadı: %s', e)) from e
        if date and response.status_code == 404:
            return None
        if response.status_code != 200:
            raise UserError(self.env._('TCMB kurları alınamadı (HTTP %s): %s', response.status_code, url))
        return self._atlas_tcmb_parse(response.content)

    @api.model
    def _atlas_tcmb_update_rates(self, companies, date=None):
        """TCMB kurlarını şirketlerin kur tablosuna yazar.

        Kur, bülten tarihine kaydedilir. Odoo kuru işlem tarihinden *önceki* en yakın
        kayıttan aldığı için D günü bülteni D+1 tarihli işlemlerde kullanılır
        (VUK uygulaması: bir önceki günün TCMB kuru).
        Manuel girilmiş kurların üzerine yazılmaz. Yalnızca aktif dövizler güncellenir.

        :param companies: ana (root) şirketler; kurlar ana şirket bazında tutulur
        :param date: bülten tarihi; verilmezse son yayımlanan bülten kullanılır
        :return: kullanılan bülten tarihi, o gün bülten yoksa None
        """
        result = self._atlas_tcmb_fetch(date)
        if not result:
            return None
        bulletin_date, values = result
        values['TRY'] = dict.fromkeys(TCMB_RATE_TYPES, 1.0)

        Rate = self.env['res.currency.rate']
        currencies = self.search([])
        for company in companies.filtered(lambda c: not c.parent_id):
            rate_type = company.atlas_tcmb_rate_type
            company_value = values.get(company.currency_id.name, {}).get(rate_type)
            if not company_value:
                _logger.warning("TCMB bülteninde şirket para birimi bulunamadı: %s", company.currency_id.name)
                continue
            for currency in currencies - company.currency_id:
                currency_values = values.get(currency.name, {})
                if not currency_values.get(rate_type):
                    continue
                vals = {
                    'rate': company_value / currency_values[rate_type],
                    'atlas_source': 'tcmb',
                    'atlas_bulletin_date': bulletin_date,
                }
                for key, (_tag, field_name) in TCMB_RATE_TYPES.items():
                    vals[field_name] = currency_values.get(key, 0.0)

                existing = Rate.search([
                    ('currency_id', '=', currency.id),
                    ('company_id', '=', company.id),
                    ('name', '=', bulletin_date),
                ], limit=1)
                if not existing:
                    Rate.create({**vals, 'currency_id': currency.id, 'company_id': company.id, 'name': bulletin_date})
                elif existing.atlas_source == 'tcmb':
                    existing.write(vals)
        return bulletin_date

    @api.model
    def _atlas_cron_tcmb_update(self):
        companies = self.env['res.company'].search([('parent_id', '=', False), ('atlas_tcmb_auto', '=', True)])
        if not companies:
            return
        try:
            bulletin_date = self._atlas_tcmb_update_rates(companies)
            _logger.info("TCMB kurları güncellendi (bülten: %s)", bulletin_date)
        except UserError as e:
            _logger.error("TCMB kur güncellemesi başarısız: %s", e)

    @api.model
    def _atlas_tcmb_update_range(self, companies, date_from, date_to):
        """Tarih aralığındaki tüm TCMB bültenlerini çeker. Bülten olmayan günler atlanır."""
        dates = []
        day = date_from
        while day <= date_to:
            if self._atlas_tcmb_update_rates(companies, day):
                dates.append(day)
            day += timedelta(days=1)
        return dates
