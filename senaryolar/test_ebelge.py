from datetime import date
from odoo.exceptions import UserError
from odoo.fields import Command
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; P = env['res.partner']; M = env['account.move']; tr = env.ref('base.tr')
def fatura(partner, mt='out_invoice', fp=None, vergi=None):
    return M.create({'move_type': mt, 'partner_id': partner.id, 'invoice_date': date(2026, 9, 1), 'fiscal_position_id': fp.id if fp else False,
                     'invoice_line_ids': [Command.create({'name': 'Mal', 'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.set(vergi.ids)] if vergi else False})]})
mukellef = P.create({'name': 'EB Mükellef A.Ş.', 'is_company': True, 'atlas_cari_tipi': 'alici', 'vat': '1234567890', 'country_id': tr.id,
                     'atlas_efatura_mukellef': True, 'atlas_efatura_etiket': 'urn:mail:defaultpk@a.com.tr'})
bireysel = P.create({'name': 'EB Bireysel', 'is_company': False, 'atlas_cari_tipi': 'alici'})
c.atlas_ebelge_aktif = False
f0 = fatura(mukellef)
ok(f0.atlas_ebelge_tipi == 'kagit' and f0.atlas_seri_id.on_ek == 'ATL', "e-Belge kapalıyken kâğıt fatura, ATL serisi")
c.atlas_ebelge_aktif = True; c.atlas_efatura_senaryo = 'TICARIFATURA'
f1 = fatura(mukellef)
ok(f1.atlas_ebelge_tipi == 'efatura' and f1.atlas_ebelge_senaryo == 'TICARIFATURA' and f1.atlas_fatura_tipi == 'SATIS' and f1.atlas_seri_id.ebelge_tipi == 'efatura',
   f"mükellef cari: e-Fatura / TICARIFATURA / SATIS, seri {f1.atlas_seri_id.on_ek}")
f1.action_post()
ok(len(f1.atlas_ettn or '') == 36 and f1.name.startswith('ATL') and len(f1.name) == 16, f"onay: {f1.name}, ETTN {f1.atlas_ettn[:8]}...")
f2 = fatura(bireysel)
ok(f2.atlas_ebelge_tipi == 'earsiv' and f2.atlas_ebelge_senaryo == 'EARSIVFATURA' and f2.atlas_seri_id.on_ek == 'ARS', "mükellef olmayan: e-Arşiv, ARS serisi")
f2.action_post()
ok(f2.name == 'ARS2026000000001', f"e-Arşiv numarası: {f2.name}")
mukellef.atlas_efatura_senaryo = 'TEMELFATURA'
ok(fatura(mukellef).atlas_ebelge_senaryo == 'TEMELFATURA', "cari bazında temel senaryo")
vkn_siz = P.create({'name': 'EB VKN siz', 'is_company': True, 'atlas_cari_tipi': 'alici', 'atlas_efatura_mukellef': True})
f3 = fatura(vkn_siz)
try:
    with env.cr.savepoint(): f3.action_post(); hata = None
except UserError as e: hata = str(e)
ok(hata and 'VKN' in hata, "VKN'siz e-Fatura onaylanmadı")
fp_ihr = env['account.fiscal.position'].search([('company_id', '=', c.id), ('atlas_gib_kod_id.tip', '=', 'ihracat')], limit=1)
yabanci = P.create({'name': 'EB Foreign GmbH', 'is_company': True, 'atlas_cari_tipi': 'alici', 'country_id': env.ref('base.de').id, 'vat': 'DE123456788'})
f4 = fatura(yabanci, fp=fp_ihr)
ok(fp_ihr and f4.atlas_ebelge_tipi == 'efatura' and f4.atlas_ebelge_senaryo == 'IHRACAT' and f4.atlas_fatura_tipi == 'ISTISNA', "ihracat: e-Fatura / IHRACAT / ISTISNA")
fp_ik = env['account.fiscal.position'].search([('company_id', '=', c.id), ('atlas_gib_kod_id.tip', '=', 'ihrac_kayitli')], limit=1)
ok(fatura(mukellef, fp=fp_ik).atlas_fatura_tipi == 'IHRACKAYITLI', "ihraç kayıtlı fatura tipi")
kdv = env['account.chart.template'].with_company(c).ref('tr_s_20')
tev = kdv.copy({'name': 'KDV %20 Tevkifat test', 'atlas_gib_kod_id': env.ref('atlas_muhasebe_base.gib_601').id})
ok(fatura(mukellef, vergi=tev).atlas_fatura_tipi == 'TEVKIFAT', "tevkifat kodlu vergi → TEVKIFAT")
iade = fatura(mukellef, mt='in_refund')
ok(iade.atlas_fatura_tipi == 'IADE' and iade.atlas_ebelge_senaryo == 'TEMELFATURA' and iade.atlas_ebelge_tipi == 'efatura', "alış iadesi: IADE / TEMELFATURA")
alis = fatura(mukellef, mt='in_invoice')
ok(not alis.atlas_ebelge_tipi and not alis.atlas_fatura_tipi, "alış faturasında e-Belge alanları boş")
f5 = fatura(mukellef); f5.atlas_ebelge_tipi = 'earsiv'
ok(f5.atlas_seri_id.on_ek == 'ARS', "elle e-Arşiv seçilince seri ARS'ye döndü")
env.cr.rollback(); print("(geri alındı)")
