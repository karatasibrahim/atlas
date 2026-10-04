import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount

_logger = logging.getLogger(__name__)

GRAPH_URL = 'https://graph.facebook.com'
OTURUM_SURESI = timedelta(hours=24)  # serbest metin yalnız son gelen mesajdan sonraki 24 saatte gönderilebilir
MESAJ_DURUMLARI = [
    ('kuyrukta', 'Kuyrukta'),
    ('gonderildi', 'Gönderildi'),
    ('iletildi', 'İletildi'),
    ('okundu', 'Okundu'),
    ('alindi', 'Alındı'),
    ('hata', 'Hata'),
]
WA_DURUM = {'sent': 'gonderildi', 'delivered': 'iletildi', 'read': 'okundu', 'failed': 'hata'}
DURUM_SIRASI = {'kuyrukta': 0, 'gonderildi': 1, 'iletildi': 2, 'okundu': 3}


def telefon_normalize(numara, ulke_kodu=90):
    """WhatsApp için yalnız rakamlardan oluşan uluslararası numara: '0532 111 22 33' → '905321112233'."""
    rakam = re.sub(r'\D', '', numara or '')
    if not rakam:
        return ''
    if rakam.startswith('00'):
        return rakam[2:]
    if (numara or '').strip().startswith('+'):
        return rakam
    if rakam.startswith('0'):
        return f'{ulke_kodu}{rakam[1:]}'
    if ulke_kodu == 90 and len(rakam) == 10 and rakam.startswith('5'):
        return f'90{rakam}'
    return rakam


