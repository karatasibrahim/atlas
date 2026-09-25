"""Dönem sonu işlemlerinde ortak yardımcılar."""
from odoo.exceptions import UserError
from odoo.fields import Command

# 7/A gider grubu: (gider öneki, yansıtma hesabı öneki, aktarılacak hesap öneki)
# Üretim giderleri (710/720/730) yarı mamule (151), faaliyet giderleri gelir tablosuna aktarılır.
YANSITMA_7A = [
    ('710', '711', '151'),
    ('720', '721', '151'),
    ('730', '731', '151'),
    ('750', '751', '630'),
    ('760', '761', '631'),
    ('770', '771', '632'),
    ('780', '781', '660'),
]


def account_by_code(env, company, code):
    """Tam kod veya 3 haneli ana hesap kodu ile hesap (ana hesap için ilk alt hesap, ör. 646 -> 646000)."""
    Account = env['account.account'].with_company(company)
    base = [('company_ids', 'in', company.root_id.id)]
    account = Account.search(base + [('code', '=', code)], limit=1)
    if not account and len(code) == 3:
        account = Account.search(base + [('code', '=like', f'{code}%')], order='code', limit=1)
    if not account:
        raise UserError(env._('%s hesabı hesap planında bulunamadı.', code))
    return account


def account_balances(env, company, domain, groupby=('account_id',)):
    """[(grup değerleri..., bakiye, döviz tutarı)] onaylı hareketlerden."""
    return env['account.move.line']._read_group(
        [('company_id', '=', company.id), ('parent_state', '=', 'posted')] + domain,
        list(groupby), ['balance:sum', 'amount_currency:sum'])


def create_entry(env, company, date, ref, lines, fis_turu='mahsup', post=True):
    """Satır sözlüklerinden dengeli yevmiye fişi oluşturur; boş satırları atlar."""
    currency = company.currency_id
    lines = [line for line in lines
             if not currency.is_zero(line.get('balance', 0.0)) or line.get('amount_currency')]
    if not lines:
        return env['account.move']
    move = env['account.move'].with_company(company).create({
        'move_type': 'entry',
        'atlas_fis_turu': fis_turu,
        'date': date,
        'ref': ref,
        'company_id': company.id,
        'line_ids': [Command.create(line) for line in lines],
    })
    if post:
        move.action_post()
    return move
