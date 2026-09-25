from . import models
from . import wizard


def _atlas_kasa_banka_post_init(env):
    env['account.journal'].search([('type', '=', 'cash')])._atlas_set_direct_cash_payments()
    for company in env['res.company'].search([('chart_template', '=', 'tr')]):
        env['atlas.seri']._atlas_create_virman_series(company)
        env['atlas.banka.kural']._atlas_create_default_rules(company)
