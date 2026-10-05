import json
import logging
import re
import secrets

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CAGRI_DURUMLARI = [
    ('baslatildi', 'Başlatıldı'),
    ('caliyor', 'Çalıyor'),
    ('cevaplandi', 'Cevaplandı'),
    ('tamamlandi', 'Tamamlandı'),
    ('cevapsiz', 'Cevapsız'),
    ('hata', 'Hata'),
]
# Santralden gelen olay adları → iç olay
OLAYLAR = {
    'ringing': 'caliyor', 'ring': 'caliyor', 'caliyor': 'caliyor', 'incoming': 'caliyor', 'dial': 'caliyor',
    'answered': 'cevaplandi', 'answer': 'cevaplandi', 'cevaplandi': 'cevaplandi', 'bridge': 'cevaplandi',
    'hangup': 'kapandi', 'end': 'kapandi', 'completed': 'kapandi', 'kapandi': 'kapandi',
    'missed': 'cevapsiz', 'noanswer': 'cevapsiz', 'cevapsiz': 'cevapsiz', 'busy': 'cevapsiz',
}


def numara_normalize(numara, ulke_kodu=90):
    """Karşılaştırma için uluslararası rakam dizisi: '0532 111 22 33' → '905321112233'."""
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


class AtlasVoipSaglayici(models.Model):
    _name = 'atlas.voip.saglayici'
    _description = 'VoIP / Santral Bağlantısı'

    name = fields.Char(string='Ad', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)
    yontem = fields.Selection([('tel', 'Bilgisayardaki softphone (tel: bağlantısı)'), ('http', 'Santral API ile arama (click-to-call)')],
                              string='Arama Yöntemi', default='tel', required=True)
    url_sablonu = fields.Char(string='İstek Adresi',
                              help='Yer tutucular: {dahili} {numara} {numara_yerel} {numara_e164} {anahtar}. '
                                   'Ör. https://santral.ornek.com/originate?key={anahtar}&ext={dahili}&to={numara_yerel}')
    http_yontem = fields.Selection([('GET', 'GET'), ('POST', 'POST')], string='HTTP Yöntemi', default='GET')
    govde_sablonu = fields.Text(string='İstek Gövdesi (JSON)', help='POST için; aynı yer tutucular kullanılabilir.')
    basliklar = fields.Text(string='Ek Başlıklar (JSON)', help='Ör. {"Authorization": "Bearer {anahtar}"}')
    anahtar = fields.Char(string='API Anahtarı', groups='base.group_system')
    dis_hat_oneki = fields.Char(string='Dış Hat Öneki', help='Santral dışarı aramada bekliyorsa (ör. 0 veya 9).')
    olay_anahtari = fields.Char(string='Olay Anahtarı', required=True, copy=False, groups='base.group_system',
                                default=lambda self: secrets.token_urlsafe(24))
    olay_url = fields.Char(string='Olay (Webhook) Adresi', compute='_compute_olay_url', compute_sudo=True)

    def _compute_olay_url(self):
        for s in self:
            s.olay_url = f'{s.get_base_url()}/voip/olay/{s.olay_anahtari}' if s.olay_anahtari else ''

    def _yer_tutucular(self, numara, dahili):
        self.ensure_one()
        e164 = numara_normalize(numara)
        yerel = '0' + e164[2:] if e164.startswith('90') else '00' + e164
        return {'dahili': dahili or '', 'numara': (self.dis_hat_oneki or '') + yerel, 'numara_yerel': yerel,
                'numara_e164': '+' + e164, 'anahtar': self.sudo().anahtar or ''}

    @staticmethod
    def _doldur(metin, degerler):
        for k, v in degerler.items():
            metin = metin.replace('{%s}' % k, str(v))
        return metin

    def _ara(self, numara, dahili):
        """Santrale click-to-call isteği gönderir."""
        self.ensure_one()
        if not self.url_sablonu:
            raise UserError(self.env._('Santral istek adresi tanımlı değil.'))
        d = self._yer_tutucular(numara, dahili)
        url = self._doldur(self.url_sablonu, d)
        basliklar = json.loads(self._doldur(self.basliklar, d)) if self.basliklar else {}
        govde = json.loads(self._doldur(self.govde_sablonu, d)) if self.http_yontem == 'POST' and self.govde_sablonu else None
        try:
            yanit = requests.request(self.http_yontem, url, headers=basliklar, json=govde, timeout=15)
        except requests.RequestException as hata:
            raise UserError(self.env._('Santrale bağlanılamadı: %s', hata)) from hata
        if yanit.status_code >= 400:
            raise UserError(self.env._('Santral aramayı reddetti (%(kod)s): %(metin)s', kod=yanit.status_code, metin=yanit.text[:200]))
        return yanit.text[:200]

    @api.model
    def _aktif(self):
        return self.search([('company_id', 'in', (self.env.company.id, False))], limit=1)


