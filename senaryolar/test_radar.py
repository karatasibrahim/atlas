import json
from datetime import date

from odoo.exceptions import UserError
from odoo.addons.atlas_radar.services import ayristirici, metin, siniflandirici
from odoo.addons.atlas_radar.services.guvenlik import GuvenlikHatasi, alan_adlari, url_dogrula
from odoo.addons.atlas_radar.services.tarayici import EN_FAZLA_BOYUT, TaramaHatasi, Tarayici

ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
GENEL_IP = lambda host, port: {'93.184.216.34'}


class SahteYanit:
    def __init__(self, durum=200, govde=b'', tur='text/html; charset=utf-8', konum=None):
        self.status_code = durum
        self.govde = govde if isinstance(govde, bytes) else govde.encode('utf-8')
        self.headers = {'Content-Type': tur}
        if konum:
            self.headers['Location'] = konum

    def iter_content(self, boyut):
        for i in range(0, len(self.govde), boyut):
            yield self.govde[i:i + boyut]

    def close(self):
        pass


class SahteOturum:
    """URL → yanıt (ya da yanıt listesi). İstekleri kaydeder."""
    def __init__(self, yollar):
        self.yollar = yollar
        self.istekler = []

    def request(self, metot, url, **kw):
        self.istekler.append((metot, url, kw.get('data'), kw.get('headers', {}).get('User-Agent')))
        y = self.yollar.get(url)
        if isinstance(y, list):
            y = y.pop(0) if len(y) > 1 else y[0]
        return y or SahteYanit(404, 'yok')


def tarayici(kaynak, yollar, **kw):
    oturum = SahteOturum(yollar)
    return Tarayici(alan_adlari(kaynak.izinli_alanlar), bekleme=0, oturum=oturum, cozumleyici=GENEL_IP, uyku=lambda s: None, **kw), oturum


env = env(context=dict(env.context, tz='Europe/Istanbul'))
Kaynak = env['atlas.radar.kaynak']
Degisiklik = env['atlas.radar.degisiklik']
Denetim = env['atlas.radar.denetim']

# --- Kurulum verisi
tum = Kaynak.with_context(active_test=False).search([])
ebelge = env.ref('atlas_radar.kaynak_ebelge')
ok(len(tum) >= 7 and not ebelge.active and 'robots' in (ebelge.notlar or ''), "7 kaynak kuruldu; e-Belge portalı robots.txt nedeniyle pasif")
ok(env['atlas.radar.kural'].search_count([]) >= 16 and env['atlas.radar.modul'].search_count([]) >= 11, "kurallar ve ERP modülleri kuruldu")
menu = env.ref('atlas_radar.menu_radar_root')
ok(menu.group_ids == env.ref('base.group_system'), "Radar menüsü yalnız sistem yöneticisine açık")
erisim = env['ir.access'].search([('model_id.model', 'like', 'atlas.radar.%')])
ok(erisim and all(a.group_id == env.ref('base.group_system') for a in erisim), "tüm Radar modellerine yalnız yönetici erişir")
ok(env['atlas.radar.ayar']._ayar('sorumlu') == env.ref('base.user_admin') and env['atlas.radar.ayar']._ayar('proje'), "varsayılan sorumlu ve görev projesi")

# --- Metin yardımcıları ve sınıflandırıcı
ok(metin.tarih_bul('5 Ekim 2026 Gayrimenkul') == date(2026, 10, 5) and metin.tarih_bul('02/10/2026 tarihli') == date(2026, 10, 2)
   and metin.url_tarih('/eskiler/2026/10/20261005-1.htm') == date(2026, 10, 5), "tarih ayıklama (yazılı ay, sayısal, URL)")
ok(metin.yururluk_bul('Bu tebliğ 01.01.2027 tarihinden itibaren uygulanır.') == date(2027, 1, 1)
   and metin.yururluk_bul('1 Şubat 2027 tarihinde yürürlüğe girer') == date(2027, 2, 1), "yürürlük tarihi ifadeleri")
