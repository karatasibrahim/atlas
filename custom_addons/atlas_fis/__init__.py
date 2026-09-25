from . import models


def _atlas_fis_post_init(env):
    for company in env['res.company'].search([('chart_template', '=', 'tr')]):
        env['atlas.seri']._atlas_create_default_series(company)
