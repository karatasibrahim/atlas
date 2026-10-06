import json
from html import escape

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext


class AtlasBilgiYorum(models.Model):
    """Makale metnine bağlı yorum dizisi (Enterprise knowledge.article.thread eşleniği).

    Makalede seçilen metnin sonuna bir işaret (gömülü bileşen) konur; mesajlar bu kaydın chatter'ındadır.
    """
    _name = 'atlas.bilgi.yorum'
    _description = 'Bilgi Makalesi Yorumu'
    _inherit = ['mail.thread']
    _order = 'id desc'

    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade', index=True)
    metin = fields.Text(string='Yorumlanan Metin')
    cozuldu = fields.Boolean(string='Çözüldü', tracking=True)
    mesaj_sayisi = fields.Integer(string='Mesaj', compute='_compute_mesaj_sayisi')

    def _compute_mesaj_sayisi(self):
        for y in self:
            y.mesaj_sayisi = len(y.message_ids.filtered(lambda m: m.message_type == 'comment'))

    def _okuma_kontrol(self):
        # yorumlar sudo ile okunur; erişim, gerçek kullanıcının makaleye erişimiyle denetlenir
        self.makale_id.sudo(False).check_access('read')

    def _ozet(self):
        mesajlar = self.message_ids.filtered(lambda m: m.message_type == 'comment').sorted('id')
        return {'id': self.id, 'metin': self.metin or '', 'cozuldu': self.cozuldu,
                'mesajlar': [{'id': m.id, 'yazar': m.author_id.name or '', 'yazar_id': m.author_id.id,
                              'govde': html2plaintext(m.body or '').strip(), 'tarih': fields.Datetime.to_string(m.date)} for m in mesajlar]}


class AtlasBilgiBaglanti(models.Model):
    """Makale ↔ herhangi bir kayıt bağlantısı (kayıttan bilgi bankasına erişim)."""
    _name = 'atlas.bilgi.baglanti'
    _description = 'Bilgi Makalesi Kayıt Bağlantısı'
    _order = 'id desc'

    makale_id = fields.Many2one('atlas.bilgi.makale', string='Makale', required=True, ondelete='cascade', index=True)
    res_model = fields.Char(string='Model', required=True, index=True)
    res_id = fields.Integer(string='Kayıt', required=True, index=True)
    kayit_adi = fields.Char(string='Kayıt Adı')

    _baglanti_benzersiz = models.Constraint('UNIQUE(makale_id, res_model, res_id)', 'Makale bu kayda zaten bağlı.')

    def action_kayit(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}