ok(metin.ozet('a  b\n\n c ') == metin.ozet('a b\nc') and metin.ozet('a') != metin.ozet('b'), "içerik özeti boşluklara duyarsız, içeriğe duyarlı")
kurallar = env['atlas.radar.kural']._motor_kurallari()
s = siniflandirici.siniflandir('E-FATURALARIN düzenlenmesine ilişkin duyuru', '', kurallar)
ok(s and s['kategori_id'] == env.ref('atlas_radar.kat_ebelge').id and env.ref('atlas_radar.mod_ebelge').id in s['modul_ids']
   and s['guven'] >= 60, f"Türkçe ek ve büyük harf: 'E-FATURALARIN' e-Belge kuralına uydu (güven {s and s['guven']})")
s2 = siniflandirici.siniflandir('UBL-TR Şematron dosyaları güncellendi', 'e-Fatura teknik kılavuz', kurallar)
ok(s2 and s2['onem'] == 'kritik' and s2['kirici'] and s2['gelistirme'], "şema değişikliği: kritik, kırıcı, geliştirme gerekli")
ok(siniflandirici.siniflandir('Beykoz Üniversitesi Lisansüstü Yönetmeliği', '', kurallar) is None, "ilgisiz yönetmelik eşleşmedi")
s3 = siniflandirici.siniflandir('Taksi Mali Cihaz Teknik Kılavuzu (Sürüm 2.0) yayımlanmıştır', '', kurallar)
ok(not s3 or s3['onem'] != 'kritik', "birlikte geçmeli: e-belge bağlamı olmayan 'teknik kılavuz' kritik sayılmadı")
ok(siniflandirici.siniflandir('Ankara Üniversitesi Yönetmeliği', 'ders kesintisi, planlı bakım ve ssl güncelleme', kurallar) is None,
   "yalnız başlıkta ara: metindeki 'planlı bakım' sistem kuralını tetiklemedi")
ok(siniflandirici.siniflandir('Kamuoyu Duyurusu (Veri İhlali Bildirimi) – X A.Ş.', 'kişisel veri', kurallar) is None,
   "hariç kelime: veri ihlali duyurusu KVKK kuralına uymadı")

# --- Ayrıştırıcılar
html = """<html><body><nav><a href="/kurumsal">Kurumsal Bilgiler ve Tarihçe</a></nav>
<div class="news__box"><a href="/Icerik/9024/x">İlgili Kişilerin Başvurularına Verilecek Cevap</a><span>01.10.2026</span></div>
<div class="news__box"><a href="/Icerik/9023/y#ust">KDV Oranlarında Değişiklik Yapılmasına Dair Karar</a><span>30.09.2026</span></div>
<div class="news__box"><a href="javascript:void(0)">Javascript bağlantısı uzun başlık</a></div></body></html>"""
og = ayristirici.html_liste(html, 'https://www.ornek.gov.tr/Duyurular', '//div[contains(@class, "news__box")]//a')
ok(len(og) == 2 and og[0]['url'] == 'https://www.ornek.gov.tr/Icerik/9024/x' and og[1]['url'].endswith('/Icerik/9023/y')
   and og[0]['tarih'] == date(2026, 10, 1), "HTML liste: seçici, göreli adres, # temizliği, üst öğeden tarih")
rss = """<?xml version="1.0"?><rss><channel><item><title>e-Arşiv Fatura Duyurusu</title><link>https://ornek.gov.tr/a</link>
<guid>A1</guid><pubDate>Mon, 05 Oct 2026 09:00:00 +0300</pubDate><description>&lt;p&gt;Metin&lt;/p&gt;</description></item></channel></rss>"""
og = ayristirici.rss(rss, 'https://ornek.gov.tr/rss')
ok(len(og) == 1 and og[0]['kimlik'] == 'A1' and og[0]['tarih'] == date(2026, 10, 5) and og[0]['icerik'] == 'Metin', "RSS ayrıştırma")
xxe = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&x;</title><guid>1</guid></item></channel></rss>'
og = ayristirici.rss(xxe, 'https://ornek.gov.tr/rss')
ok(not og or 'root:' not in og[0]['baslik'], "RSS: harici varlık (XXE) çözülmüyor")

