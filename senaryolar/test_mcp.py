import json
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
M = env['atlas.mcp']
ICP = env['ir.config_parameter'].sudo()
ICP.set_bool('atlas_mcp.etkin', True)
ICP.set_bool('atlas_mcp.yazma', False)
cagri = lambda yontem, params=None, kimlik=1: M.isle({'jsonrpc': '2.0', 'id': kimlik, 'method': yontem, 'params': params or {}})
arac = lambda ad, **a: cagri('tools/call', {'name': ad, 'arguments': a})['result']
ini = cagri('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test'}})['result']
ok(ini['protocolVersion'] and ini['capabilities']['tools'] is not None and ini['serverInfo']['name'] == 'Atlas ERP', "initialize")
ok(M.isle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) is None, "bildirim yanıtsız (HTTP 202)")
araclar = [t['name'] for t in cagri('tools/list')['result']['tools']]
ok({'modelleri_listele', 'kayit_ara', 'grupla'} <= set(araclar) and 'kayit_olustur' not in araclar, "araç listesi (yazma araçları kapalı)")
ml = arac('modelleri_listele', arama='partner')
ok(not ml['isError'] and any(x['model'] == 'res.partner' for x in json.loads(ml['content'][0]['text'])), "modelleri listele (arama)")
P = env['res.partner']
P.create([{'name': 'MCP Test A', 'city': 'İstanbul'}, {'name': 'MCP Test B', 'city': 'İstanbul'}, {'name': 'MCP Test C', 'city': 'Ankara'}])
ara = arac('kayit_ara', model='res.partner', domain=[['name', 'like', 'MCP Test']], alanlar=['name', 'city'], siralama='name')
kayitlar = ara['structuredContent']['sonuc']
ok([k['name'] for k in kayitlar] == ['MCP Test A', 'MCP Test B', 'MCP Test C'] and kayitlar[0]['city'] == 'İstanbul', "kayıt ara")
ok(arac('kayit_say', model='res.partner', domain=[['name', 'like', 'MCP Test']])['structuredContent']['sonuc'] == 3, "kayıt say")
gr = arac('grupla', model='res.partner', domain=[['name', 'like', 'MCP Test']], grupla=['city'], toplamlar=['__count'])['structuredContent']['sonuc']
ok({g['city']: g['__count'] for g in gr} == {'İstanbul': 2, 'Ankara': 1}, f"grupla: {gr}")
ok(arac('kayit_ara', model='res.users.apikeys')['isError'] and arac('kayit_ara', model='yok.model')['isError'], "yasaklı ve olmayan model hata")
ok(arac('kayit_olustur', model='res.partner', degerler={'name': 'X'})['isError'], "yazma kapalıyken oluşturma reddedilir")
ICP.set_bool('atlas_mcp.yazma', True)
yeni = arac('kayit_olustur', model='res.partner', degerler={'name': 'MCP Yeni'})
ok(not yeni['isError'] and P.browse(yeni['structuredContent']['sonuc']['id']).name == 'MCP Yeni', "yazma açıkken oluşturma")
# Yetki: portal benzeri kısıtlı kullanıcı muhasebe kaydı okuyamaz
kisitli = env['res.users'].create({'name': 'MCP Kısıtlı', 'login': 'mcp_kisitli', 'group_ids': [(6, 0, env.ref('base.group_user').ids)]})
red = M.with_user(kisitli)._arac_cagir('kayit_ara', {'model': 'account.move'})
ok(red['isError'], "kullanıcı yetkisi dışındaki model okunamaz")
ok(env['atlas.mcp.gunluk'].search_count([('arac', '=', 'kayit_ara')]) >= 3, "çağrılar günlüğe yazıldı")
ok(cagri('yok/yontem')['error']['code'] == -32601 and M.isle({'foo': 1})['error']['code'] == -32600, "JSON-RPC hata kodları")
env.cr.rollback(); print("(geri alındı)")
