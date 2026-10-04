import base64
import io
from datetime import date, timedelta
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools.pdf import PdfFileReader
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
b64 = lambda b: base64.b64encode(b).decode()

def pdf_olustur(sayfa=2):
    t = io.BytesIO(); c = canvas.Canvas(t)
    for i in range(sayfa):
        c.drawString(100, 750, f'Sozlesme sayfa {i + 1}'); c.showPage()
    c.save(); return t.getvalue()

def imza_png(bos=False):
    r = Image.new('RGBA', (400, 150), (0, 0, 0, 0))
    if not bos:
        ImageDraw.Draw(r).line([(20, 100), (120, 40), (220, 110), (380, 30)], fill=(15, 23, 42, 255), width=4)
    t = io.BytesIO(); r.save(t, 'PNG'); return t.getvalue()

T = env['atlas.imza.talep']
u1 = env['res.users'].create({'name': 'IMZ Satışçı', 'login': 'imz_satis', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
u2 = env['res.users'].create({'name': 'IMZ Diğer', 'login': 'imz_diger', 'group_ids': [Command.set([env.ref('base.group_user').id])]})
p1 = env['res.partner'].create({'name': 'Ayşe Yılmaz', 'email': 'ayse@ornek.com.tr'})
p2 = env['res.partner'].create({'name': 'Şükrü Öztürk', 'email': 'sukru@ornek.com.tr'})
p3 = env['res.partner'].create({'name': 'Epostasız Kişi'})

try:
    with env.cr.savepoint(): T.create({'konu': 'x', 'dosya': b64(b'merhaba'), 'dosya_adi': 'a.txt'}); pdf_degil = False
except Exception: pdf_degil = True
ok(pdf_degil, "PDF olmayan dosya reddedildi")

t = T.with_user(u1).create({'konu': 'Satış Sözleşmesi', 'dosya': b64(pdf_olustur()), 'dosya_adi': 'sozlesme.pdf', 'sirali': True,
                            'imzaci_ids': [Command.create({'partner_id': p1.id, 'sira': 1}), Command.create({'partner_id': p2.id, 'sira': 2})]})
ok(t.name.startswith('IMZ') and t.sayfa_sayisi == 2 and t.durum == 'taslak', f"talep {t.name}: 2 sayfa, taslak")
ok(t.denetim_ids.olay == 'olusturma', "denetim: oluşturuldu")
ok(t not in T.with_user(u2).search([]), "başka kullanıcı talebi görmez")
ok(t in T.with_user(u1).search([]), "oluşturan kendi talebini görür")

t3 = T.create({'konu': 'Eksik', 'dosya': b64(pdf_olustur(1)), 'imzaci_ids': [Command.create({'partner_id': p3.id})]})
try:
    with env.cr.savepoint(): t3.action_gonder(); gitti = True
except UserError: gitti = False
ok(not gitti, "e-postası olmayan imzacıya gönderilemez")
t3.imzaci_ids.write({'partner_id': p1.id, 'sayfa': 5})
try:
    with env.cr.savepoint(): t3.action_gonder(); gitti = True
except UserError: gitti = False
ok(not gitti, "olmayan sayfaya imza konumu reddedildi")

onceki_mail = env['mail.mail'].search([], order='id desc', limit=1).id or 0
t.with_user(u1).action_gonder()
i1, i2 = t.imzaci_ids.sorted('sira')
mailler = env['mail.mail'].search([('id', '>', onceki_mail), ('model', '=', 'atlas.imza.imzaci')])
ok(t.durum == 'gonderildi' and len(t.orijinal_ozet) == 64, "gönderildi, orijinal SHA-256 saklandı")
ok(i1.durum == 'gonderildi' and i2.durum == 'bekliyor' and len(mailler) == 1 and p1 in mailler.recipient_ids
   and i1.token in mailler.body_html, "sıralı: yalnızca ilk imzacıya bağlantılı davet gitti")
try:
    with env.cr.savepoint(): t.with_user(u1).write({'dosya': b64(pdf_olustur(3))}); degisti = True
except UserError: degisti = False
ok(not degisti, "gönderilmiş talebin belgesi değiştirilemez")
try:
    with env.cr.savepoint(): i2.sudo()._imzala(imza_png(), 'Şükrü Öztürk'); sirasiz = True
except UserError: sirasiz = False
ok(not sirasiz, "sırası gelmeyen imzalayamaz")

i1.sudo()._goruntulendi(ip='10.0.0.5', tarayici='TestTarayici/1.0')
ok(i1.durum == 'goruldu' and 'goruntuleme' in t.denetim_ids.mapped('olay'), "görüntüleme denetime yazıldı")
try:
    with env.cr.savepoint(): i1.sudo()._imzala(imza_png(bos=True), 'Ayşe Yılmaz'); bos_imza = True
except UserError: bos_imza = False
ok(not bos_imza, "boş imza tuvali reddedildi")
try:
    with env.cr.savepoint(): i1.sudo()._imzala(b'PNG degil', 'Ayşe Yılmaz'); bozuk = True
except UserError: bozuk = False
ok(not bozuk, "bozuk görüntü reddedildi")

onceki_mail = env['mail.mail'].search([], order='id desc', limit=1).id or 0
i1.sudo()._imzala(imza_png(), 'Ayşe Yılmaz', ip='10.0.0.5', tarayici='TestTarayici/1.0')
mailler = env['mail.mail'].search([('id', '>', onceki_mail), ('model', '=', 'atlas.imza.imzaci')])
ok(i1.durum == 'imzaladi' and i1.imza_tarihi and i1.ip == '10.0.0.5' and i1.imza_resmi, "ilk imza: zaman, IP, görüntü kaydedildi")
ok(i2.durum == 'gonderildi' and len(mailler) == 1 and p2 in mailler.recipient_ids and t.durum == 'gonderildi',
   "sıradaki imzacı davet edildi, talep hâlâ bekliyor")

i2.sudo()._imzala(imza_png(), 'Şükrü Öztürk', ip='10.0.0.9')
ok(t.durum == 'tamamlandi' and t.tamamlanma_tarihi and t.ilerleme == 100, "tüm imzalar: talep tamamlandı")
imzali = t.imzali_dosya.content
okuyucu = PdfFileReader(io.BytesIO(imzali), strict=False)
import hashlib
ok(len(okuyucu.pages) == 3 and hashlib.sha256(imzali).hexdigest() == t.imzali_ozet, "imzalı PDF: 2 sayfa + denetim sayfası, özet doğru")
son_sayfa = okuyucu.pages[1].extract_text(); denetim = okuyucu.pages[2].extract_text()
ok('Ayşe Yılmaz' in son_sayfa and 'Şükrü Öztürk' in son_sayfa and 'Sozlesme sayfa 2' in son_sayfa,
   "imzalar son sayfaya Türkçe adlarla basıldı")
ok(t.orijinal_ozet in denetim and '10.0.0.9' in denetim and 'İmza Denetim Kaydı' in denetim, "denetim sayfası: özet, IP, başlık")
ok(t.imzali_dosya_adi == 'sozlesme (imzalı).pdf', "imzalı dosya adı")
mesaj = t.message_ids.filtered(lambda m: m.attachment_ids and p1 in m.partner_ids and p2 in m.partner_ids)
ok(len(mesaj) == 1 and mesaj.attachment_ids.name == 'sozlesme (imzalı).pdf', "imzalı belge imzacılara e-postayla gönderildi")
ok(t.with_user(u1).action_imzali_indir()['url'].startswith(f'/web/content/atlas.imza.talep/{t.id}/imzali_dosya'), "indirme bağlantısı")

# Paralel + red
r = T.create({'konu': 'Gizlilik Sözleşmesi', 'dosya': b64(pdf_olustur(1)), 'dosya_adi': 'nda.pdf', 'sirali': False, 'user_id': u1.id,
              'imzaci_ids': [Command.create({'partner_id': p1.id}), Command.create({'partner_id': p2.id, 'sayfa': 1, 'konum_otomatik': False, 'x_oran': 50, 'y_oran': 10})]})
r.action_gonder()
ok(all(i.durum == 'gonderildi' for i in r.imzaci_ids), "paralel: tüm imzacılar aynı anda davet edildi")
ok(r.imzaci_ids[1]._konum(0) == (50, 10) and r.imzaci_ids[0]._konum(4) == (36.0, 71.0), "imza konumu: elle ve otomatik ızgara")
eski_token = r.imzaci_ids[0].token
try:
    with env.cr.savepoint(): r.imzaci_ids[0].sudo()._reddet(''); nedensiz = True
except UserError: nedensiz = False
ok(not nedensiz, "red nedeni zorunlu")
r.imzaci_ids[0].sudo()._reddet('Madde 4 hatalı')
ok(r.durum == 'reddedildi' and r.activity_ids.user_id == u1 and not r.imzaci_ids[1]._imzalayabilir(), "red: talep durdu, sorumluya aktivite")
r.action_taslaga_al()
ok(r.durum == 'taslak' and all(i.durum == 'bekliyor' for i in r.imzaci_ids) and r.imzaci_ids[0].token != eski_token,
   "taslağa alındı, eski bağlantılar geçersiz")

# Süre ve hatırlatma
s = T.create({'konu': 'Süreli', 'dosya': b64(pdf_olustur(1)), 'son_tarih': date.today() + timedelta(days=5), 'hatirlatma_gun': 2,
              'imzaci_ids': [Command.create({'partner_id': p1.id})]})
s.action_gonder()
s.imzaci_ids.davet_tarihi = s.imzaci_ids.davet_tarihi - timedelta(days=3)
T._cron_imza()
ok(s.imzaci_ids.son_hatirlatma and 'hatirlatma' in s.denetim_ids.mapped('olay'), "cron: geciken imzacıya hatırlatma")
s.son_tarih = date.today() - timedelta(days=1)
T._cron_imza()
ok(s.durum == 'suresi_doldu' and not s.imzaci_ids._imzalayabilir(), "cron: son tarihi geçen talep kapandı")
try:
    with env.cr.savepoint(): t.unlink(); silindi = True
except UserError: silindi = False
ok(not silindi, "tamamlanmış talep silinemez")
env.cr.rollback(); print("(geri alındı)")
