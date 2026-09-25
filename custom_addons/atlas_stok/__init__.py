from . import models
from . import wizard


def _atlas_stok_post_init(env):
    for company in env['res.company'].search([('chart_template', '=', 'tr')]):
        company._atlas_setup_stock_accounting()
        env['atlas.seri']._atlas_create_irsaliye_series(company)
    env['res.config.settings'].create({})._atlas_enable_stock_features()