class ResUsers(models.Model):
    _inherit = 'res.users'

    atlas_dahili = fields.Char(string='Santral Dahilisi', user_writeable=True,
                               help='Kullanıcının santraldeki dahili numarası (ör. 101).')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    atlas_cagri_ids = fields.One2many('atlas.voip.cagri', 'partner_id', string='Aramalar')
    atlas_cagri_sayisi = fields.Integer(compute='_compute_atlas_cagri_sayisi')

    def _compute_atlas_cagri_sayisi(self):
        # şirketin kişileriyle yapılan aramalar da sayılır
        for p in self:
            p.atlas_cagri_sayisi = self.env['atlas.voip.cagri'].search_count([('partner_id', 'child_of', p.id)]) if p.id else 0

    @api.model
    def _atlas_numara_bul(self, numara):
        e164 = numara_normalize(numara)
        if len(e164) < 7:
            return self.browse()
        sutunlar = ['phone'] + (['mobile'] if 'mobile' in self._fields and self._fields['mobile'].store else [])
        kosul = ' OR '.join(f"regexp_replace(coalesce({s}, ''), '\\D', '', 'g') LIKE %s" for s in sutunlar)
        self.env.cr.execute(f'SELECT id FROM res_partner WHERE active AND ({kosul}) ORDER BY is_company, id LIMIT 50',
                            ['%' + e164[-9:]] * len(sutunlar))
        for p in self.sudo().browse([r[0] for r in self.env.cr.fetchall()]):
            for s in sutunlar:
                if p[s] and numara_normalize(p[s], p.country_id.phone_code or 90) == e164:
                    return p
        return self.browse()

    def action_atlas_aramalar(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.voip.cagri', 'view_mode': 'list,form',
                'domain': [('partner_id', 'child_of', self.id)], 'name': self.env._('Aramalar')}


