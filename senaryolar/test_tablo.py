import json
from odoo.exceptions import AccessError
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
T = env['atlas.tablo']
tid = T.atlas_tablo_yeni('TB Bütçe')
t = T.browse(tid)
ac = t.atlas_tablo_ac()
ok(ac['ad'] == 'TB Bütçe' and 'sheets' in ac['veri'] and not ac['salt_okunur'], "yeni tablo boş o-spreadsheet verisiyle açılıyor")
veri = dict(ac['veri'])
veri['sheets'][0]['cells'] = {'A1': '100', 'A2': '=A1*2'}
t.atlas_tablo_kaydet(json.dumps(veri), 'TB Bütçe 2026')
ok(t.name == 'TB Bütçe 2026' and json.loads(t.spreadsheet_data)['sheets'][0]['cells']['A2'] == '=A1*2', "kaydet: içerik ve ad")
eylem = t.action_ac()
ok(eylem['tag'] == 'atlas_tablo.duzenle' and eylem['params']['tablo_id'] == t.id, "tablo düzenleyici eylemi")
# Paylaşım: düzenleyici listesi doluysa yalnız sahibi ve listedekiler yazar
diger = env['res.users'].create({'name': 'TB Kullanıcı', 'login': 'tb_kullanici', 'group_ids': [(6, 0, env.ref('base.group_user').ids)]})
t.paylasilan_ids = env.ref('base.user_admin')
t.user_id = env.ref('base.user_admin')
ok(t.with_user(diger).atlas_tablo_ac()['salt_okunur'], "paylaşılmayan kullanıcı için salt okunur")
try:
    t.with_user(diger).atlas_tablo_kaydet('{}'); yazdi = True
except AccessError:
    yazdi = False
ok(not yazdi, "paylaşılmayan kullanıcı kaydedemez")
yeni = T.action_yeni()
ok(yeni['tag'] == 'atlas_tablo.duzenle' and T.browse(yeni['params']['tablo_id']).name, "Yeni Hesap Tablosu menüsü")
paket = env['ir.qweb']._get_asset_bundle('spreadsheet.o_spreadsheet')
ok(any('atlas_tablo/static/src/bundle/editor.js' in (getattr(f, 'url', '') or '') for f in paket.javascripts),
   "düzenleyici o-spreadsheet paketinde (ihtiyaç anında yüklenir)")
env.cr.rollback(); print("(geri alındı)")
