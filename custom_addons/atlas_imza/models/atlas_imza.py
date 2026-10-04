import base64
import hashlib
import io
import secrets
from datetime import timedelta

from PIL import Image

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import file_path, format_datetime
from odoo.tools.pdf import PdfFileReader, PdfFileWriter

TALEP_DURUMLARI = [
    ('taslak', 'Taslak'),
    ('gonderildi', 'İmza Bekleniyor'),
    ('tamamlandi', 'Tamamlandı'),
    ('reddedildi', 'Reddedildi'),
    ('suresi_doldu', 'Süresi Doldu'),
    ('iptal', 'İptal'),
]
IMZACI_DURUMLARI = [
    ('bekliyor', 'Sırada'),
    ('gonderildi', 'Gönderildi'),
    ('goruldu', 'Görüntülendi'),
    ('imzaladi', 'İmzaladı'),
    ('reddetti', 'Reddetti'),
]
OLAYLAR = [
    ('olusturma', 'Oluşturuldu'),
    ('gonderim', 'Gönderildi'),
    ('goruntuleme', 'Görüntülendi'),
    ('imza', 'İmzalandı'),
    ('red', 'Reddedildi'),
    ('tamamlama', 'Tamamlandı'),
    ('iptal', 'İptal edildi'),
    ('hatirlatma', 'Hatırlatma'),
    ('sure', 'Süresi doldu'),
]

YAZI_TIPI = 'web/static/fonts/google/Roboto/Roboto-Regular.ttf'
YAZI_TIPI_KALIN = 'web/static/fonts/google/Roboto/Roboto-Bold.ttf'
IMZA_GENISLIK = 0.28  # sayfa genişliğine oranla imza kutusu


def _sha256(veri):
    return hashlib.sha256(veri).hexdigest()


def _yazi_tiplerini_kaydet():
    """Türkçe karakterleri basabilmek için reportlab'e TTF kaydeder."""
    from reportlab.pdfbase import pdfmetrics  # noqa: PLC0415
    from reportlab.pdfbase.ttfonts import TTFont  # noqa: PLC0415
    if 'AtlasImza' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('AtlasImza', file_path(YAZI_TIPI)))
        pdfmetrics.registerFont(TTFont('AtlasImzaKalin', file_path(YAZI_TIPI_KALIN)))