# --- Güvenlik (SSRF / izinli alan)
izin = {'ornek.gov.tr'}
hatalar = []
for url, coz in [('ftp://ornek.gov.tr/x', GENEL_IP), ('https://kotu.com/x', GENEL_IP), ('https://10.0.0.1/x', GENEL_IP),
                 ('https://ic.ornek.gov.tr/x', lambda h, p: {'10.1.2.3'}), ('https://ornek.gov.tr/x', lambda h, p: {'127.0.0.1'}),
                 ('https://ornek.gov.tr/x', lambda h, p: {'::ffff:192.168.1.5'}), ('https://u:p@ornek.gov.tr/x', GENEL_IP)]:
    try:
        url_dogrula(url, izin, coz)
    except GuvenlikHatasi:
        hatalar.append(url)
ok(len(hatalar) == 7, "SSRF: şema, izinsiz alan, IP adresi, özel/loopback/IPv4-mapped IP, URL içi kimlik reddedildi")
ok(url_dogrula('https://www.ornek.gov.tr/x', izin, GENEL_IP).hostname == 'www.ornek.gov.tr', "izinli alt alan adı geçer")
try:
    with env.cr.savepoint():
        Kaynak.create({'name': 'X', 'kurum': 'X', 'url': 'https://kotu.com/', 'izinli_alanlar': 'ornek.gov.tr'})
    ok(False, "izin dışı kaynak adresi reddedilmeli")
except Exception:
    ok(True, "kaynak adresi izinli alan listesinde olmalı (kısıt)")

# --- Kaynak: JSON API, temel tarama, yeni ve güncellenen öğe
k = Kaynak.create({
    'name': 'Test GİB', 'kurum': 'Test İdaresi', 'url': 'https://api.ornek.gov.tr/duyuru', 'izinli_alanlar': 'ornek.gov.tr',
    'tur': 'json_api', 'http_metot': 'POST', 'istek_govdesi': '{"type": 1}', 'json_liste_yolu': 'sonuc.liste',
    'json_tarih': 'tarih', 'json_icerik': 'aciklama', 'link_sablonu': 'https://www.ornek.gov.tr/duyuru/{slug}',
})
def json_govde(*kayitlar):
    return json.dumps({'sonuc': {'liste': list(kayitlar)}})
d1 = {'id': 1, 'slug': '1-ilk', 'title': 'Vergi rehberi yayımlandı', 'tarih': '2026-09-01T10:00:00', 'aciklama': '<p>Rehber</p>'}
d2 = {'id': 2, 'slug': '2-mali', 'title': 'Mali tatil duyurusu', 'tarih': '2026-09-02T10:00:00', 'aciklama': 'Mali tatil'}
robots = SahteYanit(200, 'User-agent: *\nAllow: /\n', 'text/plain')
t, oturum = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots, 'https://api.ornek.gov.tr/duyuru': SahteYanit(200, json_govde(d1, d2), 'application/json')})
sonuc = k._tara(t)
ok(not sonuc and len(k.belge_ids) == 2 and set(k.belge_ids.mapped('durum')) == {'temel'} and k.ilk_tarama_tamam and k.saglik == 'iyi',
   "ilk tarama temel alındı: 2 belge, değişiklik açılmadı, kaynak sağlıklı")
istek = [i for i in oturum.istekler if i[1].endswith('/duyuru')][0]
ok(istek[0] == 'POST' and istek[2] == b'{"type": 1}' and istek[3].startswith('AtlasRadar/') and istek[3].isascii(),
   "POST gövdesi ve ASCII User-Agent gönderildi")
ok(k.belge_ids.filtered(lambda b: b.dis_kimlik == '1').url == 'https://www.ornek.gov.tr/duyuru/1-ilk', "bağlantı şablonundan adres")

d3 = {'id': 3, 'slug': '3-efatura', 'title': 'e-Fatura uygulamasında yeni düzenleme',
      'tarih': '2026-10-01T09:00:00', 'aciklama': 'e-Fatura ve e-Arşiv düzenlemesi 01.01.2027 tarihinden itibaren uygulanacaktır.'}