class AtlasWhatsappHesap(models.Model):
    _name = 'atlas.whatsapp.hesap'
    _description = 'WhatsApp Business Hesabı'

    name = fields.Char(string='Hesap', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    telefon_no_id = fields.Char(string='Phone Number ID', required=True, help='Meta Business > WhatsApp > API Setup ekranındaki numara kimliği.')
    waba_id = fields.Char(string='WhatsApp Business Account ID', required=True)
    erisim_anahtari = fields.Char(string='Erişim Anahtarı (Token)', required=True, groups='base.group_system',
                                  help='Kalıcı sistem kullanıcısı erişim anahtarı önerilir.')
    uygulama_sirri = fields.Char(string='Uygulama Gizli Anahtarı', groups='base.group_system',
                                 help='Webhook imzasını (X-Hub-Signature-256) doğrulamak için.')
    dogrulama_anahtari = fields.Char(string='Webhook Doğrulama Anahtarı', required=True, copy=False, groups='base.group_system',
                                     default=lambda self: secrets.token_urlsafe(24))
    api_surumu = fields.Char(string='API Sürümü', default='v21.0', required=True)
    gorunen_numara = fields.Char(string='Numara')
    webhook_url = fields.Char(string='Webhook Adresi', compute='_compute_webhook_url')
    sablon_ids = fields.One2many('atlas.whatsapp.sablon', 'hesap_id', string='Şablonlar')

    def _compute_webhook_url(self):
        for h in self:
            h.webhook_url = f'{h.get_base_url()}/whatsapp/webhook/{h.id}' if h.id else ''

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------

    def _api(self, yontem, yol, veri=None, params=None):
        self.ensure_one()
        hesap = self.sudo()
        url = f'{GRAPH_URL}/{hesap.api_surumu}/{yol}'
        basliklar = {'Authorization': f'Bearer {hesap.erisim_anahtari}'}
        try:
            yanit = requests.request(yontem, url, headers=basliklar, json=veri, params=params, timeout=20)
        except requests.RequestException as hata:
            raise UserError(self.env._('WhatsApp sunucusuna bağlanılamadı: %s', hata)) from hata
        try:
            icerik = yanit.json()
        except ValueError:
            icerik = {}
        if yanit.status_code >= 400 or 'error' in icerik:
            hata = icerik.get('error', {})
            raise UserError(self.env._('WhatsApp API hatası (%(kod)s): %(mesaj)s',
                                       kod=hata.get('code', yanit.status_code), mesaj=hata.get('message') or yanit.text[:300]))
        return icerik

    def action_baglanti_test(self):
        self.ensure_one()
        bilgi = self._api('GET', self.telefon_no_id, params={'fields': 'display_phone_number,verified_name,quality_rating'})
        self.gorunen_numara = bilgi.get('display_phone_number')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'title': self.env._('Bağlantı başarılı'),
                           'message': f"{bilgi.get('verified_name', '')} {bilgi.get('display_phone_number', '')} "
                                      f"({self.env._('kalite')}: {bilgi.get('quality_rating', '-')})"}}

    def action_sablon_senkron(self):
        """Meta'daki onaylı/bekleyen şablonları içe aktarır."""
        Sablon = self.env['atlas.whatsapp.sablon']
        for hesap in self:
            yanit = hesap._api('GET', f'{hesap.waba_id}/message_templates', params={'limit': 200})
            for veri in yanit.get('data', []):
                govde = next((c.get('text', '') for c in veri.get('components', []) if c.get('type') == 'BODY'), '')
                baslik = next((c.get('text', '') for c in veri.get('components', [])
                               if c.get('type') == 'HEADER' and c.get('format') == 'TEXT'), '')
                durum = {'APPROVED': 'onaylandi', 'PENDING': 'bekliyor', 'REJECTED': 'reddedildi'}.get(veri.get('status'), 'bekliyor')
                mevcut = Sablon.search([('hesap_id', '=', hesap.id), ('wa_adi', '=', veri['name']),
                                        ('dil', '=', veri.get('language', 'tr'))], limit=1)
                vals = {'govde': govde, 'baslik': baslik or False, 'durum': durum,
                        'kategori': (veri.get('category') or 'UTILITY').lower(), 'wa_id': veri.get('id')}
                if mevcut:
                    mevcut.write(vals)
                else:
                    Sablon.create(dict(vals, hesap_id=hesap.id, name=veri['name'], wa_adi=veri['name'], dil=veri.get('language', 'tr')))
        return True

    def _mesaj_gonder(self, telefon, govde_json):
        self.ensure_one()
        veri = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': telefon, **govde_json}
        yanit = self._api('POST', f'{self.telefon_no_id}/messages', veri=veri)
        return (yanit.get('messages') or [{}])[0].get('id')

    # -------------------------------------------------------------------------
    # Webhook
    # -------------------------------------------------------------------------

    def _imza_dogrula(self, govde_bytes, imza):
        self.ensure_one()
        sir = self.sudo().uygulama_sirri
        if not sir:
            return True  # gizli anahtar girilmemişse imza doğrulanamaz (kurulum aşaması)
        beklenen = 'sha256=' + hmac.new(sir.encode(), govde_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(beklenen, imza or '')

    def _webhook_isle(self, veri):
        self.ensure_one()
        Mesaj = self.env['atlas.whatsapp.mesaj'].sudo()
        for giris in veri.get('entry', []):
            for degisiklik in giris.get('changes', []):
                deger = degisiklik.get('value', {})
                if deger.get('metadata', {}).get('phone_number_id') not in (None, self.telefon_no_id):
                    continue
                for durum in deger.get('statuses', []):
                    Mesaj._durum_guncelle(durum)
                kisiler = {k.get('wa_id'): k.get('profile', {}).get('name') for k in deger.get('contacts', [])}
                for mesaj in deger.get('messages', []):
                    Mesaj._gelen_kaydet(self, mesaj, kisiler.get(mesaj.get('from')))


class AtlasWhatsappSablon(models.Model):
    _name = 'atlas.whatsapp.sablon'
    _description = 'WhatsApp Mesaj Şablonu'
    _order = 'name'

    name = fields.Char(string='Ad', required=True)
    hesap_id = fields.Many2one('atlas.whatsapp.hesap', string='Hesap', required=True, ondelete='cascade')
    wa_adi = fields.Char(string='Meta Şablon Adı', required=True, help='Meta\'da onaylanan şablonun adı (küçük harf, alt çizgi).')
    wa_id = fields.Char(string='Meta Kimliği', readonly=True)
    dil = fields.Char(string='Dil', default='tr', required=True)
    kategori = fields.Selection([('utility', 'Hizmet'), ('marketing', 'Pazarlama'), ('authentication', 'Doğrulama')],
                                default='utility', string='Kategori')
    durum = fields.Selection([('bekliyor', 'Onay Bekliyor'), ('onaylandi', 'Onaylandı'), ('reddedildi', 'Reddedildi')],
                             string='Durum', default='bekliyor')
    baslik = fields.Char(string='Başlık')
    govde = fields.Text(string='Gövde', required=True, help='Meta\'daki gövde metni; değişkenler {{1}}, {{2}} …')
    model_id = fields.Many2one('ir.model', string='Uygulandığı Model', ondelete='cascade',
                               help='Değişkenlerin okunacağı kayıt türü (ör. Satış Siparişi).')
    model_name = fields.Char(related='model_id.model', string='Model Adı')
    telefon_alani = fields.Char(string='Telefon Alanı', default='partner_id',
                                help='Kayıttaki iş ortağı alanı (ör. partner_id) ya da telefon alanı (ör. phone).')
    degisken_ids = fields.One2many('atlas.whatsapp.sablon.degisken', 'sablon_id', string='Değişkenler')

    @api.constrains('govde', 'degisken_ids')
    def _check_degiskenler(self):
        for s in self:
            sayilar = {int(n) for n in re.findall(r'\{\{(\d+)\}\}', s.govde or '')}
            tanimli = set(s.degisken_ids.mapped('sira'))
            eksik = sayilar - tanimli
            if s.model_id and eksik:
                raise ValidationError(self.env._('%(sablon)s: {{%(no)s}} değişkeni için alan tanımlayın.',
                                                 sablon=s.name, no=min(eksik)))

    def _degerler(self, kayit):
        self.ensure_one()
        degerler = []
        for d in self.degisken_ids.sorted('sira'):
            deger = d._oku(kayit) if kayit else (d.sabit or '')
            degerler.append(str(deger if deger not in (False, None) else ''))
        return degerler

    def _onizleme(self, kayit):
        self.ensure_one()
        metin = self.govde or ''
        for sira, deger in enumerate(self._degerler(kayit), start=1):
            metin = metin.replace('{{%d}}' % sira, deger)
        return metin

    def _api_govdesi(self, kayit):
        self.ensure_one()
        parametreler = [{'type': 'text', 'text': deger or '-'} for deger in self._degerler(kayit)]
        sablon = {'name': self.wa_adi, 'language': {'code': self.dil}}
        if parametreler:
            sablon['components'] = [{'type': 'body', 'parameters': parametreler}]
        return {'type': 'template', 'template': sablon}


class AtlasWhatsappSablonDegisken(models.Model):
    _name = 'atlas.whatsapp.sablon.degisken'
    _description = 'WhatsApp Şablon Değişkeni'
    _order = 'sira'

    sablon_id = fields.Many2one('atlas.whatsapp.sablon', required=True, ondelete='cascade')
    sira = fields.Integer(string='No', required=True, help='{{1}} için 1')
    alan_yolu = fields.Char(string='Alan', help='Kayıttaki alan yolu, ör. partner_id.name, amount_total, name')
    sabit = fields.Char(string='Sabit Değer', help='Alan yoksa kullanılacak değer')

    def _oku(self, kayit):
        self.ensure_one()
        sablon_modeli = self.sablon_id.model_id.model
        if sablon_modeli and kayit._name != sablon_modeli:
            raise UserError(self.env._('%(sablon)s şablonu yalnız %(model)s kayıtlarından gönderilebilir.',
                                       sablon=self.sablon_id.name, model=self.sablon_id.model_id.name))
        if not self.alan_yolu:
            return self.sabit or ''
        deger = kayit
        for parca in self.alan_yolu.split('.'):
            if parca not in deger._fields:
                raise UserError(self.env._('"%(alan)s" alanı %(model)s modelinde yok.', alan=self.alan_yolu, model=kayit._name))
            alan = deger._fields[parca]
            deger = deger[parca]
            if alan.type == 'monetary' and 'currency_id' in kayit._fields:
                return format_amount(self.env, deger, kayit.currency_id)
            if isinstance(deger, models.BaseModel):
                deger = deger[:1]
                if not deger:
                    return self.sabit or ''
        if isinstance(deger, models.BaseModel):
            return deger.display_name
        if isinstance(deger, float):
            return f'{deger:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        if hasattr(deger, 'strftime'):
            return deger.strftime('%d.%m.%Y')
        return deger if deger not in (False, None) else (self.sabit or '')


class AtlasWhatsappMesaj(models.Model):
    _name = 'atlas.whatsapp.mesaj'
    _description = 'WhatsApp Mesajı'
    _order = 'id desc'

    hesap_id = fields.Many2one('atlas.whatsapp.hesap', string='Hesap', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Kişi', index=True)
    telefon = fields.Char(string='Telefon', required=True, index=True)
    yon = fields.Selection([('giden', 'Giden'), ('gelen', 'Gelen')], string='Yön', required=True, default='giden')
    tur = fields.Selection([('sablon', 'Şablon'), ('metin', 'Metin'), ('diger', 'Diğer')], string='Tür', default='metin')
    sablon_id = fields.Many2one('atlas.whatsapp.sablon', string='Şablon')
    govde = fields.Text(string='Mesaj')
    durum = fields.Selection(MESAJ_DURUMLARI, string='Durum', default='kuyrukta', required=True, index=True)
    hata = fields.Char(string='Hata')
    wa_mesaj_id = fields.Char(string='WhatsApp Mesaj Kimliği', index=True, copy=False)
    res_model = fields.Char(string='İlgili Model', index=True)
    res_id = fields.Many2oneReference(string='İlgili Kayıt', model_field='res_model')
    kullanici_id = fields.Many2one('res.users', string='Gönderen', default=lambda self: self.env.user)

    _wa_uniq = models.UniqueIndex('(wa_mesaj_id) WHERE wa_mesaj_id IS NOT NULL')

    def _ilgili_kayit(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            return self.env[self.res_model].browse(self.res_id).exists()
        return None

    def _gonder(self):
        for mesaj in self.filtered(lambda m: m.yon == 'giden' and m.durum in ('kuyrukta', 'hata')):
            kayit = mesaj._ilgili_kayit()
            if mesaj.tur == 'sablon':
                govde_json = mesaj.sablon_id._api_govdesi(kayit)
            else:
                govde_json = {'type': 'text', 'text': {'preview_url': True, 'body': mesaj.govde}}
            try:
                wa_id = mesaj.hesap_id._mesaj_gonder(mesaj.telefon, govde_json)
                mesaj.write({'durum': 'gonderildi', 'wa_mesaj_id': wa_id, 'hata': False})
            except UserError as hata:
                mesaj.write({'durum': 'hata', 'hata': str(hata)[:300]})
            mesaj._sohbete_yaz()

    def _sohbete_yaz(self):
        """Mesajı ilgili kaydın (yoksa kişinin) yazışmasına not olarak ekler."""
        for mesaj in self:
            hedef = mesaj._ilgili_kayit() or mesaj.partner_id
            if not hedef or not hasattr(hedef, 'message_post'):
                continue
            ok = '⬅' if mesaj.yon == 'gelen' else '➡'
            durum = '' if mesaj.durum not in ('hata',) else f" — {self.env._('Hata')}: {mesaj.hata}"
            hedef.sudo().message_post(
                body=self.env._('%(ok)s WhatsApp (%(tel)s): %(metin)s%(durum)s', ok=ok, tel=mesaj.telefon, metin=mesaj.govde or '', durum=durum),
                subtype_xmlid='mail.mt_note', author_id=(mesaj.partner_id.id if mesaj.yon == 'gelen' else mesaj.kullanici_id.partner_id.id) or None)

    @api.model
    def _durum_guncelle(self, veri):
        mesaj = self.search([('wa_mesaj_id', '=', veri.get('id'))], limit=1)
        yeni = WA_DURUM.get(veri.get('status'))
        if not mesaj or not yeni:
            return
        if yeni == 'hata':
            hata = (veri.get('errors') or [{}])[0]
            mesaj.write({'durum': 'hata', 'hata': f"{hata.get('code', '')} {hata.get('title', '')}".strip()})
        elif DURUM_SIRASI.get(yeni, 0) > DURUM_SIRASI.get(mesaj.durum, -1):
            mesaj.durum = yeni  # durumlar geri gitmez (okundu → iletildi gelmez)

    @api.model
    def _gelen_kaydet(self, hesap, veri, profil_adi=None):
        if veri.get('id') and self.search_count([('wa_mesaj_id', '=', veri['id'])]):
            return self.browse()  # aynı webhook tekrar geldi
        telefon = veri.get('from', '')
        tur = veri.get('type')
        if tur == 'text':
            metin = veri.get('text', {}).get('body', '')
        elif tur in ('button', 'interactive'):
            metin = (veri.get('button', {}).get('text') or veri.get('interactive', {}).get('button_reply', {}).get('title')
                     or veri.get('interactive', {}).get('list_reply', {}).get('title') or '')
        else:
            metin = f'[{tur}]'
        partner = self.env['res.partner']._atlas_whatsapp_bul(telefon)
        if not partner:
            partner = self.env['res.partner'].sudo().create({'name': profil_adi or f'+{telefon}', 'phone': f'+{telefon}'})
        # yanıt verilen giden mesajın kaydına bağla
        ilgili = self.search([('telefon', '=', telefon), ('yon', '=', 'giden'), ('res_model', '!=', False)], limit=1)
        mesaj = self.create({
            'hesap_id': hesap.id, 'partner_id': partner.id, 'telefon': telefon, 'yon': 'gelen',
            'tur': 'metin' if tur == 'text' else 'diger', 'govde': metin, 'durum': 'alindi', 'wa_mesaj_id': veri.get('id'),
            'res_model': ilgili.res_model or False, 'res_id': ilgili.res_id or False, 'kullanici_id': False,
        })
        partner.sudo().atlas_whatsapp_son_gelen = fields.Datetime.now()
        mesaj._sohbete_yaz()
        kayit = mesaj._ilgili_kayit()
        adaylar = [ilgili.kullanici_id, kayit.user_id if kayit and 'user_id' in kayit._fields else None, partner.user_id]
        sorumlu = next((u for u in adaylar if u and u.active and not u.share), None)
        if sorumlu:
            (mesaj._ilgili_kayit() or partner).sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=sorumlu.id,
                summary=self.env._('WhatsApp mesajı: %s', (metin or '')[:60]))
        return mesaj

    def action_yanitla(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.whatsapp.gonder', 'view_mode': 'form', 'target': 'new',
                'context': {'default_partner_id': self.partner_id.id, 'default_telefon': self.telefon,
                            'default_hesap_id': self.hesap_id.id, 'default_res_model': self.res_model, 'default_res_id': self.res_id}}

    def action_tekrar_gonder(self):
        self._gonder()
        return True


class ResPartner(models.Model):
    _inherit = 'res.partner'

    atlas_whatsapp_son_gelen = fields.Datetime(string='Son WhatsApp Mesajı', readonly=True, copy=False)
    atlas_whatsapp_mesaj_ids = fields.One2many('atlas.whatsapp.mesaj', 'partner_id', string='WhatsApp Mesajları')

    @api.model
    def _atlas_whatsapp_bul(self, telefon):
        """Gelen numarayı kayıtlı (biçimi farklı olabilen) telefonlarla eşleştirir."""
        if not telefon or len(telefon) < 7:
            return self.browse()
        sutunlar = ['phone'] + (['mobile'] if 'mobile' in self._fields and self._fields['mobile'].store else [])
        kosul = ' OR '.join(f"regexp_replace(coalesce({s}, ''), '\\D', '', 'g') LIKE %s" for s in sutunlar)
        self.env.cr.execute(f'SELECT id FROM res_partner WHERE active AND ({kosul}) ORDER BY id LIMIT 50',
                            ['%' + telefon[-9:]] * len(sutunlar))
        for p in self.sudo().browse([r[0] for r in self.env.cr.fetchall()]):
            for s in sutunlar:
                if p[s] and telefon_normalize(p[s], p.country_id.phone_code or 90) == telefon:
                    return p
        return self.browse()

    def _atlas_whatsapp_telefon(self):
        self.ensure_one()
        numara = (self.mobile if 'mobile' in self._fields else False) or self.phone
        return telefon_normalize(numara, self.country_id.phone_code or 90)

    def _atlas_whatsapp_oturum_acik(self):
        self.ensure_one()
        return bool(self.atlas_whatsapp_son_gelen) and fields.Datetime.now() - self.atlas_whatsapp_son_gelen < OTURUM_SURESI

    def action_atlas_whatsapp(self):
        return self.env['atlas.whatsapp.gonder']._ac(self)


class AtlasWhatsappGonder(models.TransientModel):
    _name = 'atlas.whatsapp.gonder'
    _description = 'WhatsApp Gönder'

    hesap_id = fields.Many2one('atlas.whatsapp.hesap', string='Hesap', required=True,
                               default=lambda self: self.env['atlas.whatsapp.hesap'].search([], limit=1))
    res_model = fields.Char()
    res_id = fields.Integer()
    partner_id = fields.Many2one('res.partner', string='Kişi')
    telefon = fields.Char(string='Telefon', required=True)
    oturum_acik = fields.Boolean(compute='_compute_oturum', string='24 Saatlik Oturum Açık')
    tur = fields.Selection([('sablon', 'Şablon'), ('metin', 'Serbest Metin')], string='Gönderim', default='sablon', required=True)
    sablon_id = fields.Many2one('atlas.whatsapp.sablon', string='Şablon',
                                domain="[('hesap_id', '=', hesap_id), ('durum', '=', 'onaylandi'), '|', ('model_name', '=', False), ('model_name', '=', res_model)]")
    metin = fields.Text(string='Mesaj')
    onizleme = fields.Text(string='Önizleme', compute='_compute_onizleme')

    @api.depends('partner_id')
    def _compute_oturum(self):
        for w in self:
            w.oturum_acik = bool(w.partner_id) and w.partner_id._atlas_whatsapp_oturum_acik()

    @api.depends('sablon_id', 'tur', 'metin')
    def _compute_onizleme(self):
        for w in self:
            if w.tur == 'sablon' and w.sablon_id:
                w.onizleme = w.sablon_id._onizleme(w._kayit())
            else:
                w.onizleme = w.metin or ''

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.telefon = self.partner_id._atlas_whatsapp_telefon()
            if self.partner_id._atlas_whatsapp_oturum_acik() and not self.sablon_id:
                self.tur = 'metin'

    def _kayit(self):
        if self.res_model and self.res_id and self.res_model in self.env:
            return self.env[self.res_model].browse(self.res_id).exists()
        return None

    @api.model
    def _ac(self, kayit):
        kayit.ensure_one()
        partner = kayit if kayit._name == 'res.partner' else (kayit.partner_id if 'partner_id' in kayit._fields else self.env['res.partner'])
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.whatsapp.gonder', 'view_mode': 'form', 'target': 'new',
                'name': self.env._('WhatsApp Gönder'),
                'context': {'default_res_model': kayit._name, 'default_res_id': kayit.id, 'default_partner_id': partner.id,
                            'default_telefon': partner._atlas_whatsapp_telefon() if partner else False}}

    def action_gonder(self):
        self.ensure_one()
        telefon = telefon_normalize(self.telefon, (self.partner_id.country_id.phone_code or 90) if self.partner_id else 90)
        if len(telefon) < 10:
            raise UserError(self.env._('Geçerli bir telefon numarası girin.'))
        if self.tur == 'metin':
            if not (self.metin or '').strip():
                raise UserError(self.env._('Mesaj yazın.'))
            if not self.oturum_acik:
                raise UserError(self.env._('Kişi son 24 saatte size yazmadığı için yalnız onaylı şablon gönderilebilir (WhatsApp kuralı).'))
        elif not self.sablon_id:
            raise UserError(self.env._('Bir şablon seçin.'))
        mesaj = self.env['atlas.whatsapp.mesaj'].create({
            'hesap_id': self.hesap_id.id, 'partner_id': self.partner_id.id, 'telefon': telefon, 'yon': 'giden',
            'tur': self.tur, 'sablon_id': self.sablon_id.id if self.tur == 'sablon' else False,
            'govde': self.onizleme, 'res_model': self.res_model or False, 'res_id': self.res_id or False,
        })
        mesaj._gonder()
        if mesaj.durum == 'hata':
            raise UserError(self.env._('Mesaj gönderilemedi: %s', mesaj.hata))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('WhatsApp mesajı gönderildi.'),
                           'next': {'type': 'ir.actions.act_window_close'}}}