class AtlasBilgiMakale(models.Model):
    _inherit = 'atlas.bilgi.makale'

    yorum_ids = fields.One2many('atlas.bilgi.yorum', 'makale_id', string='Yorumlar')
    baglanti_ids = fields.One2many('atlas.bilgi.baglanti', 'makale_id', string='Bağlı Kayıtlar')
    acik_yorum_sayisi = fields.Integer(string='Açık Yorum', compute='_compute_acik_yorum')

    @api.depends('yorum_ids.cozuldu')
    def _compute_acik_yorum(self):
        for m in self:
            m.acik_yorum_sayisi = len(m.yorum_ids.filtered(lambda y: not y.cozuldu))

    def _disa_govde(self, herkese_acik=False):
        """Gövdeyi dışarıda (mesaj, önizleme, paylaşım sayfası) gösterilecek hale getirir: yorum işaretleri çıkarılır,
        gömülü görünüm başlığa, alt sayfalar listesi makale adlarına çevrilir."""
        self.ensure_one()
        from lxml import html as lxml_html
        if not self.body:
            return Markup('')
        kok = lxml_html.fragment_fromstring(str(self.body), create_parent='div')
        for el in kok.xpath("//*[@data-embedded='atlasBilgiYorum']"):
            el.drop_tree()
        for el in kok.xpath("//*[@data-embedded='atlasBilgiGorunum']"):
            try:
                props = json.loads(el.get('data-embedded-props') or '{}')
            except ValueError:
                props = {}
            yeni = lxml_html.fragment_fromstring(f'<p><em>📋 {escape(props.get("ad") or self.env._("Gömülü görünüm"))}</em></p>')
            el.getparent().replace(el, yeni)
        for el in kok.xpath("//*[@data-embedded='atlasBilgiAltSayfalar']"):
            altlar = self.sudo().child_ids.filtered(lambda a: a.active and not a.oge_mi and (not herkese_acik or a.herkese_acik))
            if herkese_acik:
                ogeler = ''.join(f'<li><a href="/bilgi/paylas/{a.id}/{a.erisim_anahtari}">{escape(a.simge or "")} {escape(a.name)}</a></li>' for a in altlar)
            else:
                ogeler = ''.join(f'<li>{escape(a.simge or "")} {escape(a.name)}</li>' for a in altlar)
            el.getparent().replace(el, lxml_html.fragment_fromstring(f'<ul>{ogeler}</ul>' if ogeler else '<p></p>'))
        icerik = ''.join(lxml_html.tostring(c, encoding='unicode') for c in kok)
        return Markup((kok.text and escape(kok.text) or '') + icerik)

    # ------------------------------------------------------------------ gömülü görünümler
    @api.model
    def gorunum_secenekleri(self, arama=''):
        """Makaleye gömülebilecek menü eylemleri: [{eylem_id, yol, model, modlar}]."""
        Menu = self.env['ir.ui.menu']
        menuler = Menu.search([('action', '!=', False)], order='parent_path')
        arama = (arama or '').strip().lower()
        sonuc = []
        for m in menuler:
            # menü görünürlüğü kullanıcıya göre (search), eylem ayrıntısı sudo ile okunur; model okuma yetkisi ayrıca denetlenir
            eylem = m.sudo().action
            if eylem._name != 'ir.actions.act_window' or not eylem.res_model or eylem.res_model not in self.env:
                continue
            modlar = [v for v in (eylem.view_mode or '').split(',') if v in ('list', 'kanban')]
            if not modlar:
                continue
            yol = (m.sudo().complete_name or m.sudo().name).replace('/', '›')
            if arama and arama not in yol.lower():
                continue
            if not self.env[eylem.res_model].has_access('read'):
                continue
            sonuc.append({'eylem_id': eylem.id, 'yol': yol, 'ad': m.sudo().name, 'model': eylem.res_model, 'modlar': modlar})
            if len(sonuc) >= 40:
                break
        return sonuc

    @api.model
    def _gorunum_blogu(self, eylem_id, tur, ad, domain=None, context=None):
        props = {'eylem_id': int(eylem_id), 'tur': tur if tur in ('list', 'kanban') else 'list', 'ad': ad or ''}
        if domain:
            props['domain'] = domain if isinstance(domain, str) else json.dumps(domain)
        if context:
            props['context'] = {k: v for k, v in context.items() if k in ('group_by', 'search_default_filter')} if isinstance(context, dict) else {}
        return (f'<div data-embedded="atlasBilgiGorunum" data-oe-protected="true" contenteditable="false" '
                f'data-embedded-props="{escape(json.dumps(props))}"></div><p><br></p>')

    def gorunum_ekle(self, eylem_id, tur, ad, domain=None, context=None):
        """Listedeki / kanbandaki görünümü (filtreleriyle) makalenin sonuna gömer."""
        self.ensure_one()
        if self.kullanici_yetkisi != 'write' or self.kilitli:
            raise AccessError(self.env._('Bu makaleyi düzenleyemezsiniz.'))
        self.body = Markup(self.body or '') + Markup(self._gorunum_blogu(eylem_id, tur, ad, domain, context))
        return self.action_ac()

    @api.model
    def gorunum_bilgisi(self, eylem_id):
        eylem = self.env['ir.actions.act_window'].sudo().browse(int(eylem_id)).exists()
        if not eylem or not eylem.res_model or not self.env[eylem.res_model].has_access('read'):
            return False
        return {'ad': eylem.name, 'model': eylem.res_model}

    @api.model
    def makale_ara_baglanti(self, metin):
        return self.ara(metin, limit=10)

    # ------------------------------------------------------------------ yorumlar
    def yorum_olustur(self, metin, ilk_mesaj):
        self.ensure_one()
        self.check_access('read')
        if not (ilk_mesaj or '').strip():
            raise UserError(self.env._('Yorum boş olamaz.'))
        yorum = self.env['atlas.bilgi.yorum'].sudo().create({'makale_id': self.id, 'metin': (metin or '')[:2000]})
        yorum.with_user(self.env.user).sudo().message_post(body=ilk_mesaj, message_type='comment', subtype_xmlid='mail.mt_comment',
                                                           author_id=self.env.user.partner_id.id)
        return yorum._ozet()

    @api.model
    def yorum_getir(self, yorum_id):
        yorum = self.env['atlas.bilgi.yorum'].sudo().browse(int(yorum_id)).exists()
        if not yorum:
            return False
        yorum._okuma_kontrol()
        return yorum._ozet()

    @api.model
    def yorum_yanitla(self, yorum_id, mesaj):
        yorum = self.env['atlas.bilgi.yorum'].sudo().browse(int(yorum_id))
        yorum._okuma_kontrol()
        if (mesaj or '').strip():
            yorum.message_post(body=mesaj, message_type='comment', subtype_xmlid='mail.mt_comment', author_id=self.env.user.partner_id.id)
            # makaleyi düzenleyenlere bildirim: son düzenleyen ve yorumu başlatan
            ilgililer = (yorum.makale_id.son_duzenleyen_id.partner_id | yorum.message_ids.author_id) - self.env.user.partner_id
            if ilgililer:
                yorum.makale_id.sudo().message_post(
                    body=self.env._('"%(metin)s" yorumuna yanıt: %(mesaj)s', metin=(yorum.metin or '')[:80], mesaj=mesaj),
                    partner_ids=ilgililer.ids, message_type='comment', subtype_xmlid='mail.mt_note')
        return yorum._ozet()

    @api.model
    def yorum_coz(self, yorum_id, cozuldu=True):
        yorum = self.env['atlas.bilgi.yorum'].sudo().browse(int(yorum_id))
        yorum._okuma_kontrol()
        yorum.cozuldu = cozuldu
        return yorum._ozet()

    def yorumlar(self):
        self.ensure_one()
        self.check_access('read')
        return [y._ozet() for y in self.sudo().yorum_ids]

    # ------------------------------------------------------------------ kayıtlardan bilgi bankası
    @api.model
    def kayit_makaleleri(self, res_model, res_id):
        baglantilar = self.env['atlas.bilgi.baglanti'].search([('res_model', '=', res_model), ('res_id', '=', int(res_id))])
        return [{'id': b.makale_id.id, 'ad': b.makale_id.name, 'simge': b.makale_id.simge or '📄', 'baglanti_id': b.id}
                for b in baglantilar if b.makale_id.active]

    def makale_onizleme(self):
        self.ensure_one()
        return {'id': self.id, 'ad': self.name, 'simge': self.simge or '📄', 'govde': str(self._disa_govde()),
                'yol': ' / '.join(self._ust_zincir().mapped('name')[:-1])}

    def kayda_bagla(self, res_model, res_id):
        self.ensure_one()
        self.check_access('read')
        kayit = self.env[res_model].browse(int(res_id)).exists()
        kayit.check_access('read')
        Baglanti = self.env['atlas.bilgi.baglanti'].sudo()
        if not Baglanti.search_count([('makale_id', '=', self.id), ('res_model', '=', res_model), ('res_id', '=', kayit.id)]):
            Baglanti.create({'makale_id': self.id, 'res_model': res_model, 'res_id': kayit.id, 'kayit_adi': kayit.display_name})
        return True

    @api.model
    def baglanti_kaldir(self, baglanti_id):
        b = self.env['atlas.bilgi.baglanti'].sudo().browse(int(baglanti_id))
        # kaydı ya da makaleyi düzenleyebilen bağlantıyı kaldırabilir
        if not self.env[b.res_model].browse(b.res_id).has_access('write') and b.makale_id.sudo(False).kullanici_yetkisi != 'write':
            raise AccessError(self.env._('Bu bağlantıyı kaldırma yetkiniz yok.'))
        b.unlink()
        return True

    def kayda_gonder(self, res_model, res_id):
        """Makaleyi kaydın mesajlaşmasına mesaj olarak ekler (ör. müşteriye çözüm makalesi)."""
        self.ensure_one()
        self.check_access('read')
        kayit = self.env[res_model].browse(int(res_id)).exists()
        if not hasattr(kayit, 'message_post'):
            raise UserError(self.env._('Bu kayıtta mesajlaşma yok.'))
        kayit.check_access('read')
        kayit.message_post(body=Markup(f'<h4>{escape(self.simge or "")} {escape(self.name or "")}</h4>') + self._disa_govde(),
                           message_type='comment', subtype_xmlid='mail.mt_note')
        self.kayda_bagla(res_model, res_id)
        return True

    def baglanti_listesi(self):
        self.ensure_one()
        return [{'id': b.id, 'model': b.res_model, 'res_id': b.res_id, 'ad': b.kayit_adi or f'{b.res_model},{b.res_id}',
                 'model_adi': self.env['ir.model']._get(b.res_model).name} for b in self.sudo().baglanti_ids]