class AtlasVoipCagri(models.Model):
    _name = 'atlas.voip.cagri'
    _description = 'Telefon Görüşmesi'
    _order = 'baslangic desc, id desc'

    name = fields.Char(string='Görüşme', compute='_compute_name', store=True)
    yon = fields.Selection([('giden', 'Giden'), ('gelen', 'Gelen')], string='Yön', required=True, default='giden', index=True)
    numara = fields.Char(string='Numara', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Kişi', index=True)
    user_id = fields.Many2one('res.users', string='Kullanıcı', default=lambda self: self.env.user, index=True)
    dahili = fields.Char(string='Dahili')
    durum = fields.Selection(CAGRI_DURUMLARI, string='Durum', default='baslatildi', required=True, index=True)
    baslangic = fields.Datetime(string='Başlangıç', default=fields.Datetime.now, required=True)
    cevaplanma = fields.Datetime(string='Cevaplanma')
    bitis = fields.Datetime(string='Bitiş')
    sure = fields.Integer(string='Süre (sn)')
    sure_metin = fields.Char(string='Süre', compute='_compute_sure_metin')
    kayit_url = fields.Char(string='Ses Kaydı')
    santral_id = fields.Char(string='Santral Çağrı Kimliği', index=True, copy=False)
    notlar = fields.Text(string='Notlar')
    res_model = fields.Char(string='İlgili Model')
    res_id = fields.Many2oneReference(string='İlgili Kayıt', model_field='res_model')
    hata = fields.Char(string='Hata')

    @api.depends('yon', 'partner_id', 'numara')
    def _compute_name(self):
        for c in self:
            c.name = f"{'⬅' if c.yon == 'gelen' else '➡'} {c.partner_id.name or c.numara}"

    @api.depends('sure')
    def _compute_sure_metin(self):
        for c in self:
            c.sure_metin = f'{c.sure // 60}:{c.sure % 60:02d}' if c.sure else ''

    # -------------------------------------------------------------------------
    # Giden arama
    # -------------------------------------------------------------------------

    @api.model
    def atlas_ara(self, numara, res_model=None, res_id=None):
        """Telefon alanındaki arama düğmesinden çağrılır. {'yontem': 'tel'|'api'}"""
        if not numara:
            raise UserError(self.env._('Aranacak numara yok.'))
        partner = self.env['res.partner']
        if res_model == 'res.partner' and res_id:
            partner = partner.browse(res_id).exists()
        elif res_model and res_id and res_model in self.env:
            kayit = self.env[res_model].browse(res_id).exists()
            if kayit and 'partner_id' in kayit._fields:
                partner = kayit.partner_id
        partner = partner or self.env['res.partner']._atlas_numara_bul(numara)
        saglayici = self.env['atlas.voip.saglayici']._aktif()
        cagri = self.create({'yon': 'giden', 'numara': numara, 'partner_id': partner.id or False, 'dahili': self.env.user.atlas_dahili,
                             'res_model': res_model or False, 'res_id': res_id or False})
        if not saglayici or saglayici.yontem == 'tel':
            return {'yontem': 'tel', 'cagri_id': cagri.id}
        if not self.env.user.atlas_dahili:
            cagri.write({'durum': 'hata', 'hata': self.env._('Kullanıcının dahilisi tanımlı değil')})
            raise UserError(self.env._('Tercihlerinizde santral dahilinizi tanımlayın.'))
        try:
            saglayici._ara(numara, self.env.user.atlas_dahili)
        except UserError as hata:
            cagri.write({'durum': 'hata', 'hata': str(hata)[:200]})
            raise
        return {'yontem': 'api', 'cagri_id': cagri.id}

    # -------------------------------------------------------------------------
    # Santral olayları
    # -------------------------------------------------------------------------

    @api.model
    def _olay_isle(self, veri):
        """Santral olayını işler. Esnek alan adları: event/olay, call_id, from/caller, to/callee, extension, duration, recording."""
        al = lambda *anahtarlar: next((veri[a] for a in anahtarlar if veri.get(a) not in (None, '')), None)  # noqa: E731
        olay = OLAYLAR.get(str(al('event', 'olay', 'status', 'state') or '').lower())
        if not olay:
            return self.browse()
        santral_id = str(al('call_id', 'callid', 'uniqueid', 'cagri_id') or '')
        dahili = str(al('extension', 'dahili', 'agent', 'ext') or '')
        yon = 'giden' if str(al('direction', 'yon') or '').lower() in ('outbound', 'out', 'giden') else 'gelen'
        arayan = str(al('from', 'caller', 'caller_id', 'arayan', 'src') or '')
        aranan = str(al('to', 'callee', 'aranan', 'dst') or '')
        dis_numara = aranan if yon == 'giden' else arayan
        cagri = self.search([('santral_id', '=', santral_id)], limit=1) if santral_id else self.browse()
        kullanici = self.env['res.users'].sudo().search([('atlas_dahili', '=', dahili), ('share', '=', False)], limit=1) if dahili else \
            self.env['res.users']
        if not cagri and yon == 'giden' and dis_numara:
            # click-to-call ile başlatılan giden arama: son başlatılan kaydı santral kimliğiyle eşleştir
            cagri = self.search([('yon', '=', 'giden'), ('santral_id', '=', False), ('durum', '=', 'baslatildi'),
                                 ('user_id', '=', kullanici.id or False)], limit=1)
            if cagri and numara_normalize(cagri.numara)[-9:] != numara_normalize(dis_numara)[-9:]:
                cagri = self.browse()
        if not cagri:
            partner = self.env['res.partner']._atlas_numara_bul(dis_numara)
            cagri = self.sudo().create({'yon': yon, 'numara': dis_numara or '?', 'partner_id': partner.id or False,
                                        'user_id': kullanici.id or False, 'dahili': dahili or False, 'santral_id': santral_id or False,
                                        'durum': 'caliyor'})
        else:
            cagri = cagri.sudo()
            vals = {}
            if santral_id and not cagri.santral_id:
                vals['santral_id'] = santral_id
            if kullanici and not cagri.user_id:
                vals['user_id'] = kullanici.id
            if vals:
                cagri.write(vals)
        simdi = fields.Datetime.now()
        if olay == 'caliyor':
            if cagri.durum == 'baslatildi':
                cagri.durum = 'caliyor'
            if cagri.yon == 'gelen':
                cagri._ekrana_getir()
        elif olay == 'cevaplandi':
            cagri.write({'durum': 'cevaplandi', 'cevaplanma': simdi})
        elif olay in ('kapandi', 'cevapsiz'):
            sure = al('duration', 'billsec', 'sure')
            try:
                sure = int(float(sure)) if sure is not None else None
            except (TypeError, ValueError):
                sure = None
            cevaplandi = olay == 'kapandi' and (cagri.durum == 'cevaplandi' or (sure or 0) > 0)
            if sure is None and cagri.cevaplanma:
                sure = int((simdi - cagri.cevaplanma).total_seconds())
            cagri.write({'durum': 'tamamlandi' if cevaplandi else 'cevapsiz', 'bitis': simdi, 'sure': sure or 0,
                         'kayit_url': al('recording', 'recording_url', 'kayit', 'kayit_url') or cagri.kayit_url})
            cagri._sonuc_isle()
        return cagri

    def _ekrana_getir(self):
        """Gelen aramada ilgili kullanıcının (yoksa tüm iç kullanıcıların) ekranında bildirim açar."""
        for c in self:
            yuk = {'cagri_id': c.id, 'numara': c.numara, 'partner_id': c.partner_id.id or False,
                   'partner_ad': c.partner_id.display_name or '', 'sirket': c.partner_id.commercial_partner_id.name
                   if c.partner_id and c.partner_id.parent_id else ''}
            alicilar = c.user_id or self.env['res.users'].sudo().search(
                [('share', '=', False), ('group_ids', 'in', self.env.ref('base.group_user').id)])
            for kullanici in alicilar:
                kullanici._bus_send('atlas_voip/gelen', yuk)

    def _sonuc_isle(self):
        for c in self:
            hedef = c.partner_id
            if hedef:
                durum = dict(CAGRI_DURUMLARI)[c.durum]
                hedef.sudo().message_post(
                    body=self.env._('%(yon)s arama (%(numara)s) — %(durum)s%(sure)s', yon='Gelen' if c.yon == 'gelen' else 'Giden',
                                    numara=c.numara, durum=durum, sure=f', {c.sure_metin}' if c.sure else ''),
                    subtype_xmlid='mail.mt_note', author_id=(c.user_id.partner_id.id or None))
            if c.yon == 'gelen' and c.durum == 'cevapsiz':
                sorumlu = c.user_id or c.partner_id.user_id
                if sorumlu and c.partner_id:
                    c.partner_id.sudo().activity_schedule(
                        'mail.mail_activity_data_call', user_id=sorumlu.id,
                        summary=self.env._('Cevapsız arama: %s', c.partner_id.name or c.numara))
                if c.user_id:
                    c.user_id._bus_send('atlas_voip/cevapsiz', {'numara': c.numara, 'partner_ad': c.partner_id.display_name or ''})

    def action_kisi_olustur(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'res.partner', 'view_mode': 'form', 'target': 'current',
                'context': {'default_phone': self.numara}}

    def action_geri_ara(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'atlas_voip.ara', 'params': {'numara': self.numara,
                                                                               'res_model': 'res.partner', 'res_id': self.partner_id.id}}
