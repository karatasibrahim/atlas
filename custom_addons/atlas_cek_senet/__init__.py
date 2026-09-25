from . import models


def _atlas_cek_senet_post_init(env):
    for company in env['res.company'].search([('chart_template', '=', 'tr')]):
        company._atlas_setup_cek_accounts()
        env['atlas.seri']._atlas_create_cek_series(company)