d1b = dict(d1, aciklama='<p>Rehber güncellendi: KDV tevkifat oranları değişti.</p>')
t, _ = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots, 'https://api.ornek.gov.tr/duyuru': SahteYanit(200, json_govde(d1b, d2, d3), 'application/json')})
sonuc = k._tara(t)
yeni = sonuc.filtered(lambda d: d.tur == 'yeni')
guncel = sonuc.filtered(lambda d: d.tur == 'guncelleme')
ok(len(sonuc) == 2 and len(yeni) == 1 and len(guncel) == 1, "ikinci tarama: 1 yeni yayın, 1 içerik güncellemesi")
ok(yeni.kategori_id == env.ref('atlas_radar.kat_ebelge') and yeni.onem == 'yuksek' and yeni.siniflandirma == 'kural'
   and yeni.yururluk_tarihi == date(2027, 1, 1) and yeni.yayim_tarihi == date(2026, 10, 1),
   f"yeni: e-Belge, yüksek, yürürlük 01.01.2027 ({yeni.yururluk_tarihi})")
ok(set(yeni.modul_ids.mapped('teknik_ad')) >= {'atlas_ebelge', 'atlas_mysoft'} and len(yeni.etki_ids) == len(yeni.modul_ids),
   "etkilenen modüller için etki satırları açıldı")
ok(yeni.activity_ids and env.ref('base.user_admin') in yeni.activity_ids.mapped('user_id'), "yüksek önem: sorumluya aktivite")
belge1 = guncel.belge_id
ok(belge1.surum == 2 and belge1.onceki_ozet and '+' in (guncel.fark or '') and 'tevkifat' in guncel.fark
   and guncel.kategori_id == env.ref('atlas_radar.kat_kdv'), "güncelleme: sürüm 2, önceki özet, fark, KDV kuralı")
t, _ = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots, 'https://api.ornek.gov.tr/duyuru': SahteYanit(200, json_govde(d1b, d2, d3), 'application/json')})
ok(not k._tara(t), "aynı içerik tekrar tarandığında değişiklik yok")
d4 = {'id': 4, 'slug': '4', 'title': '10995 Sayılı Karar Uyarınca Uygulanacak ÖTV Tutarları (12.09.2026)', 'tarih': '2026-09-12', 'aciklama': 'Eylül'}
d5 = {'id': 5, 'slug': '5', 'title': '10995 Sayılı Karar Uyarınca Uygulanacak ÖTV Tutarları (13.09.2026)', 'tarih': '2026-09-13', 'aciklama': 'Eylül 13'}
t, _ = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots, 'https://api.ornek.gov.tr/duyuru': SahteYanit(200, json_govde(d1b, d2, d3, d4, d5), 'application/json')})
otv = k._tara(t)
ok(len(otv) == 2 and not otv.filtered(lambda d: d.durum == 'mukerrer'), "aynı kaynakta benzer başlıklı ayrı duyurular mükerrer sayılmadı")

# --- Mükerrer: başka kaynakta aynı başlık
k2 = Kaynak.create({'name': 'Test RG', 'kurum': 'Test Gazete', 'url': 'https://gazete.ornek.gov.tr/', 'izinli_alanlar': 'gazete.ornek.gov.tr',
                    'tur': 'html_liste', 'link_deseni': r'/eskiler/\d+', 'sadece_eslesenler': True, 'detay_getir': True,
                    'ilk_tarama_tamam': True})
sayfa = """<html><body><a href="/eskiler/1">–– Beykoz Üniversitesi Lisansüstü Eğitim Yönetmeliği</a>
<a href="/eskiler/2">e-Fatura uygulamasında yeni düzenleme</a>
<a href="/eskiler/3">Asgari Ücret Tespit Komisyonu Kararı</a></body></html>"""
detay = '<html><body><nav>Menü</nav><main>2027 yılı asgari ücret tutarı belirlenmiştir. 1 Ocak 2027 tarihinden itibaren geçerlidir.</main></body></html>'
t, oturum = tarayici(k2, {'https://gazete.ornek.gov.tr/robots.txt': SahteYanit(404), 'https://gazete.ornek.gov.tr/': SahteYanit(200, sayfa),
                         'https://gazete.ornek.gov.tr/eskiler/1': SahteYanit(200, '<main>Üniversite yönetmeliği</main>'),
                         'https://gazete.ornek.gov.tr/eskiler/2': SahteYanit(200, '<main>e-Fatura düzenlemesi</main>'),
                         'https://gazete.ornek.gov.tr/eskiler/3': SahteYanit(200, detay)})
