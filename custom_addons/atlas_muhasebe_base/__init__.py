from . import models
from . import wizard


def _atlas_post_init(env):
    """Türkiye şirketlerinde Tek Düzen Hesap Planı'nı (l10n_tr 'tr' şablonu) yükler.

    Şablon, registry tamamen yüklendikten sonra yüklenir (account modülünün
    kendi otomatik yükleme mekanizmasıyla aynı yol).
    """
    turkey = env.ref('base.tr')
    companies = env['res.company'].search([('parent_id', '=', False)]).filtered(
        lambda c: c.country_id in (turkey, env['res.country'])
        and c.chart_template != 'tr'
        and not c._existing_accounting()
    )
    if companies:
        company_ids = companies.ids
        companies.country_id = turkey

        def load_tr_chart(env):
            for company in env['res.company'].browse(company_ids):
                env['account.chart.template'].try_loading('tr', company)

        env.registry._auto_install_template = load_tr_chart

    env['res.currency'].with_context(active_test=False).search(
        [('name', 'in', ('USD', 'EUR', 'GBP'))]
    ).active = True