class AtlasImzaTalep(models.Model):
    _name = 'atlas.imza.talep'
    _description = 'İmza Talebi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Numara', required=True, copy=False, readonly=True, default='/')
    konu = fields.Char(string='Konu', required=True, tracking=True)
    mesaj = fields.Html(string='İmzacılara Mesaj', sanitize=True)
    durum = fields.Selection(TALEP_DURUMLARI, string='Durum', default='taslak', required=True, tracking=True,
                             copy=False, index=True)
    dosya = fields.Binary(string='Belge (PDF)', attachment=True, copy=True)
    dosya_adi = fields.Char(string='Dosya Adı')
    sayfa_sayisi = fields.Integer(string='Sayfa', compute='_compute_sayfa_sayisi', store=True)
    orijinal_ozet = fields.Char(string='Orijinal SHA-256', copy=False, readonly=True)
    imzali_dosya = fields.Binary(string='İmzalı Belge', attachment=True, copy=False, readonly=True)
    imzali_dosya_adi = fields.Char(copy=False)
    imzali_ozet = fields.Char(string='İmzalı SHA-256', copy=False, readonly=True)
    sirali = fields.Boolean(string='Sıralı İmza', default=True,
                            help='İşaretliyse imzacılar sırayla davet edilir; bir sonraki kişi öncekinin imzasından sonra e-posta alır.')
    son_tarih = fields.Date(string='Son İmza Tarihi', tracking=True)
    hatirlatma_gun = fields.Integer(string='Hatırlatma (gün)', default=3,
                                    help='Bu kadar gün imzalanmayan davetler için hatırlatma e-postası gönderilir. 0: kapalı.')
    imzaci_ids = fields.One2many('atlas.imza.imzaci', 'talep_id', string='İmzacılar', copy=True)
    denetim_ids = fields.One2many('atlas.imza.denetim', 'talep_id', string='Denetim İzi', readonly=True)
    imzalanan_sayisi = fields.Integer(compute='_compute_ilerleme')
    imzaci_sayisi = fields.Integer(compute='_compute_ilerleme')
    ilerleme = fields.Float(string='İlerleme', compute='_compute_ilerleme')
    res_model = fields.Char(string='İlgili Model', readonly=True, copy=False)
    res_id = fields.Many2oneReference(string='İlgili Kayıt', model_field='res_model', readonly=True, copy=False)
    tamamlanma_tarihi = fields.Datetime(string='Tamamlanma', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Sorumlu', default=lambda self: self.env.user, tracking=True)

    @api.depends('dosya')
    def _compute_sayfa_sayisi(self):
        for talep in self:
            talep.sayfa_sayisi = 0
            if talep.dosya:
                try:
                    talep.sayfa_sayisi = len(PdfFileReader(io.BytesIO(talep.dosya.content), strict=False).pages)
                except Exception:  # noqa: BLE001 - bozuk dosya, kısıt yakalar
                    talep.sayfa_sayisi = 0

    @api.depends('imzaci_ids.durum')
    def _compute_ilerleme(self):
        for talep in self:
            talep.imzaci_sayisi = len(talep.imzaci_ids)
            talep.imzalanan_sayisi = len(talep.imzaci_ids.filtered(lambda i: i.durum == 'imzaladi'))
            talep.ilerleme = 100.0 * talep.imzalanan_sayisi / talep.imzaci_sayisi if talep.imzaci_sayisi else 0.0

    @api.constrains('dosya')
    def _check_dosya(self):
        for talep in self.filtered('dosya'):
            if not talep.dosya.content.startswith(b'%PDF'):
                raise ValidationError(self.env._('İmza için yalnızca PDF belge yüklenebilir.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('atlas.imza.talep') or '/'
        talepler = super().create(vals_list)
        for talep in talepler:
            talep._denetim('olusturma')
        return talepler

    def write(self, vals):
        if {'dosya', 'imzaci_ids'} & set(vals) and any(t.durum != 'taslak' for t in self):
            raise UserError(self.env._('Gönderilmiş bir talebin belgesi ve imzacıları değiştirilemez; iptal edip yeniden oluşturun.'))
        return super().write(vals)

    def unlink(self):
        if any(t.durum in ('gonderildi', 'tamamlandi') for t in self):
            raise UserError(self.env._('İmza bekleyen veya tamamlanmış talepler silinemez.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Akış
    # -------------------------------------------------------------------------

    def _denetim(self, olay, imzaci=None, aciklama=None, ip=None, tarayici=None):
        self.ensure_one()
        return self.env['atlas.imza.denetim'].sudo().create({
            'talep_id': self.id, 'imzaci_id': imzaci.id if imzaci else False, 'olay': olay,
            'aciklama': aciklama, 'ip': ip, 'tarayici': (tarayici or '')[:250] or False,
            'kullanici_id': self.env.user.id,
        })

    def action_gonder(self):
        for talep in self:
            if talep.durum != 'taslak':
                raise UserError(self.env._('%s zaten gönderilmiş.', talep.name))
            if not talep.dosya:
                raise UserError(self.env._('%s için imzalanacak PDF belgeyi yükleyin.', talep.name))
            if not talep.imzaci_ids:
                raise UserError(self.env._('%s için en az bir imzacı ekleyin.', talep.name))
            eksik = talep.imzaci_ids.filtered(lambda i: not i.partner_id.email)
            if eksik:
                raise UserError(self.env._('E-posta adresi olmayan imzacılar: %s', ', '.join(eksik.mapped('partner_id.name'))))
            if not talep.sayfa_sayisi:
                raise UserError(self.env._('PDF okunamadı; belgeyi kontrol edin.'))
            for imzaci in talep.imzaci_ids:
                if imzaci.sayfa > talep.sayfa_sayisi:
                    raise UserError(self.env._('%(kisi)s için seçilen sayfa (%(sayfa)s) belgede yok.',
                                               kisi=imzaci.partner_id.name, sayfa=imzaci.sayfa))
            talep.write({'durum': 'gonderildi', 'orijinal_ozet': _sha256(talep.dosya.content)})
            talep.message_subscribe(partner_ids=talep.imzaci_ids.partner_id.ids)
            talep._denetim('gonderim', aciklama=self.env._('Orijinal belge özeti: %s', talep.orijinal_ozet))
            talep._davet_gonder()
        return True

    def _siradaki_imzacilar(self):
        self.ensure_one()
        bekleyen = self.imzaci_ids.filtered(lambda i: i.durum == 'bekliyor')
        if not self.sirali:
            return bekleyen
        if self.imzaci_ids.filtered(lambda i: i.durum in ('gonderildi', 'goruldu')):
            return self.env['atlas.imza.imzaci']
        ilk = bekleyen.sorted(lambda i: (i.sira, i.id))[:1]
        return bekleyen.filtered(lambda i: i.sira == ilk.sira) if ilk else ilk

    def _davet_gonder(self):
        self.ensure_one()
        sablon = self.env.ref('atlas_imza.mail_template_imza_davet')
        for imzaci in self._siradaki_imzacilar():
            imzaci.sudo().write({'durum': 'gonderildi', 'davet_tarihi': fields.Datetime.now()})
            sablon.sudo().send_mail(imzaci.id, force_send=False)
            self.message_post(body=self.env._('İmza daveti gönderildi: %s', imzaci.partner_id.name),
                              subtype_xmlid='mail.mt_note')

    def _imza_sonrasi(self):
        """Bir imzadan sonra: sıradakini davet et ya da talebi tamamla."""
        self.ensure_one()
        if all(i.durum == 'imzaladi' for i in self.imzaci_ids):
            self._tamamla()
        else:
            self._davet_gonder()

    def _tamamla(self):
        self.ensure_one()
        pdf = self._imzali_pdf_olustur()
        ad = (self.dosya_adi or self.konu or self.name).rsplit('.', 1)[0] + ' (imzalı).pdf'
        self.sudo().write({
            'imzali_dosya': base64.b64encode(pdf).decode(), 'imzali_dosya_adi': ad, 'imzali_ozet': _sha256(pdf),
            'durum': 'tamamlandi', 'tamamlanma_tarihi': fields.Datetime.now(),
        })
        self._denetim('tamamlama', aciklama=self.env._('İmzalı belge özeti: %s', self.imzali_ozet))
        self.sudo().message_post(
            body=self.env._('Tüm imzacılar belgeyi imzaladı. İmzalı belge ektedir.'),
            partner_ids=self.imzaci_ids.partner_id.ids, attachments=[(ad, pdf)],
            message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=(self.user_id or self.create_uid).partner_id.id)
        if self.res_model and self.res_id and self.res_model in self.env:
            kayit = self.env[self.res_model].sudo().browse(self.res_id).exists()
            if kayit and hasattr(kayit, 'message_post'):
                kayit.message_post(body=self.env._('%s imza talebi tamamlandı.', self.name), attachments=[(ad, pdf)])

    def action_iptal(self):
        for talep in self.filtered(lambda t: t.durum in ('taslak', 'gonderildi')):
            talep.write({'durum': 'iptal'})
            talep._denetim('iptal')
        return True

    def action_taslaga_al(self):
        for talep in self.filtered(lambda t: t.durum in ('iptal', 'reddedildi', 'suresi_doldu')):
            talep.write({'durum': 'taslak', 'orijinal_ozet': False})
            for imzaci in talep.imzaci_ids.sudo():
                # eski bağlantılar geçersiz olsun diye anahtar yenilenir
                imzaci.write({'durum': 'bekliyor', 'imza_resmi': False, 'imza_tarihi': False, 'davet_tarihi': False,
                              'son_hatirlatma': False, 'red_nedeni': False, 'ip': False, 'tarayici': False,
                              'ad_soyad': False, 'token': secrets.token_urlsafe(32)})
        return True

    def action_hatirlat(self):
        sablon = self.env.ref('atlas_imza.mail_template_imza_davet')
        for talep in self.filtered(lambda t: t.durum == 'gonderildi'):
            for imzaci in talep.imzaci_ids.filtered(lambda i: i.durum in ('gonderildi', 'goruldu')):
                sablon.sudo().send_mail(imzaci.id, force_send=False)
                imzaci.sudo().son_hatirlatma = fields.Datetime.now()
                talep._denetim('hatirlatma', imzaci)
        return True

    def action_imzali_indir(self):
        self.ensure_one()
        if not self.imzali_dosya:
            raise UserError(self.env._('Henüz imzalı belge oluşmadı.'))
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': f'/web/content/atlas.imza.talep/{self.id}/imzali_dosya/{self.imzali_dosya_adi}?download=true'}

    @api.model
    def _cron_imza(self):
        bugun = fields.Date.context_today(self)
        simdi = fields.Datetime.now()
        for talep in self.search([('durum', '=', 'gonderildi')]):
            if talep.son_tarih and talep.son_tarih < bugun:
                talep.write({'durum': 'suresi_doldu'})
                talep._denetim('sure')
                talep.message_post(body=self.env._('Son imza tarihi geçti; talep kapatıldı.'))
                continue
            if talep.hatirlatma_gun <= 0:
                continue
            sinir = simdi - timedelta(days=talep.hatirlatma_gun)
            gecikenler = talep.imzaci_ids.filtered(
                lambda i: i.durum in ('gonderildi', 'goruldu') and (i.son_hatirlatma or i.davet_tarihi or simdi) <= sinir)
            if gecikenler:
                sablon = self.env.ref('atlas_imza.mail_template_imza_davet')
                for imzaci in gecikenler:
                    sablon.send_mail(imzaci.id, force_send=False)
                    imzaci.son_hatirlatma = simdi
                    talep._denetim('hatirlatma', imzaci)

    # -------------------------------------------------------------------------
    # PDF
    # -------------------------------------------------------------------------

    def _imzali_pdf_olustur(self):
        """İmzaları sayfalara basar ve sona denetim sayfası ekler."""
        self.ensure_one()
        from reportlab.pdfgen import canvas  # noqa: PLC0415
        from reportlab.lib.utils import ImageReader  # noqa: PLC0415
        _yazi_tiplerini_kaydet()

        okuyucu = PdfFileReader(io.BytesIO(self.dosya.content), strict=False)
        yazici = PdfFileWriter()
        sayfa_adedi = len(okuyucu.pages)
        imzacilar = self.imzaci_ids.filtered(lambda i: i.durum == 'imzaladi').sorted(lambda i: (i.sira, i.id))
        sayfaya_gore = {}
        for imzaci in imzacilar:
            sayfaya_gore.setdefault((imzaci.sayfa or sayfa_adedi) - 1, []).append(imzaci)

        for no, sayfa in enumerate(okuyucu.pages):
            if no in sayfaya_gore:
                kutu = sayfa.mediabox
                sol, alt = float(kutu.left), float(kutu.bottom)
                gen, yuk = float(kutu.width), float(kutu.height)
                tampon = io.BytesIO()
                tuval = canvas.Canvas(tampon, pagesize=(gen, yuk))
                for sira, imzaci in enumerate(sayfaya_gore[no]):
                    x_oran, y_oran = imzaci._konum(sira)
                    kutu_gen = gen * IMZA_GENISLIK
                    kutu_yuk = kutu_gen * 0.4
                    x = sol + gen * x_oran / 100.0
                    y = alt + yuk * (1 - y_oran / 100.0) - kutu_yuk  # oran üstten ölçülür
                    resim = ImageReader(io.BytesIO(imzaci.imza_resmi.content))
                    tuval.drawImage(resim, x, y + 14, width=kutu_gen, height=kutu_yuk - 14,
                                    mask='auto', preserveAspectRatio=True, anchor='sw')
                    tuval.setStrokeColorRGB(0.15, 0.39, 0.92)
                    tuval.setLineWidth(0.6)
                    tuval.line(x, y + 13, x + kutu_gen, y + 13)
                    tuval.setFillColorRGB(0.2, 0.2, 0.2)
                    tuval.setFont('AtlasImza', 6.5)
                    tuval.drawString(x, y + 6, imzaci.ad_soyad or imzaci.partner_id.name)
                    tuval.drawString(x, y - 1, '%s · %s' % (
                        format_datetime(self.env, imzaci.imza_tarihi, dt_format='dd.MM.yyyy HH:mm'), self.name))
                tuval.save()
                katman = PdfFileReader(io.BytesIO(tampon.getvalue()), strict=False).pages[0]
                sayfa.merge_page(katman)
            yazici.add_page(sayfa)

        for sayfa in PdfFileReader(io.BytesIO(self._denetim_sayfasi()), strict=False).pages:
            yazici.add_page(sayfa)
        yazici.add_metadata({'/Title': self.konu, '/Subject': self.name, '/Producer': 'Atlas e-İmza'})
        cikti = io.BytesIO()
        yazici.write(cikti)
        return cikti.getvalue()

    def _denetim_sayfasi(self):
        from reportlab.lib.pagesizes import A4  # noqa: PLC0415
        from reportlab.lib.utils import ImageReader  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415
        _yazi_tiplerini_kaydet()
        gen, yuk = A4
        tampon = io.BytesIO()
        tuval = canvas.Canvas(tampon, pagesize=A4)
        kenar = 40
        y = yuk - kenar

        def satir(metin, boyut=8.5, kalin=False, girinti=0, aralik=12):
            nonlocal y
            if y < kenar + 20:
                tuval.showPage()
                y = yuk - kenar
            tuval.setFont('AtlasImzaKalin' if kalin else 'AtlasImza', boyut)
            tuval.drawString(kenar + girinti, y, metin)
            y -= aralik

        tz_tarih = lambda t: format_datetime(self.env, t, dt_format='dd.MM.yyyy HH:mm:ss') if t else '-'  # noqa: E731
        satir(self.env._('İmza Denetim Kaydı'), 15, True, aralik=20)
        satir(f'{self.name} — {self.konu}', 10, True, aralik=16)
        satir(self.env._('Belge: %(ad)s (%(sayfa)s sayfa)', ad=self.dosya_adi or '-', sayfa=self.sayfa_sayisi))
        satir(self.env._('Gönderen: %(kisi)s · %(sirket)s', kisi=self.create_uid.name, sirket=self.company_id.name))
        satir(self.env._('Orijinal belge SHA-256: %s', self.orijinal_ozet or '-'), 7.5)
        satir(self.env._('Bu sayfa belgeye eklenmeden önce oluşturulmuştur; imzalı dosyanın özeti sistemde saklanır.'), 7.5,
              aralik=20)

        satir(self.env._('İmzacılar'), 11, True, aralik=16)
        for imzaci in self.imzaci_ids.sorted(lambda i: (i.sira, i.id)):
            if y < kenar + 90:
                tuval.showPage()
                y = yuk - kenar
            satir(f'{imzaci.sira}. {imzaci.ad_soyad or imzaci.partner_id.name}  <{imzaci.partner_id.email or ""}>', 9.5, True)
            satir(self.env._('Durum: %(durum)s · Davet: %(davet)s · İmza: %(imza)s',
                             durum=dict(IMZACI_DURUMLARI)[imzaci.durum], davet=tz_tarih(imzaci.davet_tarihi),
                             imza=tz_tarih(imzaci.imza_tarihi)), girinti=12)
            satir(self.env._('IP: %(ip)s · Tarayıcı: %(tarayici)s', ip=imzaci.ip or '-',
                             tarayici=(imzaci.tarayici or '-')[:95]), 7, girinti=12)
            if imzaci.imza_resmi:
                tuval.drawImage(ImageReader(io.BytesIO(imzaci.imza_resmi.content)), kenar + 12, y - 36, width=150,
                                height=40, mask='auto', preserveAspectRatio=True, anchor='sw')
                y -= 46
            y -= 6

        satir(self.env._('Olaylar'), 11, True, aralik=16)
        for kayit in self.denetim_ids.sorted('id'):
            kim = kayit.imzaci_id.partner_id.name or kayit.kullanici_id.name or ''
            metin = f'{tz_tarih(kayit.create_date)}  {dict(OLAYLAR)[kayit.olay]}  {kim}'
            if kayit.ip:
                metin += f'  ({kayit.ip})'
            satir(metin, 8)
            if kayit.aciklama:
                satir(kayit.aciklama[:120], 7, girinti=12)
        tuval.setFont('AtlasImza', 7)
        tuval.drawString(kenar, 25, self.env._('Atlas e-İmza · Basit elektronik imza kaydıdır; 5070 sayılı Kanun kapsamında '
                                               'nitelikli elektronik imza yerine geçmez.'))
        tuval.save()
        return tampon.getvalue()


class AtlasImzaImzaci(models.Model):
    _name = 'atlas.imza.imzaci'
    _description = 'İmzacı'
    _order = 'sira, id'
    _rec_name = 'partner_id'

    talep_id = fields.Many2one('atlas.imza.talep', string='Talep', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Kişi', required=True)
    sira = fields.Integer(string='Sıra', default=1)
    durum = fields.Selection(IMZACI_DURUMLARI, string='Durum', default='bekliyor', required=True, copy=False)
    token = fields.Char(string='Erişim Anahtarı', required=True, copy=False,
                        default=lambda self: secrets.token_urlsafe(32))
    sayfa = fields.Integer(string='İmza Sayfası', default=0, help='0: son sayfa.')
    konum_otomatik = fields.Boolean(string='Otomatik Konum', default=True,
                                    help='İmzalar sayfanın altına yan yana yerleştirilir.')
    x_oran = fields.Float(string='Soldan %', default=5.0)
    y_oran = fields.Float(string='Üstten %', default=82.0)
    ad_soyad = fields.Char(string='İmzalayan Ad Soyad', copy=False)
    imza_resmi = fields.Binary(string='İmza', attachment=True, copy=False)
    imza_tarihi = fields.Datetime(string='İmza Tarihi', copy=False, readonly=True)
    davet_tarihi = fields.Datetime(string='Davet Tarihi', copy=False, readonly=True)
    son_hatirlatma = fields.Datetime(copy=False, readonly=True)
    ip = fields.Char(string='IP', copy=False, readonly=True)
    tarayici = fields.Char(string='Tarayıcı', copy=False, readonly=True)
    red_nedeni = fields.Text(string='Red Nedeni', copy=False, readonly=True)
    url = fields.Char(string='İmza Bağlantısı', compute='_compute_url', compute_sudo=True)

    _token_uniq = models.UniqueIndex('(token)')

    def _compute_url(self):
        # website kuruluyken get_base_url tekil kayıt ister
        for imzaci in self:
            imzaci.url = f'{imzaci.get_base_url()}/imza/{imzaci.token}'

    def _konum(self, sira_sayfada):
        """(soldan %, üstten %) — otomatikte 3 sütunlu ızgara, alttan yukarı."""
        self.ensure_one()
        if not self.konum_otomatik:
            return self.x_oran, self.y_oran
        sutun, satir = sira_sayfada % 3, sira_sayfada // 3
        return 4.0 + sutun * 32.0, 84.0 - satir * 13.0

    def _imzalayabilir(self):
        self.ensure_one()
        return self.talep_id.durum == 'gonderildi' and self.durum in ('gonderildi', 'goruldu')

    def _goruntulendi(self, ip=None, tarayici=None):
        self.ensure_one()
        if self.durum == 'gonderildi':
            self.durum = 'goruldu'
            self.talep_id._denetim('goruntuleme', self, ip=ip, tarayici=tarayici)

    def _imzala(self, png, ad_soyad, ip=None, tarayici=None):
        """Herkese açık sayfadan imza (sudo ile çağrılır)."""
        self.ensure_one()
        if not self._imzalayabilir():
            raise UserError(self.env._('Bu imza bağlantısı artık geçerli değil.'))
        ad_soyad = (ad_soyad or '').strip()
        if len(ad_soyad) < 3:
            raise UserError(self.env._('Adınızı ve soyadınızı yazın.'))
        try:
            resim = Image.open(io.BytesIO(png))
            resim.verify()
            resim = Image.open(io.BytesIO(png))
        except Exception as hata:  # noqa: BLE001
            raise UserError(self.env._('İmza görüntüsü okunamadı.')) from hata
        if resim.format != 'PNG' or resim.width > 3000 or resim.height > 2000:
            raise UserError(self.env._('Geçersiz imza görüntüsü.'))
        if not self._cizim_var(resim):
            raise UserError(self.env._('Lütfen imzanızı çizin.'))
        self.write({'durum': 'imzaladi', 'imza_resmi': base64.b64encode(png).decode(), 'ad_soyad': ad_soyad,
                    'imza_tarihi': fields.Datetime.now(), 'ip': ip, 'tarayici': (tarayici or '')[:250]})
        self.talep_id._denetim('imza', self, ip=ip, tarayici=tarayici,
                               aciklama=self.env._('Ad soyad: %(ad)s · İmza görüntüsü özeti: %(ozet)s',
                                                   ad=ad_soyad, ozet=_sha256(png)[:16]))
        self.talep_id.message_post(body=self.env._('%s belgeyi imzaladı.', ad_soyad), subtype_xmlid='mail.mt_note',
                                   author_id=self.partner_id.id)
        self.talep_id._imza_sonrasi()

    @staticmethod
    def _cizim_var(resim):
        """Beyaz zemine yerleştirildiğinde koyu piksel var mı (boş tuval reddedilir)."""
        zemin = Image.new('RGBA', resim.size, (255, 255, 255, 255))
        zemin.alpha_composite(resim.convert('RGBA'))
        return zemin.convert('L').getextrema()[0] < 160

    def _reddet(self, neden, ip=None, tarayici=None):
        self.ensure_one()
        if not self._imzalayabilir():
            raise UserError(self.env._('Bu imza bağlantısı artık geçerli değil.'))
        neden = (neden or '').strip()
        if not neden:
            raise UserError(self.env._('Red nedenini yazın.'))
        self.write({'durum': 'reddetti', 'red_nedeni': neden, 'ip': ip, 'tarayici': (tarayici or '')[:250]})
        talep = self.talep_id
        talep._denetim('red', self, aciklama=neden, ip=ip, tarayici=tarayici)
        talep.write({'durum': 'reddedildi'})
        talep.message_post(body=self.env._('%(kisi)s imzalamayı reddetti: %(neden)s', kisi=self.partner_id.name, neden=neden),
                           partner_ids=talep.user_id.partner_id.ids, subtype_xmlid='mail.mt_comment',
                           author_id=self.partner_id.id)
        if talep.user_id:
            talep.activity_schedule('mail.mail_activity_data_todo', user_id=talep.user_id.id,
                                    summary=self.env._('İmza reddedildi: %s', self.partner_id.name), note=neden)


class AtlasImzaDenetim(models.Model):
    _name = 'atlas.imza.denetim'
    _description = 'İmza Denetim Kaydı'
    _order = 'id'

    talep_id = fields.Many2one('atlas.imza.talep', string='Talep', required=True, ondelete='cascade', index=True)
    imzaci_id = fields.Many2one('atlas.imza.imzaci', string='İmzacı', ondelete='set null')
    olay = fields.Selection(OLAYLAR, string='Olay', required=True)
    aciklama = fields.Char(string='Açıklama')
    ip = fields.Char(string='IP')
    tarayici = fields.Char(string='Tarayıcı')
    kullanici_id = fields.Many2one('res.users', string='Kullanıcı')