sonuc = k2._tara(t)
ilgisiz = k2.belge_ids.filtered(lambda b: 'Beykoz' in b.name)
ok(ilgisiz.durum == 'ilgisiz' and not ilgisiz.degisiklik_ids and ilgisiz.name.startswith('Beykoz'),
   "kurala uymayan Resmî Gazete öğesi değişiklik olmadı (başlıktaki –– temizlendi)")
asgari = sonuc.filtered(lambda d: 'Asgari' in d.name)
ok(asgari.onem == 'kritik' and asgari.yururluk_tarihi == date(2027, 1, 1) and 'atlas_bordro' in asgari.modul_ids.mapped('teknik_ad')
   and 'asgari ücret tutarı' in (asgari.icerik or ''), "detay sayfası okundu: asgari ücret → bordro, kritik, yürürlük 1 Ocak 2027")
ok('Menü' not in (asgari.icerik or ''), "detay metninde menü/nav atıldı")
muk = sonuc.filtered(lambda d: 'e-Fatura' in d.name)
ok(muk.durum == 'mukerrer' and muk.mukerrer_id == yeni and not muk.activity_ids, "başka kaynaktaki aynı duyuru mükerrer işaretlendi, bildirim yok")

# --- robots.txt, yönlendirme, hatalar, sınırlar
k3 = Kaynak.create({'name': 'Test Robots', 'kurum': 'X', 'url': 'https://yasak.ornek.gov.tr/duyuru', 'izinli_alanlar': 'yasak.ornek.gov.tr'})
t, oturum = tarayici(k3, {'https://yasak.ornek.gov.tr/robots.txt': SahteYanit(200, 'User-agent: *\nDisallow: /\n', 'text/plain'),
                         'https://yasak.ornek.gov.tr/duyuru': SahteYanit(200, '<a href="/a">Gizli duyuru başlığı uzun</a>')})
k3._tara(t)
ok(k3.robots_durumu == 'engelli' and k3.saglik == 'robots' and not any(i[1].endswith('/duyuru') for i in oturum.istekler),
   "robots.txt Disallow: sayfa istenmedi, kaynak 'robots engeli'")
t, oturum = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots,
                         'https://api.ornek.gov.tr/duyuru': SahteYanit(302, '', konum='https://kotu.com/ic')})
k._tara(t)
ok('izinli listede değil' in (k.son_hata or '') and k.ardisik_hata == 1 and k.saglik == 'uyari' and not any('kotu.com' in i[1] for i in oturum.istekler),
   "izin dışı alana yönlendirme takip edilmedi (SSRF)")
uykular = []
oturum = SahteOturum({'https://api.ornek.gov.tr/duyuru': SahteYanit(503, 'bakım')})
t = Tarayici({'ornek.gov.tr'}, bekleme=0, oturum=oturum, cozumleyici=GENEL_IP, uyku=uykular.append, robots=False)
try:
    t.getir('https://api.ornek.gov.tr/duyuru'); tekrar = False
except TaramaHatasi as e:
    tekrar = '503' in str(e)
ok(tekrar and len(oturum.istekler) == 3 and uykular == [2, 4], "HTTP 503: 3 deneme, üstel bekleme (2 s, 4 s)")
oturum = SahteOturum({'https://hiz.ornek.gov.tr/a': SahteYanit(200, 'x'), 'https://hiz.ornek.gov.tr/b': SahteYanit(200, 'y')})
uykular = []
t = Tarayici({'ornek.gov.tr'}, bekleme=5, oturum=oturum, cozumleyici=GENEL_IP, uyku=uykular.append, robots=False)
t.getir('https://hiz.ornek.gov.tr/a'); t.getir('https://hiz.ornek.gov.tr/b')
ok(len(uykular) == 1 and 4 < uykular[0] <= 5, f"hız sınırı: aynı alana ikinci istekten önce bekleme ({uykular})")
oturum = SahteOturum({'https://api.ornek.gov.tr/buyuk': SahteYanit(200, b'0' * (EN_FAZLA_BOYUT + 10))})
t = Tarayici({'ornek.gov.tr'}, bekleme=0, oturum=oturum, cozumleyici=GENEL_IP, robots=False)
try:
    t.getir('https://api.ornek.gov.tr/buyuk'); buyuk = False
except TaramaHatasi as e:
    buyuk = 'boyut' in str(e)
