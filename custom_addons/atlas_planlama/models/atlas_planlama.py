from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

GUNLER = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']


def _saat_metni(saat):
    s = int(saat) % 24
    dk = int(round((saat - int(saat)) * 60))
    return f'{s:02d}:{dk:02d}'


class AtlasPlanlamaRol(models.Model):
    _name = 'atlas.planlama.rol'
    _description = 'Planlama Rolü'
    _order = 'sequence, name'

    name = fields.Char(string='Rol', required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Renk')
    active = fields.Boolean(default=True)
    employee_ids = fields.Many2many('hr.employee', string='Bu rolü üstlenebilenler')


class AtlasPlanlamaSablon(models.Model):
    """Vardiya şablonu: başlangıç saati, süre ve mola."""
    _name = 'atlas.planlama.sablon'
    _description = 'Vardiya Şablonu'
    _order = 'sequence, baslangic_saat'

    ad = fields.Char(string='Şablon', required=True)
    name = fields.Char(compute='_compute_name', store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    baslangic_saat = fields.Float(string='Başlangıç', required=True, default=8.0)
    sure_saat = fields.Float(string='Süre (saat)', required=True, default=8.0)
    mola_dk = fields.Integer(string='Mola (dk)', default=30)
    rol_id = fields.Many2one('atlas.planlama.rol', string='Rol')
    workcenter_id = fields.Many2one('mrp.workcenter', string='İş Merkezi')
    company_id = fields.Many2one('res.company', string='Şirket')

    _sure_pozitif = models.Constraint('CHECK(sure_saat > 0 AND sure_saat <= 24)', 'Vardiya süresi 0-24 saat arasında olmalı.')
    _saat_aralik = models.Constraint('CHECK(baslangic_saat >= 0 AND baslangic_saat < 24)', 'Başlangıç saati 00:00-23:59 arasında olmalı.')

    @api.depends('ad', 'baslangic_saat', 'sure_saat')
    def _compute_name(self):
        for sablon in self:
            bitis = sablon.baslangic_saat + sablon.sure_saat
            sablon.name = f'{sablon.ad} {_saat_metni(sablon.baslangic_saat)}-{_saat_metni(bitis)}'


class AtlasPlanlamaVardiya(models.Model):
    _name = 'atlas.planlama.vardiya'
    _description = 'Vardiya'
    _inherit = ['mail.thread']
    _order = 'baslangic, employee_id'

    name = fields.Char(compute='_compute_name', string='Vardiya')
    employee_id = fields.Many2one('hr.employee', string='Çalışan', index=True, tracking=True,
                                  help='Boş bırakılırsa açık (atanmamış) vardiyadır.')
    user_id = fields.Many2one(related='employee_id.user_id', string='Kullanıcı', store=True)
    rol_id = fields.Many2one('atlas.planlama.rol', string='Rol', tracking=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='İş Merkezi', index=True)
    sablon_id = fields.Many2one('atlas.planlama.sablon', string='Şablon')
    baslangic = fields.Datetime(string='Başlangıç', required=True, index=True, tracking=True)
    bitis = fields.Datetime(string='Bitiş', required=True, tracking=True)
    mola_dk = fields.Integer(string='Mola (dk)', default=0)
    planlanan_saat = fields.Float(string='Planlanan Saat', compute='_compute_planlanan_saat', store=True, aggregator='sum')
    durum = fields.Selection([('taslak', 'Taslak'), ('yayinlandi', 'Yayınlandı')], string='Durum',
                             default='taslak', required=True, tracking=True, index=True)
    yayin_tarihi = fields.Datetime(string='Yayın Tarihi', readonly=True, copy=False)
    notlar = fields.Text(string='Not')
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    color = fields.Integer(related='rol_id.color', string='Renk')
    cakisma = fields.Boolean(string='Çakışma', compute='_compute_uyarilar')
    izinli = fields.Boolean(string='İzinli', compute='_compute_uyarilar')
    uyari = fields.Char(string='Uyarı', compute='_compute_uyarilar')

    _tarih_sirasi = models.Constraint('CHECK(bitis > baslangic)', 'Vardiya bitişi başlangıçtan sonra olmalı.')

    @api.depends('baslangic', 'bitis', 'employee_id', 'rol_id')
    def _compute_name(self):
        for v in self:
            if not v.baslangic or not v.bitis:
                v.name = ''
                continue
            bas, bit = self._yerel(v.baslangic), self._yerel(v.bitis)
            v.name = f'{v.employee_id.sudo().name or self.env._("Açık vardiya")} {bas:%d.%m %H:%M}-{bit:%H:%M}' + (
                f' ({v.rol_id.name})' if v.rol_id else '')

    @api.depends('baslangic', 'bitis', 'mola_dk')
    def _compute_planlanan_saat(self):
        for v in self:
            if v.baslangic and v.bitis:
                v.planlanan_saat = max((v.bitis - v.baslangic).total_seconds() / 3600.0 - (v.mola_dk or 0) / 60.0, 0.0)
            else:
                v.planlanan_saat = 0.0

    def _compute_uyarilar(self):
        Leave = self.env['hr.leave'] if 'hr.leave' in self.env else None
        for v in self:
            cakisan = self.search_count([
                ('id', '!=', v.id or 0), ('employee_id', '=', v.employee_id.id),
                ('baslangic', '<', v.bitis), ('bitis', '>', v.baslangic)]) if v.employee_id and v.baslangic and v.bitis else 0
            izin = Leave.sudo().search_count([
                ('employee_id', '=', v.employee_id.id), ('state', '=', 'validate'),
                ('date_from', '<', v.bitis), ('date_to', '>', v.baslangic)]) if Leave is not None and v.employee_id and v.baslangic else 0
            v.cakisma, v.izinli = bool(cakisan), bool(izin)
            mesaj = []
            if cakisan:
                mesaj.append(self.env._('Aynı saatlerde başka vardiyası var'))
            if izin:
                mesaj.append(self.env._('Bu tarihte onaylı izni var'))
            v.uyari = ', '.join(mesaj)

    @api.onchange('sablon_id')
    def _onchange_sablon_id(self):
        if self.sablon_id:
            gun = self._yerel(self.baslangic).date() if self.baslangic else fields.Date.context_today(self)
            self.update(self._sablon_degerleri(self.sablon_id, gun))

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and not self.rol_id:
            self.rol_id = self.env['atlas.planlama.rol'].search([('employee_ids', 'in', self.employee_id.ids)], limit=1)

    # -------------------------------------------------------------------------
    # Saat dilimi
    # -------------------------------------------------------------------------

    @api.model
    def _tz(self):
        return ZoneInfo(self.env.user.tz or self.env.company.partner_id.tz or 'Europe/Istanbul')

    @api.model
    def _yerel(self, utc_dt):
        return utc_dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(self._tz()).replace(tzinfo=None)

    @api.model
    def _utc(self, yerel_dt):
        return yerel_dt.replace(tzinfo=self._tz()).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

    @api.model
    def _sablon_degerleri(self, sablon, gun):
        bas = datetime.combine(gun, time()) + timedelta(hours=sablon.baslangic_saat)
        vals = {'baslangic': self._utc(bas), 'bitis': self._utc(bas + timedelta(hours=sablon.sure_saat)),
                'mola_dk': sablon.mola_dk, 'sablon_id': sablon.id}
        if sablon.rol_id:
            vals['rol_id'] = sablon.rol_id.id
        if sablon.workcenter_id:
            vals['workcenter_id'] = sablon.workcenter_id.id
        return vals

    # -------------------------------------------------------------------------
    # Yayınlama ve kopyalama
    # -------------------------------------------------------------------------

    def action_yayinla(self):
        taslaklar = self.filtered(lambda v: v.durum == 'taslak')
        taslaklar.write({'durum': 'yayinlandi', 'yayin_tarihi': fields.Datetime.now()})
        for employee, vardiyalar in taslaklar.grouped('employee_id').items():
            partner = employee.user_id.partner_id or employee.work_contact_id
            if not partner:
                continue
            satirlar = ''.join(f'<li>{v.name}</li>' for v in vardiyalar.sorted('baslangic'))
            vardiyalar[:1].message_notify(
                partner_ids=partner.ids, subject=self.env._('Vardiya planınız yayınlandı'),
                body=self.env._('Yeni vardiyalarınız:') + f'<ul>{satirlar}</ul>')
        return True

    def action_taslaga_al(self):
        self.write({'durum': 'taslak', 'yayin_tarihi': False})
        return True

    def action_tekrarla(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'atlas.planlama.tekrar.wizard', 'view_mode': 'form',
            'target': 'new', 'name': self.env._('Vardiyayı Tekrarla'), 'context': {'default_vardiya_ids': self.ids},
        }

    def _kopyala(self, gun_farki):
        """Vardiyaları gün farkı kadar ileri taşıyarak taslak kopyalar; aynısı varsa atlar."""
        yeni = self.browse()
        for v in self:
            bas, bit = v.baslangic + timedelta(days=gun_farki), v.bitis + timedelta(days=gun_farki)
            if self.search_count([('employee_id', '=', v.employee_id.id), ('baslangic', '=', bas), ('bitis', '=', bit)]):
                continue
            yeni |= v.copy({'baslangic': bas, 'bitis': bit, 'durum': 'taslak'})
        return yeni

    # -------------------------------------------------------------------------
    # Haftalık plan ekranı
    # -------------------------------------------------------------------------

    @api.model
    def _hafta(self, hafta_basi):
        gun = fields.Date.to_date(hafta_basi) if hafta_basi else fields.Date.context_today(self)
        gun = gun - timedelta(days=gun.weekday())
        return [gun + timedelta(days=i) for i in range(7)]

    @api.model
    def _hafta_araligi(self, gunler):
        return self._utc(datetime.combine(gunler[0], time())), self._utc(datetime.combine(gunler[-1] + timedelta(days=1), time()))

    @api.model
    def _yonetici_mi(self):
        return self.env.user.has_group('atlas_planlama.group_planlama_manager')

    @api.model
    def hafta_verisi(self, hafta_basi=False, rol_id=False):
        gunler = self._hafta(hafta_basi)
        bas, bit = self._hafta_araligi(gunler)
        domain = [('baslangic', '<', bit), ('bitis', '>', bas), ('company_id', 'in', self.env.companies.ids)]
        if rol_id:
            domain.append(('rol_id', '=', rol_id))
        vardiyalar = self.search(domain)
        bugun = fields.Date.context_today(self)

        # Çalışan kartını normal kullanıcı okuyamaz; ad/unvan gösterimi için yetkili okunur.
        # Yönetici olmayan yalnızca görebildiği (yayınlanmış) vardiyaların çalışanlarını görür.
        if self._yonetici_mi():
            calisanlar = self.env['hr.employee'].sudo().search([('company_id', 'in', self.env.companies.ids)], order='name')
        else:
            calisanlar = vardiyalar.employee_id.sudo().sorted('name')
        if rol_id:
            rol = self.env['atlas.planlama.rol'].browse(rol_id)
            calisanlar = calisanlar.filtered(lambda e: e in rol.employee_ids or e in vardiyalar.employee_id) if rol.employee_ids else vardiyalar.employee_id
        izinler = {}
        if 'hr.leave' in self.env and calisanlar:
            for izin in self.env['hr.leave'].sudo().search([
                    ('employee_id', 'in', calisanlar.ids), ('state', '=', 'validate'),
                    ('date_from', '<', bit), ('date_to', '>', bas)]):
                for i, gun in enumerate(gunler):
                    g_bas, g_bit = self._hafta_araligi([gun])
                    if izin.date_from < g_bit and izin.date_to > g_bas:
                        izinler.setdefault(izin.employee_id.id, set()).add(i)

        def kart(v):
            yb, yt = self._yerel(v.baslangic), self._yerel(v.bitis)
            return {'id': v.id, 'saat': f'{yb:%H:%M}-{yt:%H:%M}', 'rol': v.rol_id.name or '', 'renk': v.color or 0,
                    'durum': v.durum, 'uyari': v.uyari or '', 'is_merkezi': v.workcenter_id.name or '',
                    'saat_toplam': v.planlanan_saat}

        satirlar = []
        for employee in list(calisanlar) + [self.env['hr.employee'].sudo()]:
            gun_kartlari = [[] for _g in gunler]
            for v in vardiyalar.filtered(lambda x: x.employee_id == employee):
                i = (self._yerel(v.baslangic).date() - gunler[0]).days
                if 0 <= i < 7:
                    gun_kartlari[i].append(kart(v))
            if not employee and not any(gun_kartlari) and not self._yonetici_mi():
                continue
            satirlar.append({
                'id': employee.id or False, 'ad': employee.name or self.env._('Açık vardiyalar'),
                'is_unvani': employee.job_title or '' if employee else '',
                'gunler': gun_kartlari, 'izinli': sorted(izinler.get(employee.id, [])),
                'toplam_saat': sum(k['saat_toplam'] for g in gun_kartlari for k in g),
            })
        return {
            'hafta_basi': fields.Date.to_string(gunler[0]),
            'baslik': f'{gunler[0]:%d.%m.%Y} - {gunler[-1]:%d.%m.%Y}',
            'gunler': [{'tarih': fields.Date.to_string(g), 'ad': f'{GUNLER[i]} {g:%d.%m}', 'bugun': g == bugun}
                       for i, g in enumerate(gunler)],
            'satirlar': satirlar,
            'sablonlar': [{'id': s.id, 'ad': s.name} for s in self.env['atlas.planlama.sablon'].search(
                [('company_id', 'in', self.env.companies.ids + [False])])],
            'roller': [{'id': r.id, 'ad': r.name} for r in self.env['atlas.planlama.rol'].search([])],
            'rol_id': rol_id or False,
            'taslak_sayisi': len(vardiyalar.filtered(lambda v: v.durum == 'taslak')),
            'toplam_saat': sum(vardiyalar.mapped('planlanan_saat')),
            'yonetici': self._yonetici_mi(),
        }

    @api.model
    def _yonetici_kontrol(self):
        if not self._yonetici_mi():
            raise UserError(self.env._('Vardiya planını yalnızca planlama yöneticileri değiştirebilir.'))

    @api.model
    def hizli_olustur(self, employee_id, gun, sablon_id):
        self._yonetici_kontrol()
        sablon = self.env['atlas.planlama.sablon'].browse(sablon_id).exists()
        if not sablon:
            raise UserError(self.env._('Şablon bulunamadı.'))
        vals = self._sablon_degerleri(sablon, fields.Date.to_date(gun))
        vals['employee_id'] = employee_id or False
        if employee_id and not sablon.rol_id:
            rol = self.env['atlas.planlama.rol'].search([('employee_ids', 'in', [employee_id])], limit=1)
            if rol:
                vals['rol_id'] = rol.id
        return self.create(vals).id

    def tasi(self, employee_id, gun):
        """Sürükle-bırak: vardiyayı başka çalışana / güne taşır (saatler korunur)."""
        self._yonetici_kontrol()
        self.ensure_one()
        hedef = fields.Date.to_date(gun)
        fark = (hedef - self._yerel(self.baslangic).date()).days
        self.write({'employee_id': employee_id or False,
                    'baslangic': self.baslangic + timedelta(days=fark), 'bitis': self.bitis + timedelta(days=fark)})
        return True

    @api.model
    def hafta_yayinla(self, hafta_basi, rol_id=False):
        self._yonetici_kontrol()
        bas, bit = self._hafta_araligi(self._hafta(hafta_basi))
        domain = [('durum', '=', 'taslak'), ('baslangic', '>=', bas), ('baslangic', '<', bit), ('company_id', 'in', self.env.companies.ids)]
        if rol_id:
            domain.append(('rol_id', '=', rol_id))
        vardiyalar = self.search(domain)
        acik = vardiyalar.filtered(lambda v: not v.employee_id)
        (vardiyalar - acik).action_yayinla()
        mesaj = self.env._('%s vardiya yayınlandı.', len(vardiyalar - acik))
        if acik:
            mesaj += ' ' + self.env._('%s açık vardiya çalışan atanmadığı için yayınlanmadı.', len(acik))
        return mesaj

    @api.model
    def onceki_haftayi_kopyala(self, hafta_basi):
        self._yonetici_kontrol()
        gunler = self._hafta(hafta_basi)
        bas, bit = self._hafta_araligi([g - timedelta(days=7) for g in gunler])
        onceki = self.search([('baslangic', '>=', bas), ('baslangic', '<', bit), ('company_id', 'in', self.env.companies.ids)])
        yeni = onceki._kopyala(7)
        return self.env._('%s vardiya kopyalandı (taslak).', len(yeni))

    # -------------------------------------------------------------------------
    # İş merkezi doluluğu
    # -------------------------------------------------------------------------

    @api.model
    def doluluk_verisi(self, hafta_basi=False):
        gunler = self._hafta(hafta_basi)
        bas, bit = self._hafta_araligi(gunler)
        merkezler = self.env['mrp.workcenter'].search([('company_id', 'in', self.env.companies.ids + [False])])
        vardiyalar = self.search([('workcenter_id', 'in', merkezler.ids), ('baslangic', '<', bit), ('bitis', '>', bas)])
        isler = self.env['mrp.workorder'].search([
            ('workcenter_id', 'in', merkezler.ids), ('state', 'not in', ('done', 'cancel')),
            ('date_start', '<', bit), ('date_start', '>=', bas)])

        def gun_index(dt):
            i = (self._yerel(dt).date() - gunler[0]).days
            return i if 0 <= i < 7 else None

        satirlar = []
        for wc in merkezler:
            kapasite, yuk = [0.0] * 7, [0.0] * 7
            for v in vardiyalar.filtered(lambda x: x.workcenter_id == wc):
                i = gun_index(v.baslangic)
                if i is not None:
                    kapasite[i] += v.planlanan_saat
            for wo in isler.filtered(lambda x: x.workcenter_id == wc):
                i = gun_index(wo.date_start)
                if i is not None:
                    yuk[i] += wo.duration_expected / 60.0
            satirlar.append({
                'id': wc.id, 'ad': wc.name,
                'gunler': [{'kapasite': round(k, 2), 'yuk': round(y, 2),
                            'oran': round(100.0 * y / k) if k else (100 if y else 0),
                            'durum': 'asiri' if y > k + 1e-6 else ('bos' if not y else 'uygun')}
                           for k, y in zip(kapasite, yuk)],
            })
        return {'gunler': [{'tarih': fields.Date.to_string(g), 'ad': f'{GUNLER[i]} {g:%d.%m}'} for i, g in enumerate(gunler)],
                'satirlar': satirlar}
