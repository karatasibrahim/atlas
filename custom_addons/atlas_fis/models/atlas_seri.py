import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import SQL

# GİB e-Fatura / e-Arşiv belge numarası: 3 karakter ön ek + 4 hane yıl + 9 hane sıra = 16 karakter
GIB_PREFIX_REGEX = re.compile(r'^[A-Z0-9]{3}$')

# Kurulumda her Türkiye şirketi için açılan örnek seriler: (ad, ön ek, hane, belge türü kodları)
DEFAULT_SERIES = [
    ('Giden Faturalar (e-Fatura/e-Arşiv)', 'ATL', 9, ['satis_fatura', 'alis_iade']),
    ('Satış İadeleri', 'SIA', 6, ['satis_iade']),
    ('Alış Faturaları', 'ALF', 6, ['alis_fatura']),
    ('Mahsup Fişleri', 'MHS', 6, ['mahsup']),
    ('Tahsil Fişleri', 'THS', 6, ['tahsil']),
    ('Tediye Fişleri', 'TDY', 6, ['tediye']),
    ('Açılış Fişleri', 'ACL', 6, ['acilis']),
    ('Kapanış Fişleri', 'KPN', 6, ['kapanis']),
    ('Dekontlar', 'DKN', 6, ['dekont']),
]