ok(buyuk, "5 MB yanıt boyutu sınırı")
for _ in range(2):
    t, _o = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots, 'https://api.ornek.gov.tr/duyuru': SahteYanit(200, '{"bozuk"', 'application/json')})
    k._tara(t)
ok(k.ardisik_hata == 3 and k.saglik == 'hata' and 'JSON' in k.son_hata
   and k.activity_ids.filtered(lambda a: 'taranamadı' in (a.summary or '')), "3 ardışık hata: kaynak hatalı, sorumluya aktivite")
t, _o = tarayici(k, {'https://api.ornek.gov.tr/robots.txt': robots, 'https://api.ornek.gov.tr/duyuru': SahteYanit(200, json_govde(), 'application/json')})
k._tara(t)
ok(k.ardisik_hata == 4 and 'öğe bulunamadı' in k.son_hata, "boş liste hata sayılır (sayfa yapısı değişmiş olabilir)")

# --- İnceleme akışı ve görevler
yeni.action_incele()
ok(yeni.durum == 'inceleniyor' and yeni.inceleyen_id == env.user, "incelemeye alındı")
yeni.action_onayla()
proje = env['atlas.radar.ayar']._ayar('proje')
ok(yeni.durum == 'onaylandi' and len(yeni.task_ids) == len(yeni.etki_ids) and set(yeni.task_ids.mapped('project_id')) == {proje}
   and all(e.task_id for e in yeni.etki_ids) and yeni.task_ids[0].date_deadline.date() == date(2027, 1, 1),
   f"onay: her etki için görev açıldı ({len(yeni.task_ids)}), son tarih = yürürlük")
try:
    with env.cr.savepoint():
        yeni.action_uygulandi(); erken = True
except UserError:
    erken = False
ok(not erken, "görevler kapanmadan 'uygulandı' yapılamaz")
yeni.task_ids.write({'state': '1_done'})
ok(all(e.durum == 'tamam' for e in yeni.etki_ids), "görev kapanınca etki tamamlandı")
yeni.action_uygulandi()
ok(yeni.durum == 'uygulandi', "değişiklik uygulandı")
try:
    with env.cr.savepoint():
        yeni.unlink(); silindi = True
except UserError:
    silindi = False
ok(not silindi, "uygulanmış değişiklik silinemez")
guncel.inceleme_notu = 'Rehber, ERP etkisi yok'
guncel.action_reddet()
ok(guncel.durum == 'reddedildi' and all(e.durum == 'ilgisiz' for e in guncel.etki_ids), "reddet: etkiler 'etkilemiyor'")
manuel = k2.belge_ids.filtered(lambda b: 'Beykoz' in b.name)
r = manuel.action_degisiklik_olustur()
ok(r['res_id'] and Degisiklik.browse(r['res_id']).siniflandirma == 'yok', "kurala uymayan belgeden elle değişiklik açıldı")
try:
    with env.cr.savepoint():
        Degisiklik.browse(r['res_id']).action_onayla(); onaylandi = True
except UserError:
    onaylandi = False
ok(not onaylandi, "sınıflandırılmamış ve modülsüz değişiklik onaylanamaz")

# --- Denetim günlüğü
kayit = Denetim.search([('model', '=', 'atlas.radar.degisiklik'), ('res_id', '=', yeni.id)])
ok({'olustur', 'inceleme', 'gorev', 'guncelle', 'bildirim'} <= set(kayit.mapped('islem')), "denetim: oluşturma, bildirim, inceleme, görev, alan değişikliği")
ok(Denetim.search_count([('model', '=', 'atlas.radar.kaynak'), ('res_id', '=', k.id), ('islem', '=', 'tarama')]) >= 5, "her tarama günlüğe yazıldı")
for islem in ('write', 'unlink'):
    try:
        with env.cr.savepoint():
            getattr(kayit[:1], islem)(*([{'aciklama': 'x'}] if islem == 'write' else [])); yapildi = True
    except UserError:
        yapildi = False
    ok(not yapildi, f"denetim kaydı değiştirilemez/silinemez ({islem})")

# --- Yapay zekâ önerisi (sahte API)
asgari.action_kurallari_uygula()
try:
    with env.cr.savepoint():
        asgari.action_ai_iste(); kapali = False
except UserError:
    kapali = True
