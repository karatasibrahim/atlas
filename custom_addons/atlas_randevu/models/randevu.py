import secrets
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import html_escape

GUNLER = [('1', 'Pazartesi'), ('2', 'Salı'), ('3', 'Çarşamba'), ('4', 'Perşembe'), ('5', 'Cuma'), ('6', 'Cumartesi'), ('7', 'Pazar')]
SORU_TIPLERI = [('char', 'Tek satır metin'), ('text', 'Çok satırlı metin'), ('phone', 'Telefon'), ('select', 'Açılır liste'),
                ('radio', 'Tek seçim'), ('checkbox', 'Çoklu seçim')]


def _tz_listesi(self):
    return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda t: t if not t.startswith('Etc/') else '_')]


def _cakisir(a1, a2, b1, b2):
    return a1 < b2 and b1 < a2


class AtlasRandevuTur(models.Model):
    """Randevu türü (Enterprise appointment.type eşleniği)."""
    _name = 'atlas.randevu.tur'
    _description = 'Randevu Türü'
    _inherit = ['mail.thread']
    _order = 'sira, id'

    name = fields.Char(string='Randevu Adı', required=True, translate=True, tracking=True)
    active = fields.Boolean(default=True)
    sira = fields.Integer(string='Sıra', default=10)
    renk = fields.Integer(string='Renk')
    aciklama = fields.Html(string='Açıklama', translate=True, help='Randevu sayfasında gösterilir')
    onay_mesaji = fields.Html(string='Onay Mesajı', translate=True, help='Randevu alındıktan sonra gösterilir')
    yayinda = fields.Boolean(string='Herkese Açık Sayfada', help='Kapalıysa yalnız davet bağlantısıyla alınabilir')
    sorumlu_id = fields.Many2one('res.users', string='Sorumlu', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)

    sure = fields.Float(string='Süre (saat)', required=True, default=1.0)
    slot_araligi = fields.Float(string='Başlangıç Aralığı (saat)', default=0.0,
                                help='Ardışık başlangıç saatleri arasındaki süre; boşsa randevu süresi kullanılır')
    tz = fields.Selection(_tz_listesi, string='Saat Dilimi', required=True, default=lambda self: self.env.user.tz or 'Europe/Istanbul')
    kategori = fields.Selection([('tekrarlayan', 'Haftalık (sürekli)'), ('donemlik', 'Belirli tarih aralığında'),
                                 ('ozel', 'Belirli saat dilimleri')], string='Müsaitlik', default='tekrarlayan', required=True)
    baslangic = fields.Datetime(string='Dönem Başlangıcı')
    bitis = fields.Datetime(string='Dönem Bitişi')
    slot_ids = fields.One2many('atlas.randevu.slot', 'tur_id', string='Müsaitlik Dilimleri', copy=True)
    min_planlama_saat = fields.Float(string='En Erken (saat önce)', default=1.0, help='Randevu en az bu kadar saat önceden alınabilir')
    max_planlama_gun = fields.Integer(string='En Geç (gün sonra)', default=30)
    min_iptal_saat = fields.Float(string='İptal Süresi (saat)', default=1.0, help='Müşteri randevudan en geç bu kadar saat önce iptal edebilir')

    planlama = fields.Selection([('personel', 'Personel'), ('kaynak', 'Kaynak (masa, oda, cihaz)')], string='Planlama',
                                default='personel', required=True)
    personel_ids = fields.Many2many('res.users', 'atlas_randevu_tur_personel_rel', 'tur_id', 'user_id', string='Personel',
                                    domain=[('share', '=', False)], default=lambda self: self.env.user)
    atama = fields.Selection([('otomatik', 'Otomatik'), ('secim', 'Müşteri seçer')], string='Atama', default='otomatik', required=True)
    calisma_saatleri = fields.Boolean(string='Çalışma Saatlerine Uy', default=False,
                                      help='Personelin çalışma takvimi dışındaki saatler gösterilmez')
    kaynak_ids = fields.Many2many('atlas.randevu.kaynak', string='Kaynaklar')
    kapasite_yonetimi = fields.Boolean(string='Kapasite Yönetimi', help='Müşteri kişi sayısı girer; kaynak kapasitesi paylaşılır')
    max_kisi = fields.Integer(string='En Fazla Kişi', default=1)

    otomatik_onay = fields.Boolean(string='Otomatik Onay', default=True, help='Kapalıysa randevu "talep" olarak gelir ve onaylanmalıdır')
    konum = fields.Char(string='Konum')
    video = fields.Selection([('yok', 'Yok'), ('discuss', 'Atlas Görüntülü Görüşme'), ('ozel', 'Özel bağlantı')], string='Görüntülü Görüşme',
                             default='yok', required=True)
    video_baglanti = fields.Char(string='Görüşme Bağlantısı')
    hatirlatma_ids = fields.Many2many('calendar.alarm', string='Hatırlatmalar')
    soru_ids = fields.Many2many('atlas.randevu.soru', string='Sorular')
    firsat_olustur = fields.Boolean(string='CRM Fırsatı Oluştur', help='CRM kuruluysa her randevu için fırsat açılır')
    onay_sablon_id = fields.Many2one('mail.template', string='Onay E-postası', domain=[('model', '=', 'calendar.event')],
                                     default=lambda self: self.env.ref('atlas_randevu.mail_randevu_onay', raise_if_not_found=False))
    talep_sablon_id = fields.Many2one('mail.template', string='Talep Alındı E-postası', domain=[('model', '=', 'calendar.event')],
                                      default=lambda self: self.env.ref('atlas_randevu.mail_randevu_talep', raise_if_not_found=False))
    iptal_sablon_id = fields.Many2one('mail.template', string='İptal E-postası', domain=[('model', '=', 'calendar.event')],
                                      default=lambda self: self.env.ref('atlas_randevu.mail_randevu_iptal', raise_if_not_found=False))

    etkinlik_ids = fields.One2many('calendar.event', 'randevu_tur_id', string='Randevular')
    randevu_sayisi = fields.Integer(string='Randevu', compute='_compute_sayilar')
    yaklasan_sayisi = fields.Integer(string='Yaklaşan', compute='_compute_sayilar')
    talep_sayisi = fields.Integer(string='Bekleyen Talep', compute='_compute_sayilar')
    url = fields.Char(string='Randevu Bağlantısı', compute='_compute_url')

    @api.constrains('sure', 'slot_araligi', 'max_kisi')
    def _check_sure(self):
        for t in self:
            if t.sure <= 0:
                raise ValidationError(self.env._('Randevu süresi sıfırdan büyük olmalı.'))
            if t.slot_araligi < 0 or t.max_kisi < 1:
                raise ValidationError(self.env._('Başlangıç aralığı negatif, en fazla kişi 1\'den küçük olamaz.'))

    @api.constrains('kategori', 'baslangic', 'bitis')
    def _check_donem(self):
        for t in self:
            if t.kategori == 'donemlik' and (not t.baslangic or not t.bitis or t.baslangic >= t.bitis):
                raise ValidationError(self.env._('Belirli tarih aralığı için başlangıç bitişten önce olmalı.'))

    def _compute_sayilar(self):
        simdi = fields.Datetime.now()
        Etkinlik = self.env['calendar.event'].sudo()
        for t in self:
            alan = [('randevu_tur_id', '=', t.id)]
            t.randevu_sayisi = Etkinlik.search_count(alan)
            t.yaklasan_sayisi = Etkinlik.search_count(alan + [('start', '>=', simdi), ('randevu_durum', 'in', ('talep', 'onayli'))])
            t.talep_sayisi = Etkinlik.search_count(alan + [('randevu_durum', '=', 'talep')])

    def _compute_url(self):
        taban = self.env['ir.config_parameter'].sudo().get_str('web.base.url') or ''
        for t in self:
            t.url = f'{taban}/randevu/{t.id}' if t.id else False

    # ------------------------------------------------------------------ müsaitlik motoru
    def _tz(self):
        return pytz.timezone(self.tz or 'Europe/Istanbul')

    def _aday_araliklar(self, bas, bit):
        """Kurala uyan aday randevu aralıkları (UTC, tz'siz): [(başlangıç, bitiş)]."""
        self.ensure_one()
        tz = self._tz()
        simdi = fields.Datetime.now()
        bas = max(bas, simdi + timedelta(hours=self.min_planlama_saat))
        bit = min(bit, simdi + timedelta(days=self.max_planlama_gun))
        if self.kategori == 'donemlik':
            bas, bit = max(bas, self.baslangic), min(bit, self.bitis)
        sure = timedelta(hours=self.sure)
        adim = timedelta(hours=self.slot_araligi or self.sure)
        sonuc = set()
        if bas >= bit:
            return []

        def ekle(yerel_bas, yerel_bit):
            t = yerel_bas
            while t + sure <= yerel_bit:
                s = tz.localize(t).astimezone(pytz.utc).replace(tzinfo=None)
                if bas <= s and s + sure <= bit:
                    sonuc.add((s, s + sure))
                t += adim

        if self.kategori == 'ozel':
            for slot in self.slot_ids.filtered(lambda s: s.tip == 'tek' and s.bas_zaman and s.bit_zaman):
                yb = pytz.utc.localize(slot.bas_zaman).astimezone(tz).replace(tzinfo=None)
                yt = pytz.utc.localize(slot.bit_zaman).astimezone(tz).replace(tzinfo=None)
                ekle(yb, yt)
        else:
            gun = pytz.utc.localize(bas).astimezone(tz).date()
            son_gun = pytz.utc.localize(bit).astimezone(tz).date()
            haftalik = self.slot_ids.filtered(lambda s: s.tip == 'haftalik')
            while gun <= son_gun:
                for slot in haftalik.filtered(lambda s: int(s.gun) == gun.isoweekday()):
                    yb = datetime.combine(gun, time()) + timedelta(hours=slot.bas_saat)
                    yt = datetime.combine(gun, time()) + timedelta(hours=slot.bit_saat if slot.bit_saat > slot.bas_saat else 24)
                    ekle(yb, yt)
                gun += timedelta(days=1)
        return sorted(sonuc)

    def _personel_mesgul(self, kullanicilar, bas, bit):
        """{user_id: [(başlangıç, bitiş)]} — iptal edilmemiş, 'meşgul' takvim etkinlikleri."""
        olaylar = self.env['calendar.event'].sudo().search([
            ('partner_ids', 'in', kullanicilar.partner_id.ids), ('start', '<', bit), ('stop', '>', bas),
            ('show_as', '=', 'busy'), ('randevu_durum', '!=', 'iptal')])
        mesgul = {u.id: [] for u in kullanicilar}
        for o in olaylar:
            bas_o, bit_o = (o.start, o.stop) if not o.allday else (datetime.combine(o.start_date, time()), datetime.combine(o.stop_date, time.max))
            for u in kullanicilar:
                if u.partner_id in o.partner_ids:
                    mesgul[u.id].append((bas_o, bit_o))
        return mesgul

    def _calisma_araliklari(self, kullanicilar, bas, bit):
        """{user_id: [(başlangıç, bitiş)]} — çalışma takvimi aralıkları (UTC, tz'siz)."""
        sonuc = {}
        for u in kullanicilar:
            takvim = u.sudo().resource_calendar_id or u.company_id.resource_calendar_id or self.env.company.resource_calendar_id
            if not takvim:
                sonuc[u.id] = None
                continue
            kaynak = u.sudo().resource_ids[:1]
            # kaynaksız takvim aralıkları başlangıcın saat diliminde hesaplanır
            yerel = pytz.timezone(u.tz or self.tz or 'UTC')
            if kaynak:
                araliklar = takvim._work_intervals_batch(pytz.utc.localize(bas), pytz.utc.localize(bit),
                                                         resources_per_tz=kaynak._get_resources_per_tz())[kaynak.id]
            else:
                araliklar = takvim._work_intervals_batch(pytz.utc.localize(bas).astimezone(yerel),
                                                         pytz.utc.localize(bit).astimezone(yerel))[False]
            sonuc[u.id] = [(a.astimezone(pytz.utc).replace(tzinfo=None), b.astimezone(pytz.utc).replace(tzinfo=None)) for a, b, _r in araliklar]
        return sonuc

    def _kaynak_kullanim(self, kaynaklar, bas, bit):
        satirlar = self.env['atlas.randevu.rezervasyon'].sudo().search([
            ('kaynak_id', 'in', kaynaklar.ids), ('bas', '<', bit), ('bit', '>', bas), ('etkinlik_id.randevu_durum', '!=', 'iptal')])
        kullanim = {k.id: [] for k in kaynaklar}
        for s in satirlar:
            kullanim[s.kaynak_id.id].append((s.bas, s.bit, s.kapasite))
        return kullanim

    def _uygunluk(self, bas, bit, personel=None, kaynaklar=None, kisi=1):
        """Aday aralıklar için uygun personel / kaynaklar: [(bas, bit, [user_id], [kaynak_id])]."""
        self.ensure_one()
        adaylar = self._aday_araliklar(bas, bit)
        if not adaylar:
            return []
        ilk, son = adaylar[0][0], adaylar[-1][1]
        sonuc = []
        if self.planlama == 'personel':
            kullanicilar = personel if personel is not None else self.personel_ids
            mesgul = self._personel_mesgul(kullanicilar, ilk, son)
            calisma = self._calisma_araliklari(kullanicilar, ilk, son) if self.calisma_saatleri else {}
            for a, b in adaylar:
                uygun = []
                for u in kullanicilar:
                    if any(_cakisir(a, b, m1, m2) for m1, m2 in mesgul[u.id]):
                        continue
                    if self.calisma_saatleri and calisma.get(u.id) is not None and not any(c1 <= a and b <= c2 for c1, c2 in calisma[u.id]):
                        continue
                    uygun.append(u.id)
                if uygun:
                    sonuc.append((a, b, uygun, []))
        else:
            kaynaklar = kaynaklar if kaynaklar is not None else self.kaynak_ids
            kullanim = self._kaynak_kullanim(kaynaklar, ilk, son)
            for a, b in adaylar:
                uygun = []
                for k in kaynaklar:
                    dolu = sum(c for k1, k2, c in kullanim[k.id] if _cakisir(a, b, k1, k2))
                    if self.kapasite_yonetimi:
                        if k.kapasite - dolu >= kisi:
                            uygun.append(k.id)
                    elif not dolu:
                        uygun.append(k.id)
                if uygun:
                    sonuc.append((a, b, [], uygun))
        return sonuc

    def musait_slotlar(self, bas_tarih, bit_tarih, personel_id=False, kaynak_id=False, kisi=1, davet=False):
        """Randevu sayfası için: yerel güne göre gruplu uygun saatler."""
        self.ensure_one()
        tz = self._tz()
        bas = tz.localize(datetime.combine(fields.Date.to_date(bas_tarih), time())).astimezone(pytz.utc).replace(tzinfo=None)
        bit = tz.localize(datetime.combine(fields.Date.to_date(bit_tarih) + timedelta(days=1), time())).astimezone(pytz.utc).replace(tzinfo=None)
        personel, kaynaklar = self._izinli(davet)
        if personel_id:
            personel = personel.filtered(lambda u: u.id == int(personel_id))
        if kaynak_id:
            kaynaklar = kaynaklar.filtered(lambda k: k.id == int(kaynak_id))
        gunler = {}
        for a, b, kullanicilar, kaynak_idleri in self._uygunluk(bas, bit, personel, kaynaklar, int(kisi or 1)):
            yerel = pytz.utc.localize(a).astimezone(tz)
            gunler.setdefault(yerel.date().isoformat(), []).append({
                'bas': fields.Datetime.to_string(a), 'saat': yerel.strftime('%H:%M'),
                'personel': kullanicilar, 'kaynaklar': kaynak_idleri})
        return gunler

    def _izinli(self, davet=False):
        personel = self.personel_ids
        kaynaklar = self.kaynak_ids
        if davet:
            if davet.personel_ids:
                personel &= davet.personel_ids
            if davet.kaynak_ids:
                kaynaklar &= davet.kaynak_ids
        return personel, kaynaklar

    # ------------------------------------------------------------------ randevu alma
    def randevu_olustur(self, bas, musteri, yanitlar=None, personel_id=False, kaynak_id=False, kisi=1, davet=False, not_metni=''):
        """Seçilen saati yeniden doğrulayıp takvim etkinliği oluşturur.

        musteri: {'ad', 'email', 'telefon'} ya da res.partner; yanitlar: {soru_id: metin | secenek_id | [secenek_id]}
        """
        self.ensure_one()
        tur = self.sudo()
        # aynı türdeki eşzamanlı rezervasyonları sıraya sok (çift rezervasyon önlemi)
        self.env.cr.execute('SELECT id FROM atlas_randevu_tur WHERE id = %s FOR UPDATE', [tur.id])
        bas = fields.Datetime.to_datetime(bas)
        bit = bas + timedelta(hours=tur.sure)
        kisi = max(1, min(int(kisi or 1), tur.max_kisi if tur.kapasite_yonetimi else 1))
        personel, kaynaklar = tur._izinli(davet)
        if personel_id:
            personel = personel.filtered(lambda u: u.id == int(personel_id))
        if kaynak_id:
            kaynaklar = kaynaklar.filtered(lambda k: k.id == int(kaynak_id))
        uygun = [u for u in tur._uygunluk(bas - timedelta(seconds=1), bit + timedelta(seconds=1), personel, kaynaklar, kisi) if u[0] == bas]
        if not uygun:
            raise UserError(self.env._('Seçilen saat artık uygun değil; lütfen başka bir saat seçin.'))
        _a, _b, kullanici_idleri, kaynak_idleri = uygun[0]
        if isinstance(musteri, models.BaseModel):
            partner = musteri
        else:
            partner = tur._musteri_bul(musteri)
        kullanici = self.env['res.users'].sudo().browse(tur._personel_sec(kullanici_idleri, bas)) if kullanici_idleri else tur.sorumlu_id
        secilen_kaynak = self.env['atlas.randevu.kaynak'].sudo().browse(kaynak_idleri[:1])
        aciklama = tur._yanit_html(yanitlar or {}, not_metni)
        vals = {
            'name': f'{tur.name} - {partner.name}',
            'start': bas, 'stop': bit, 'duration': tur.sure,
            'user_id': kullanici.id,
            'partner_ids': [Command.set((kullanici.partner_id | partner).ids)],
            'randevu_tur_id': tur.id,
            'randevu_durum': 'onayli' if tur.otomatik_onay else 'talep',
            'randevu_musteri_id': partner.id,
            'randevu_kisi': kisi,
            'randevu_davet_id': davet.id if davet else False,
            'location': secilen_kaynak.name if secilen_kaynak and not tur.konum else tur.konum,
            'alarm_ids': [Command.set(tur.hatirlatma_ids.ids)],
            'description': aciklama,
            'show_as': 'busy',
        }
        if tur.video == 'ozel' and tur.video_baglanti:
            vals['videocall_location'] = tur.video_baglanti
        etkinlik = self.env['calendar.event'].sudo().with_context(no_mail_to_attendees=True, mail_create_nosubscribe=True).create(vals)
        if tur.video == 'discuss':
            etkinlik._set_discuss_videocall_location()
        if secilen_kaynak:
            self.env['atlas.randevu.rezervasyon'].sudo().create({'etkinlik_id': etkinlik.id, 'kaynak_id': secilen_kaynak.id, 'bas': bas,
                                                                  'bit': bit, 'kapasite': kisi})
            etkinlik.randevu_kaynak_ids = [Command.set(secilen_kaynak.ids)]
        tur._yanitlari_kaydet(etkinlik, partner, yanitlar or {})
        sablon = tur.onay_sablon_id if tur.otomatik_onay else tur.talep_sablon_id
        if sablon and partner.email:
            sablon.sudo().send_mail(etkinlik.id, force_send=False, email_values={'email_to': partner.email, 'recipient_ids': []})
        if not tur.otomatik_onay:
            etkinlik.activity_schedule('mail.mail_activity_data_todo', user_id=kullanici.id,
                                       summary=self.env._('Randevu talebini onaylayın: %s', partner.name)) if hasattr(etkinlik, 'activity_schedule') else None
        if tur.firsat_olustur and 'crm.lead' in self.env and 'opportunity_id' in etkinlik._fields:
            firsat = self.env['crm.lead'].sudo().create({'name': etkinlik.name, 'partner_id': partner.id, 'user_id': kullanici.id,
                                                         'type': 'opportunity', 'description': aciklama})
            etkinlik.opportunity_id = firsat
        etkinlik.message_post(body=self.env._('Randevu çevrim içi alındı (%s).', dict(etkinlik._fields['randevu_durum'].selection)[etkinlik.randevu_durum]))
        return etkinlik

    def _musteri_bul(self, bilgi):
        email = (bilgi.get('email') or '').strip().lower()
        if not bilgi.get('ad') or not email or '@' not in email:
            raise UserError(self.env._('Ad ve geçerli bir e-posta gerekli.'))
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('email', '=ilike', email)], limit=1)
        if not partner:
            partner = Partner.create({'name': bilgi['ad'].strip(), 'email': email, 'phone': bilgi.get('telefon') or False})
        elif bilgi.get('telefon') and not partner.phone:
            partner.phone = bilgi['telefon']
        return partner

    def _personel_sec(self, kullanici_idleri, bas):
        """Otomatik atama: o gün en az randevusu olan personel (eşitlikte sıra)."""
        if len(kullanici_idleri) == 1:
            return kullanici_idleri[0]
        gun_bas = datetime.combine(bas.date(), time())
        yuk = {uid: 0 for uid in kullanici_idleri}
        for e in self.env['calendar.event'].sudo().search([('randevu_tur_id', '!=', False), ('user_id', 'in', kullanici_idleri),
                                                          ('start', '>=', gun_bas), ('start', '<', gun_bas + timedelta(days=1)),
                                                          ('randevu_durum', '!=', 'iptal')]):
            yuk[e.user_id.id] += 1
        return min(kullanici_idleri, key=lambda uid: (yuk[uid], kullanici_idleri.index(uid)))

    def _yanit_degeri(self, soru, deger):
        if soru.tip in ('select', 'radio'):
            secenek = soru.secenek_ids.filtered(lambda s: str(s.id) == str(deger))
            return secenek.name if secenek else ''
        if soru.tip == 'checkbox':
            idler = {str(d) for d in (deger if isinstance(deger, (list, tuple)) else [deger]) if d}
            return ', '.join(soru.secenek_ids.filtered(lambda s: str(s.id) in idler).mapped('name'))
        return (deger or '').strip() if isinstance(deger, str) else str(deger or '')

    def _yanit_html(self, yanitlar, not_metni=''):
        satirlar = []
        for soru in self.soru_ids:
            deger = self._yanit_degeri(soru, yanitlar.get(soru.id, yanitlar.get(str(soru.id))))
            if soru.zorunlu and not deger:
                raise UserError(self.env._('Lütfen yanıtlayın: %s', soru.name))
            if deger:
                satirlar.append(f'<li><b>{html_escape(soru.name)}</b>: {html_escape(deger)}</li>')
        if not_metni:
            satirlar.append(f'<li><b>{html_escape(self.env._("Not"))}</b>: {html_escape(not_metni)}</li>')
        return f'<ul>{"".join(satirlar)}</ul>' if satirlar else ''

    def _yanitlari_kaydet(self, etkinlik, partner, yanitlar):
        Yanit = self.env['atlas.randevu.yanit'].sudo()
        for soru in self.soru_ids:
            deger = yanitlar.get(soru.id, yanitlar.get(str(soru.id)))
            if not deger:
                continue
            if soru.tip in ('select', 'radio', 'checkbox'):
                idler = {str(d) for d in (deger if isinstance(deger, (list, tuple)) else [deger])}
                for s in soru.secenek_ids.filtered(lambda s: str(s.id) in idler):
                    Yanit.create({'etkinlik_id': etkinlik.id, 'soru_id': soru.id, 'secenek_id': s.id, 'partner_id': partner.id})
            else:
                Yanit.create({'etkinlik_id': etkinlik.id, 'soru_id': soru.id, 'metin': str(deger), 'partner_id': partner.id})

    # ------------------------------------------------------------------ eylemler
    def action_randevular(self):
        self.ensure_one()
        eylem = self.env['ir.actions.act_window']._for_xml_id('atlas_randevu.action_atlas_randevu_etkinlik')
        eylem['domain'] = [('randevu_tur_id', '=', self.id)]
        eylem['context'] = {'default_randevu_tur_id': self.id}
        return eylem

    def action_paylas(self):
        self.ensure_one()
        davet = self.env['atlas.randevu.davet'].create({'tur_ids': [Command.set(self.ids)]})
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.randevu.davet', 'res_id': davet.id, 'view_mode': 'form',
                'target': 'new', 'name': self.env._('Paylaş')}

    def action_sayfa(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/randevu/{self.id}', 'target': 'new'}

    def action_standart_program(self):
        """Hafta içi 09:00-12:00 ve 13:00-18:00."""
        for t in self:
            t.slot_ids = [Command.clear()] + [Command.create({'gun': str(g), 'bas_saat': b, 'bit_saat': s})
                                               for g in range(1, 6) for b, s in ((9.0, 12.0), (13.0, 18.0))]
        return True


class AtlasRandevuSlot(models.Model):
    _name = 'atlas.randevu.slot'
    _description = 'Randevu Müsaitlik Dilimi'
    _order = 'gun, bas_saat, bas_zaman'

    tur_id = fields.Many2one('atlas.randevu.tur', string='Randevu Türü', required=True, ondelete='cascade', index=True)
    tip = fields.Selection([('haftalik', 'Haftalık'), ('tek', 'Belirli zaman')], string='Tip', default='haftalik', required=True)
    gun = fields.Selection(GUNLER, string='Gün', default='1')
    bas_saat = fields.Float(string='Başlangıç', default=9.0)
    bit_saat = fields.Float(string='Bitiş', default=17.0)
    bas_zaman = fields.Datetime(string='Başlangıç Zamanı')
    bit_zaman = fields.Datetime(string='Bitiş Zamanı')

    @api.constrains('tip', 'bas_saat', 'bit_saat', 'bas_zaman', 'bit_zaman', 'gun')
    def _check_saat(self):
        for s in self:
            if s.tip == 'haftalik':
                if not s.gun or not (0 <= s.bas_saat < 24) or not (0 < s.bit_saat <= 24) or s.bas_saat >= s.bit_saat:
                    raise ValidationError(self.env._('Dilim saatleri hatalı: başlangıç bitişten önce ve 0-24 arasında olmalı.'))
            elif not s.bas_zaman or not s.bit_zaman or s.bas_zaman >= s.bit_zaman:
                raise ValidationError(self.env._('Belirli zaman diliminde başlangıç bitişten önce olmalı.'))


class AtlasRandevuKaynak(models.Model):
    _name = 'atlas.randevu.kaynak'
    _description = 'Randevu Kaynağı'
    _order = 'sira, id'

    name = fields.Char(string='Ad', required=True)
    active = fields.Boolean(default=True)
    sira = fields.Integer(string='Sıra', default=10)
    kapasite = fields.Integer(string='Kapasite', default=1, required=True)
    aciklama = fields.Html(string='Açıklama')
    resim = fields.Image(string='Görsel', max_width=512, max_height=512)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    tur_ids = fields.Many2many('atlas.randevu.tur', string='Randevu Türleri')

    @api.constrains('kapasite')
    def _check_kapasite(self):
        if any(k.kapasite < 1 for k in self):
            raise ValidationError(self.env._('Kapasite en az 1 olmalı.'))


class AtlasRandevuSoru(models.Model):
    _name = 'atlas.randevu.soru'
    _description = 'Randevu Sorusu'
    _order = 'sira, id'

    name = fields.Char(string='Soru', required=True, translate=True)
    sira = fields.Integer(string='Sıra', default=10)
    tip = fields.Selection(SORU_TIPLERI, string='Tip', default='char', required=True)
    zorunlu = fields.Boolean(string='Zorunlu')
    yer_tutucu = fields.Char(string='Yer Tutucu', translate=True)
    secenek_ids = fields.One2many('atlas.randevu.secenek', 'soru_id', string='Seçenekler', copy=True)
    tur_ids = fields.Many2many('atlas.randevu.tur', string='Randevu Türleri')


class AtlasRandevuSecenek(models.Model):
    _name = 'atlas.randevu.secenek'
    _description = 'Randevu Sorusu Seçeneği'
    _order = 'sira, id'

    soru_id = fields.Many2one('atlas.randevu.soru', string='Soru', required=True, ondelete='cascade')
    name = fields.Char(string='Seçenek', required=True, translate=True)
    sira = fields.Integer(string='Sıra', default=10)


class AtlasRandevuYanit(models.Model):
    _name = 'atlas.randevu.yanit'
    _description = 'Randevu Yanıtı'
    _order = 'etkinlik_id, soru_id, id'

    etkinlik_id = fields.Many2one('calendar.event', string='Randevu', required=True, ondelete='cascade', index=True)
    soru_id = fields.Many2one('atlas.randevu.soru', string='Soru', required=True, ondelete='cascade')
    secenek_id = fields.Many2one('atlas.randevu.secenek', string='Seçenek', ondelete='cascade')
    metin = fields.Text(string='Yanıt')
    partner_id = fields.Many2one('res.partner', string='Müşteri')
    tur_id = fields.Many2one(related='etkinlik_id.randevu_tur_id', store=True, string='Randevu Türü')


class AtlasRandevuRezervasyon(models.Model):
    _name = 'atlas.randevu.rezervasyon'
    _description = 'Randevu Kaynak Rezervasyonu'
    _order = 'bas'

    etkinlik_id = fields.Many2one('calendar.event', string='Randevu', required=True, ondelete='cascade', index=True)
    kaynak_id = fields.Many2one('atlas.randevu.kaynak', string='Kaynak', required=True, ondelete='cascade', index=True)
    bas = fields.Datetime(string='Başlangıç', required=True, index=True)
    bit = fields.Datetime(string='Bitiş', required=True, index=True)
    kapasite = fields.Integer(string='Kişi', default=1)


class AtlasRandevuDavet(models.Model):
    """Paylaşılabilir randevu bağlantısı (belirli türler, personel ya da kaynaklarla sınırlı)."""
    _name = 'atlas.randevu.davet'
    _description = 'Randevu Davet Bağlantısı'
    _order = 'id desc'

    name = fields.Char(string='Ad', compute='_compute_name', store=True, readonly=False)
    erisim_anahtari = fields.Char(string='Anahtar', required=True, copy=False, default=lambda self: secrets.token_urlsafe(16), index=True)
    kisa_kod = fields.Char(string='Kısa Kod', copy=False, help='Bağlantıda anahtar yerine kullanılabilir, ör. satis-ekibi')
    tur_ids = fields.Many2many('atlas.randevu.tur', string='Randevu Türleri', required=True)
    personel_ids = fields.Many2many('res.users', string='Personel', domain=[('share', '=', False)],
                                    help='Boşsa türdeki tüm personel')
    kaynak_ids = fields.Many2many('atlas.randevu.kaynak', string='Kaynaklar', help='Boşsa türdeki tüm kaynaklar')
    url = fields.Char(string='Bağlantı', compute='_compute_url')
    etkinlik_ids = fields.One2many('calendar.event', 'randevu_davet_id', string='Randevular')
    etkinlik_sayisi = fields.Integer(string='Randevu Sayısı', compute='_compute_etkinlik_sayisi')

    _kisa_kod_benzersiz = models.Constraint('UNIQUE(kisa_kod)', 'Kısa kod benzersiz olmalı.')

    @api.depends('tur_ids')
    def _compute_name(self):
        for d in self:
            if not d.name:
                d.name = ', '.join(d.tur_ids.mapped('name'))

    @api.depends('erisim_anahtari', 'kisa_kod')
    def _compute_url(self):
        taban = self.env['ir.config_parameter'].sudo().get_str('web.base.url') or ''
        for d in self:
            d.url = f'{taban}/randevu/davet/{d.kisa_kod or d.erisim_anahtari}'

    @api.depends('etkinlik_ids')
    def _compute_etkinlik_sayisi(self):
        for d in self:
            d.etkinlik_sayisi = len(d.etkinlik_ids)

    @api.constrains('kisa_kod')
    def _check_kisa_kod(self):
        for d in self:
            if d.kisa_kod and not all(c.isalnum() or c in '-_' for c in d.kisa_kod):
                raise ValidationError(self.env._('Kısa kod yalnız harf, rakam, - ve _ içerebilir.'))

    @api.model
    def _bul(self, kod):
        return self.sudo().search(['|', ('erisim_anahtari', '=', kod), ('kisa_kod', '=', kod)], limit=1)