class AtlasSeri(models.Model):
    """Seri / sayaç tanımı (Netsis "seri no" tablosu).

    Belge numarası = ön ek + [yıl + ayraç] + sıra no (hane kadar sıfırla doldurulur).
    Sıra no, aynı serinin aynı ön ekli (yıl dahil) belgeleri içinde artar; yıl eklenen serilerde
    her yıl 1'den başlar. Numara, Odoo'nun kilitli ve boşluksuz numaralandırma mekanizmasıyla onayda verilir.
    """
    _name = 'atlas.seri'
    _description = 'Seri / Sayaç Tanımı'
    _order = 'company_id, sequence, id'

    name = fields.Char(string='Seri Adı', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    belge_turu_ids = fields.Many2many('atlas.belge.turu', string='Belge Türleri', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Yevmiye Defteri', check_company=True,
        help='Boşsa seri, belge türüne uygun tüm yevmiyelerde kullanılabilir. '
             'Doluysa yalnızca bu yevmiyede kullanılır ve seri seçilince yevmiye otomatik gelir.')
    varsayilan = fields.Boolean(string='Varsayılan', help='Belge türü için otomatik seçilen seri.')

    on_ek = fields.Char(string='Ön Ek', required=True)
    yil_ekle = fields.Boolean(string='Yıl Ekle', default=True, help='Numaraya belge tarihinin yılı eklenir ve sıra her yıl baştan başlar.')
    ayirac = fields.Char(string='Ayraç', size=1, help='Yıl ile sıra no arasına konur (ör. "-" ile MHS2026-000001). e-Fatura için boş olmalıdır.')
    hane = fields.Integer(string='Sıra No Hane', default=6, required=True)
    baslangic_no = fields.Integer(
        string='Başlangıç No', default=1, required=True,
        help='Seride hiç belge yokken verilecek ilk numara (ör. eski programdan devam için).')

    ornek = fields.Char(string='Sonraki Numara', compute='_compute_ornek')
    gib_uyumlu = fields.Boolean(
        string='GİB Uyumlu', compute='_compute_gib_uyumlu',
        help='e-Fatura/e-Arşiv numarası biçimi: 3 karakter ön ek + yıl + 9 hane (toplam 16 karakter).')

    # -------------------------------------------------------------------------
    # Hesaplamalar ve kısıtlar
    # -------------------------------------------------------------------------

    @api.depends('on_ek', 'yil_ekle', 'ayirac', 'hane', 'baslangic_no')
    def _compute_ornek(self):
        today = fields.Date.context_today(self)
        for seri in self:
            if not seri.on_ek or not seri.hane:
                seri.ornek = False
                continue
            prefix = seri._get_prefix(today)
            last = seri._get_last_number(prefix) if seri.id else 0
            seri.ornek = seri._format_number(prefix, max(last, seri.baslangic_no - 1) + 1)

    @api.depends('on_ek', 'yil_ekle', 'ayirac', 'hane')
    def _compute_gib_uyumlu(self):
        for seri in self:
            seri.gib_uyumlu = bool(
                seri.on_ek and GIB_PREFIX_REGEX.match(seri.on_ek) and seri.yil_ekle and not seri.ayirac and seri.hane == 9)

    @api.constrains('on_ek', 'ayirac', 'hane', 'baslangic_no')
    def _check_format(self):
        for seri in self:
            if not re.match(r'^[A-Za-z0-9./_-]+$', seri.on_ek):
                raise ValidationError(self.env._('Ön ek yalnızca harf, rakam ve . / _ - karakterlerinden oluşabilir.'))
            if seri.on_ek[-1].isdigit() and not seri.yil_ekle and not seri.ayirac:
                raise ValidationError(self.env._('Ön ek rakamla bitiyorsa sıra no ile karışmaması için ayraç kullanın veya yıl ekleyin.'))
            if seri.ayirac and seri.ayirac.isalnum():
                raise ValidationError(self.env._('Ayraç harf veya rakam olamaz (ör. "-", "/").'))
            if not 3 <= seri.hane <= 12:
                raise ValidationError(self.env._('Sıra no hane sayısı 3 ile 12 arasında olmalıdır.'))
            if seri.baslangic_no < 1 or len(str(seri.baslangic_no)) > seri.hane:
                raise ValidationError(self.env._('Başlangıç numarası 1 veya daha büyük olmalı ve hane sayısını aşmamalıdır.'))

    @api.constrains('on_ek', 'yil_ekle', 'ayirac', 'company_id', 'active')
    def _check_prefix_unique(self):
        for seri in self.filtered('active'):
            duplicate = self.search([
                ('id', '!=', seri.id),
                ('company_id', '=', seri.company_id.id),
                ('on_ek', '=', seri.on_ek),
                ('yil_ekle', '=', seri.yil_ekle),
                ('ayirac', '=', seri.ayirac),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._('"%s" ön eki "%s" serisinde kullanılıyor.', seri.on_ek, duplicate.name))

    @api.constrains('varsayilan', 'belge_turu_ids', 'journal_id', 'company_id', 'active')
    def _check_single_default(self):
        for seri in self.filtered(lambda s: s.varsayilan and s.active):
            others = self.search([
                ('id', '!=', seri.id),
                ('company_id', '=', seri.company_id.id),
                ('varsayilan', '=', True),
                ('journal_id', '=', seri.journal_id.id),
                ('belge_turu_ids', 'in', seri.belge_turu_ids.ids),
            ])
            if others:
                raise ValidationError(self.env._(
                    'Aynı belge türü için birden fazla varsayılan seri olamaz: %s', ', '.join(others.mapped('name'))))

    @api.depends('name', 'on_ek')
    def _compute_display_name(self):
        for seri in self:
            seri.display_name = f'{seri.on_ek} - {seri.name}' if seri.on_ek else seri.name

    # -------------------------------------------------------------------------
    # Numara üretimi
    # -------------------------------------------------------------------------

    def _get_prefix(self, date):
        """Sıra numarasından önceki sabit kısım (ör. ATL2026, MHS2026-, M-)."""
        self.ensure_one()
        if self.yil_ekle:
            return f'{self.on_ek}{date.year}{self.ayirac or ""}'
        return f'{self.on_ek}{self.ayirac or ""}'

    def _format_number(self, prefix, number):
        self.ensure_one()
        if len(str(number)) > self.hane:
            raise UserError(self.env._('"%s" serisinin sıra numarası %s haneyi aştı.', self.name, self.hane))
        return f'{prefix}{number:0{self.hane}d}'

    @api.model
    def _number_sources(self):
        """Seri numarası taşıyan tablolar: [(model, numara alanı)]. Her tabloda atlas_seri_id bulunur.
        Alt modüller (ör. irsaliye) genişletir."""
        return [('account.move', 'name')]

    def _get_last_number(self, prefix):
        """Seride bu ön ekle verilmiş en büyük sıra no (tüm kaynaklarda, tüm durumlardaki belgeler)."""
        self.ensure_one()
        like = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        last = 0
        for model_name, field_name in self._number_sources():
            Model = self.env[model_name]
            Model.flush_model([field_name, 'atlas_seri_id'])
            column = SQL.identifier(field_name)
            result = self.env.execute_query(SQL(
                """
                SELECT MAX(CAST(SUBSTRING(%(column)s FROM %(start)s) AS BIGINT))
                  FROM %(table)s
                 WHERE atlas_seri_id = %(seri)s
                   AND %(column)s LIKE %(like)s
                   AND LENGTH(%(column)s) = %(length)s
                   AND SUBSTRING(%(column)s FROM %(start)s) ~ '^[0-9]+$'
                """,
                column=column, table=SQL.identifier(Model._table),
                start=len(prefix) + 1, seri=self.id, like=like, length=len(prefix) + self.hane,
            ))
            last = max(last, result[0][0] or 0)
        return last

    def _next_number(self, date):
        """Seriden sıradaki numarayı verir (fatura dışı belgeler için; seri satırı kilitlenir)."""
        self.ensure_one()
        self.env.execute_query(SQL('SELECT id FROM atlas_seri WHERE id = %s FOR UPDATE', self.id))
        prefix = self._get_prefix(date)
        return self._format_number(prefix, max(self._get_last_number(prefix), self.baslangic_no - 1) + 1)

    def _get_next_sequence_format(self, date):
        """sequence.mixin._locked_increment için biçim: ({prefix}{seq:0Nd}, {'seq': son no})."""
        self.ensure_one()
        prefix = self._get_prefix(date)
        last = max(self._get_last_number(prefix), self.baslangic_no - 1)
        format_string = prefix.replace('{', '{{').replace('}', '}}') + '{seq:0%sd}' % self.hane
        return format_string, {'seq': last}

    @api.model
    def _get_default(self, belge_turu, company, journal=None):
        """Belge türü için varsayılan seri: yevmiyeye özel olan, yoksa genel olan."""
        domain = [
            ('company_id', '=', company.id),
            ('belge_turu_ids.code', '=', belge_turu),
        ]
        if journal:
            domain.append(('journal_id', 'in', (journal.id, False)))
        candidates = self.search(domain)
        return candidates.sorted(lambda s: (not s.varsayilan, not s.journal_id, s.sequence, s.id))[:1]

    @api.model
    def _atlas_create_default_series(self, company):
        """Şirkette hiç seri yoksa örnek seri/sayaç tanımlarını oluşturur."""
        if self.with_context(active_test=False).search_count([('company_id', '=', company.id)]):
            return self
        BelgeTuru = self.env['atlas.belge.turu']
        vals_list = []
        for sequence, (name, on_ek, hane, codes) in enumerate(DEFAULT_SERIES, start=1):
            vals_list.append({
                'name': name,
                'sequence': sequence * 10,
                'company_id': company.id,
                'on_ek': on_ek,
                'yil_ekle': True,
                'hane': hane,
                'varsayilan': True,
                'belge_turu_ids': [Command.set(BelgeTuru.search([('code', 'in', codes)]).ids)],
            })
        return self.create(vals_list)

    def action_create_default_series(self):
        self._atlas_create_default_series(self.env.company)