ok(kapali, "AI kapalıyken öneri istenemez")
ayar = env['atlas.radar.ayar'].create({'ai_etkin': True, 'ai_anahtar': 'sk-test', 'ai_model': 'claude-sonnet-5'})
ayar.action_kaydet()
ok(env['atlas.radar.ayar']._ayar('ai_etkin') and 'sk-test' not in (Denetim.search([('islem', '=', 'ayar')], limit=1).aciklama or ''),
   "ayar kaydedildi; API anahtarı günlüğe yazılmadı")
asgari.action_ai_iste()

class SahteAi:
    def __init__(self): self.govde = None
    def post(self, url, json=None, headers=None, timeout=None):
        self.govde, self.basliklar = json, headers
        cevap = {'kategori': 'bordro', 'onem': 'kritik', 'moduller': ['atlas_bordro', 'olmayan_modul'], 'yururluk_tarihi': '2027-01-01',
                 'ozet': 'Asgari ücret değişti; bordro parametreleri güncellenmeli.', 'ayar_gerekli': True, 'guven': 88}
        class R:
            status_code = 200
            def json(s): return {'content': [{'type': 'text', 'text': 'İşte sonuç: ' + __import__('json').dumps(cevap)}]}
        return R()

sahte = SahteAi()
Degisiklik._ai_isle(oturum=sahte)
ok(asgari.ai_durum == 'tamam' and asgari.ai_onem == 'kritik' and asgari.ai_guven == 88 and asgari.ai_modul_ids.mapped('teknik_ad') == ['atlas_bordro']
   and asgari.ai_yururluk == date(2027, 1, 1), "AI önerisi alındı (bilinmeyen modül yok sayıldı)")
ok(sahte.govde['model'] == 'claude-sonnet-5' and sahte.basliklar['x-api-key'] == 'sk-test' and 'Asgari' in sahte.govde['messages'][0]['content'],
   "AI isteği: model, anahtar, değişiklik metni")
ok(asgari.siniflandirma == 'kural' and not asgari.ai_onerisi, "AI önerisi kabul edilmeden sınıflandırma değişmez")
asgari.action_ai_kabul()
ok(asgari.siniflandirma == 'ai' and asgari.ai_onerisi and asgari.guven == 88 and asgari.ozet.startswith('Asgari ücret'),
   "öneri uygulandı: 'AI önerisi' işaretli, güven 88")

# --- Günlük özet, panel, API serileştirme
env.ref('base.user_admin').email = env.ref('base.user_admin').email or 'admin@ornek.com'
mail = Degisiklik._ozet_gonder()
ok(mail and 'Asgari' in mail.body_html and env.ref('base.user_admin').email in mail.email_to and mail.state == 'outgoing',
   "günlük özet e-postası kuyruğa alındı")
p = Degisiklik.panel_verisi()
ok({'yeni', 'aksiyon', 'kritik', 'yaklasan', 'sorunlu_kaynak'} <= set(p['kpi']) and p['son'] and p['kaynaklar']
   and p['kpi']['sorunlu_kaynak'] >= 2, "panel verisi: KPI, son değişiklikler, kaynak sağlığı")
from odoo.addons.atlas_radar.controllers.api import _degisiklik
v = _degisiklik(asgari, ayrinti=True)
ok(v['onem'] == 'kritik' and v['ai_onerisi'] and v['etkiler'] and json.dumps(v, default=str), "API: değişiklik JSON'a dönüştü")
ok(Degisiklik.search_count([('gecikti', '=', True)]) >= 0, "yürürlüğü yaklaşan araması çalışıyor")

# --- Şimdi tara: kullanıcı isteğinde dış bağlantı yok, görev tetiklenir
onceki = env['ir.cron.trigger'].search_count([('cron_id', '=', env.ref('atlas_radar.ir_cron_radar_tara').id)])
k.action_simdi_tara()
ok(env['ir.cron.trigger'].search_count([('cron_id', '=', env.ref('atlas_radar.ir_cron_radar_tara').id)]) == onceki + 1 and not k.son_kontrol,
   "Şimdi Tara: tarama arka plan görevine bırakıldı")
ok(not env['account.move'].search_count([('create_date', '>=', yeni.create_date), ('ref', 'ilike', 'radar')]), "Radar ERP kaydı oluşturmadı")
env.cr.rollback(); print("(geri alındı)")
