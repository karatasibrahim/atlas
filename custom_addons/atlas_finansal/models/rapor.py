import base64
import io

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

from ..services.motor import ISLEYICILER, Baglam

TURLER = [
    ('tanim', 'Satır tanımlı (Bilanço, Gelir Tablosu …)'), ('mizan', 'Mizan'), ('muavin', 'Büyük Defter'), ('cari', 'Cari Defter'),
    ('yaslandirma_alacak', 'Alacak Yaşlandırma'), ('yaslandirma_borc', 'Borç Yaşlandırma'), ('nakit_akis', 'Nakit Akış Tablosu'),
    ('kur_farki', 'Gerçekleşmemiş Kur Farkları'), ('banka', 'Banka Denkleştirme'), ('vergi', 'Vergi Raporu'),
    ('yevmiye', 'Yevmiye Raporu'), ('amortisman', 'Amortisman Tablosu'),
]


class AtlasFinansalRapor(models.Model):
    _name = 'atlas.finansal.rapor'
    _description = 'Finansal Rapor'
    _order = 'sira, id'

    name = fields.Char(string='Rapor', required=True, translate=True)
    sira = fields.Integer(default=10)
    tur = fields.Selection(TURLER, string='Tür', required=True, default='tanim')
    tarih_modu = fields.Selection([('aralik', 'Tarih aralığı'), ('tek', 'Tek tarih (… itibarıyla)')], string='Tarih', default='aralik',
                                  required=True)
    karsilastirma = fields.Boolean(string='Dönem Karşılaştırması', default=True)
    filtre_cari = fields.Boolean(string='Cari Filtresi')
    filtre_yevmiye = fields.Boolean(string='Yevmiye Filtresi', default=True)
    filtre_analitik = fields.Boolean(string='Analitik Filtresi')
    filtre_hesap = fields.Boolean(string='Hesap Kodu Filtresi')
    filtre_seviye = fields.Boolean(string='Seviye Seçimi')
    filtre_cari_turu = fields.Boolean(string='Alıcı / Satıcı Seçimi')
    kapanis_haric = fields.Boolean(string='Kapanış Fişleri Hariç', default=True,
                                   help='Rapor dönemine ait yıl sonu kapanış fişleri dikkate alınmaz (kapanış öncesi durum).')
    varsayilan_seviye = fields.Selection([('1', 'Sınıf'), ('2', 'Grup'), ('3', 'Ana hesap'), ('4', 'Alt hesap')], default='3')
    nakit_hesaplari = fields.Char(string='Nakit Hesapları', default='100,102,108',
                                  help='Nakit akış tablosunda nakit sayılan hesap kodu önekleri')
    satir_ids = fields.One2many('atlas.finansal.rapor.satir', 'rapor_id', string='Satırlar', copy=True)
    action_id = fields.Many2one('ir.actions.client', string='Menü Eylemi', readonly=True, copy=False)
    aciklama = fields.Text(string='Açıklama')
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------ istemci API'si
    def _baglam(self, secenekler):
        self.ensure_one()
        return Baglam(self, secenekler)

    def _isleyici(self, b):
        return ISLEYICILER[self.tur](b)

    def rapor_verisi(self, secenekler=None):
        """Raporun tamamı (açık satırlar dahil), kolonlar ve normalleştirilmiş seçenekler."""
        self.ensure_one()
        b = self._baglam(secenekler)
        isleyici = self._isleyici(b)
        satirlar = isleyici.genislet(isleyici.kok())
        notlar = self._notlar()
        for s in satirlar:
            s['not'] = notlar.get(s['anahtar'])
        return {
            'rapor': {'id': self.id, 'ad': self.name, 'tur': self.tur, 'tarih_modu': self.tarih_modu, 'karsilastirma': self.karsilastirma,
                      'filtre_cari': self.filtre_cari, 'filtre_yevmiye': self.filtre_yevmiye, 'filtre_analitik': self.filtre_analitik,
                      'filtre_hesap': self.filtre_hesap, 'filtre_seviye': self.filtre_seviye, 'filtre_cari_turu': self.filtre_cari_turu,
                      'sayfali': isleyici.sayfalama},
            'secenekler': b.secenekler,
            'kolonlar': isleyici.kolonlar(),
            'satirlar': satirlar,
            'sirket': ', '.join(b.sirketler.mapped('name')),
            'para': {'sembol': b.para.symbol, 'konum': b.para.position, 'ondalik': b.para.decimal_places},
            'yevmiyeler': [{'id': y.id, 'ad': y.name} for y in self.env['account.journal'].search([('company_id', 'in', b.sirketler.ids)])],
        }

    def alt_satirlar(self, secenekler, anahtar):
        """Bir satırın (açık alt satırlarıyla birlikte) alt satırları."""
        self.ensure_one()
        b = self._baglam(secenekler)
        isleyici = self._isleyici(b)
        satirlar = isleyici.genislet(isleyici.cocuklar(anahtar))
        notlar = self._notlar()
        for s in satirlar:
            s['not'] = notlar.get(s['anahtar'])
        return satirlar

    def denetim_ac(self, denetim):
        """Tutara tıklanınca: o tutarı oluşturan kayıtların listesi."""
        model = (denetim or {}).get('model') or 'account.move.line'
        if model not in ('account.move.line', 'account.bank.statement.line', 'account.move'):
            raise UserError(self.env._('Geçersiz denetim modeli.'))
        alan = denetim.get('domain') or []
        if not isinstance(alan, list):
            raise UserError(self.env._('Geçersiz denetim alanı.'))
        eylem = {'type': 'ir.actions.act_window', 'res_model': model, 'domain': alan, 'target': 'current',
                 'views': [[False, 'list'], [False, 'form']], 'name': self.env._('Denetim: %s', self.name)}
        if model == 'account.move.line':
            eylem['context'] = {'search_default_group_by_account': 0, 'create': False, 'edit': False}
            gorunum = self.env.ref('account.view_move_line_tree', raise_if_not_found=False)
            if gorunum:
                eylem['views'] = [[gorunum.id, 'list'], [False, 'form']]
        return eylem

    # ------------------------------------------------------------------ notlar
    def _notlar(self):
        return {n.anahtar: n.metin for n in self.env['atlas.finansal.rapor.not'].search(
            [('rapor_id', '=', self.id), ('company_id', 'in', self.env.companies.ids)])}

    def not_kaydet(self, anahtar, metin):
        self.ensure_one()
        Not = self.env['atlas.finansal.rapor.not']
        mevcut = Not.search([('rapor_id', '=', self.id), ('anahtar', '=', anahtar), ('company_id', '=', self.env.company.id)], limit=1)
        if not (metin or '').strip():
            mevcut.unlink()
            return False
        if mevcut:
            mevcut.metin = metin
        else:
            Not.create({'rapor_id': self.id, 'anahtar': anahtar, 'metin': metin})
        return True

    # ------------------------------------------------------------------ çıktılar
    def xlsx_olustur(self, secenekler=None):
        """(dosya adı, içerik) — o anki açık satırlarla."""
        self.ensure_one()
        veri = self.rapor_verisi(secenekler)
        cikti = io.BytesIO()
        kitap = xlsxwriter.Workbook(cikti, {'in_memory': True})
        sayfa = kitap.add_worksheet(self.name[:31])
        b_ = kitap.add_format({'bold': True})
        baslik = kitap.add_format({'bold': True, 'font_size': 14})
        kolon_bicim = kitap.add_format({'bold': True, 'bg_color': '#E9ECEF', 'border': 1, 'align': 'center'})
        para = kitap.add_format({'num_format': '#,##0.00'})
        para_k = kitap.add_format({'num_format': '#,##0.00', 'bold': True})
        yuzde = kitap.add_format({'num_format': '0.0"%"'})
        oran = kitap.add_format({'num_format': '0.00'})
        kalin = kitap.add_format({'bold': True})
        s = veri['secenekler']
        sayfa.write(0, 0, self.name, baslik)
        sayfa.write(1, 0, veri['sirket'])
        donem = s['tarih_bit'] if self.tarih_modu == 'tek' else f"{s['tarih_bas']} - {s['tarih_bit']}"
        sayfa.write(2, 0, f'Dönem: {donem}' + ('  (taslaklar dahil)' if s['taslak'] else ''))
        sayfa.set_column(0, 0, 50)
        sayfa.set_column(1, len(veri['kolonlar']), 16)
        satir_no = 4
        sayfa.write(satir_no, 0, '', kolon_bicim)
        for i, k in enumerate(veri['kolonlar'], 1):
            sayfa.write(satir_no, i, k['ad'], kolon_bicim)
        for s_ in veri['satirlar']:
            if s_['sinif'] == 'daha':
                continue
            satir_no += 1
            k_ = s_['sinif'] in ('toplam', 'baslik')
            sayfa.write(satir_no, 0, '    ' * (s_.get('seviye') or 0) + s_['ad'], kalin if k_ else None)
            for i, (k, v) in enumerate(zip(veri['kolonlar'], s_['degerler']), 1):
                if v is None or v is False:
                    continue
                tur = s_.get('bicim') if k['tur'] == 'para' and s_.get('bicim') not in (None, 'para') else k['tur']
                if tur in ('para', 'doviz'):
                    sayfa.write_number(satir_no, i, v, para_k if k_ else para)
                elif tur == 'yuzde':
                    sayfa.write_number(satir_no, i, v, yuzde)
                elif tur in ('oran', 'gun'):
                    sayfa.write_number(satir_no, i, v, oran)
                else:
                    sayfa.write(satir_no, i, v)
        kitap.close()
        ad = f"{self.name} {s['tarih_bit']}.xlsx".replace('/', '-')
        return ad, cikti.getvalue()

    def xlsx_indir(self, secenekler=None):
        ad, icerik = self.xlsx_olustur(secenekler)
        ek = self.env['ir.attachment'].create({'name': ad, 'datas': base64.b64encode(icerik), 'res_model': self._name, 'res_id': self.id,
                                               'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{ek.id}?download=true', 'target': 'self'}

    def pdf_indir(self, secenekler=None):
        self.ensure_one()
        return self.env.ref('atlas_finansal.action_report_finansal').report_action(self, data={'rapor_id': self.id,
                                                                                               'secenekler': secenekler or {}})

    # ------------------------------------------------------------------ menü eylemi
    def action_ac(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'atlas_finansal.rapor', 'name': self.name, 'params': {'rapor_id': self.id}}


class AtlasFinansalRaporSatir(models.Model):
    _name = 'atlas.finansal.rapor.satir'
    _description = 'Finansal Rapor Satırı'
    _order = 'sira, id'

    rapor_id = fields.Many2one('atlas.finansal.rapor', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Satır', required=True, translate=True)
    kod = fields.Char(string='Kod', help='Formüllerde kullanılır (BÜYÜK HARF, ör. NET_SATIS)')
    sira = fields.Integer(default=10)
    parent_id = fields.Many2one('atlas.finansal.rapor.satir', string='Üst Satır', domain="[('rapor_id', '=', rapor_id)]",
                                ondelete='cascade')
    motor = fields.Selection([('baslik', 'Başlık'), ('hesap', 'Hesap kodları'), ('toplam', 'Alt satırların toplamı'),
                              ('formul', 'Formül'), ('nakit', 'Nakit akışı (karşı hesap)'), ('nakit_acilis', 'Dönem başı nakit'),
                              ('nakit_kapanis', 'Dönem sonu nakit')], string='Hesaplama', required=True, default='hesap')
    hesaplar = fields.Char(string='Hesap Kodları', help='Önekler, virgülle: "600,601,!6019" (! ile başlayan hariç)')
    donem_turu = fields.Selection([('bakiye', 'Dönem sonu bakiyesi'), ('hareket', 'Dönem hareketi (net)'), ('borc', 'Dönem borç toplamı'),
                                   ('alacak', 'Dönem alacak toplamı'), ('acilis', 'Dönem başı bakiyesi'),
                                   ('mali_yil', 'Mali yıl başından itibaren'), ('mali_yil_oncesi', 'Mali yıl öncesi bakiyesi')],
                                  string='Tutar', default='bakiye', required=True)
    isaret = fields.Integer(string='İşaret', default=1, help='-1: alacak bakiyeli hesaplar pozitif gösterilir')
    formul = fields.Char(string='Formül', help='Satır kodlarıyla: NET_SATIS - MALIYET; GUN = dönemdeki gün sayısı')
    bicim = fields.Selection([('para', 'Tutar'), ('yuzde', 'Yüzde'), ('oran', 'Oran'), ('gun', 'Gün')], default='para', required=True)
    kalin = fields.Boolean(string='Kalın (Ara Toplam)')
    gizle_sifir = fields.Boolean(string='Sıfırsa Gizle')
    gizli = fields.Boolean(string='Gizli (yalnız formül için)')
    acilabilir = fields.Boolean(string='Hesaplara Açılabilir', default=True)

    @api.constrains('formul')
    def _check_formul(self):
        for s in self.filtered('formul'):
            try:
                degiskenler = {k: 1.0 for k in s.rapor_id.satir_ids.mapped('kod') if k}
                degiskenler.update(GUN=30, abs=abs, min=min, max=max)
                safe_eval(s.formul, degiskenler)
            except ZeroDivisionError:
                pass
            except Exception as e:
                raise ValidationError(self.env._('"%(satir)s" formülü geçersiz: %(hata)s', satir=s.name, hata=e)) from e


class AtlasFinansalRaporNot(models.Model):
    _name = 'atlas.finansal.rapor.not'
    _description = 'Finansal Rapor Notu'

    rapor_id = fields.Many2one('atlas.finansal.rapor', required=True, ondelete='cascade', index=True)
    anahtar = fields.Char(required=True, index=True)
    metin = fields.Text(string='Not', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)


class AtlasFinansalRaporPdf(models.AbstractModel):
    _name = 'report.atlas_finansal.rapor_pdf'
    _description = 'Finansal Rapor PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        rapor = self.env['atlas.finansal.rapor'].browse(data.get('rapor_id') or docids)
        veri = rapor.rapor_verisi(data.get('secenekler') or {})
        return {'doc_ids': rapor.ids, 'docs': rapor, 'veri': veri, 'company': self.env.company}
