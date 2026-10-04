import math
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_round

ONAY_ALANLARI = {'atlas_onayli', 'atlas_onaylayan_id', 'atlas_onay_tarihi'}


class ResCompany(models.Model):
    _inherit = 'res.company'

    atlas_zaman_yuvarlama = fields.Integer(string='Sayaç Yuvarlama (dk)', default=15,
                                           help='Sayaç durdurulunca süre bu dakikanın katına yukarı yuvarlanır. 0: yuvarlama yok.')
    atlas_zaman_minimum = fields.Integer(string='Asgari Süre (dk)', default=15,
                                         help='Sayaçla girilen kayıtlar en az bu kadar olur.')
    atlas_zaman_hatirlatma = fields.Boolean(string='Çalışan Hatırlatması', default=True,
                                            help='Geçen hafta mesai saatinden az kayıt giren çalışanlara pazartesi e-posta gönderilir.')
    atlas_zaman_onay_hatirlatma = fields.Boolean(string='Onaylayıcı Hatırlatması', default=True,
                                                 help='Onay bekleyen kayıtlar için yöneticilere pazartesi e-posta gönderilir.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    atlas_zaman_yuvarlama = fields.Integer(related='company_id.atlas_zaman_yuvarlama', readonly=False)
    atlas_zaman_minimum = fields.Integer(related='company_id.atlas_zaman_minimum', readonly=False)
    atlas_zaman_hatirlatma = fields.Boolean(related='company_id.atlas_zaman_hatirlatma', readonly=False)
    atlas_zaman_onay_hatirlatma = fields.Boolean(related='company_id.atlas_zaman_onay_hatirlatma', readonly=False)


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    atlas_onayli = fields.Boolean(string='Onaylı', readonly=True, copy=False, index=True)
    atlas_onaylayan_id = fields.Many2one('res.users', string='Onaylayan', readonly=True, copy=False)
    atlas_onay_tarihi = fields.Datetime(string='Onay Tarihi', readonly=True, copy=False)

    def _is_readonly(self):
        return super()._is_readonly() or self.atlas_onayli

    def _atlas_onaylayici_mi(self):
        return self.env.su or self.env.user.has_group('hr_timesheet.group_hr_timesheet_approver')

    def _atlas_kilit_kontrol(self):
        kilitli = self.filtered(lambda l: l.project_id and l.atlas_onayli)
        if kilitli:
            raise UserError(self.env._('Onaylanmış zaman kayıtları değiştirilemez veya silinemez (%s kayıt). '
                                       'Önce onayı kaldırılmalıdır.', len(kilitli)))

    def write(self, vals):
        if set(vals) - ONAY_ALANLARI:
            self._atlas_kilit_kontrol()
        return super().write(vals)

    def unlink(self):
        self._atlas_kilit_kontrol()
        return super().unlink()

    def action_atlas_onayla(self):
        if not self._atlas_onaylayici_mi():
            raise AccessError(self.env._('Zaman kayıtlarını yalnızca onaylayıcılar onaylayabilir.'))
        satirlar = self.filtered(lambda l: l.project_id and not l.atlas_onayli)
        satirlar.write({'atlas_onayli': True, 'atlas_onaylayan_id': self.env.uid, 'atlas_onay_tarihi': fields.Datetime.now()})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('%s zaman kaydı onaylandı.', len(satirlar)),
                           'next': {'type': 'ir.actions.act_window_close'}}}

    def action_atlas_onay_kaldir(self):
        if not self._atlas_onaylayici_mi():
            raise AccessError(self.env._('Onayı yalnızca onaylayıcılar kaldırabilir.'))
        self.filtered('atlas_onayli').write({'atlas_onayli': False, 'atlas_onaylayan_id': False, 'atlas_onay_tarihi': False})
        return True

    # -------------------------------------------------------------------------
    # Haftalık tablo
    # -------------------------------------------------------------------------

    @api.model
    def _atlas_calisan(self, employee_id=None):
        Employee = self.env['hr.employee']
        if employee_id:
            calisan = Employee.browse(int(employee_id)).exists()
            if not calisan:
                raise UserError(self.env._('Çalışan bulunamadı.'))
            if calisan.user_id != self.env.user and not self._atlas_onaylayici_mi():
                raise AccessError(self.env._('Başka bir çalışanın zaman çizelgesini göremezsiniz.'))
            return calisan
        calisan = self.env.user.employee_id
        if not calisan:
            raise UserError(self.env._('Kullanıcınıza bağlı bir çalışan kaydı yok; İK yöneticinize başvurun.'))
        return calisan

    @api.model
    def _atlas_beklenen(self, calisan, bas, bit):
        """{tarih: mesai saati} — çalışma takvimine ve izinlere göre."""
        if not calisan.resource_calendar_id:
            return {}
        sonuc = calisan._list_work_time_per_day(datetime.combine(bas, time.min), datetime.combine(bit, time.max))
        return {gun: saat for gun, saat in sonuc.get(calisan.id, [])}

    @api.model
    def atlas_haftalik(self, baslangic, employee_id=None):
        calisan = self._atlas_calisan(employee_id)
        bas = fields.Date.to_date(baslangic)
        bas -= timedelta(days=bas.weekday())
        bit = bas + timedelta(days=6)
        gunler = [bas + timedelta(days=i) for i in range(7)]
        beklenen = self._atlas_beklenen(calisan, bas, bit)
        Line = self.sudo() if self._atlas_onaylayici_mi() else self
        satirlar = Line.search([('employee_id', '=', calisan.id), ('project_id', '!=', False),
                                ('date', '>=', bas), ('date', '<=', bit)])
        onceki = Line.search([('employee_id', '=', calisan.id), ('project_id', '!=', False),
                              ('date', '>=', bas - timedelta(days=7)), ('date', '<', bas)])
        tablo = {}

        def satir_al(proje, gorev):
            anahtar = (proje.id, gorev.id or False)
            if anahtar not in tablo:
                tablo[anahtar] = {
                    'anahtar': f'{proje.id}_{gorev.id or 0}', 'project_id': proje.id, 'project_ad': proje.display_name,
                    'task_id': gorev.id or False, 'task_ad': gorev.display_name if gorev else '',
                    'hucreler': {str(g): {'saat': 0.0, 'kilitli': False} for g in gunler}, 'toplam': 0.0,
                }
            return tablo[anahtar]

        for satir in onceki:
            satir_al(satir.project_id, satir.task_id)
        for satir in satirlar:
            kayit = satir_al(satir.project_id, satir.task_id)
            hucre = kayit['hucreler'][str(satir.date)]
            hucre['saat'] += satir.unit_amount
            hucre['kilitli'] = hucre['kilitli'] or satir.atlas_onayli
            kayit['toplam'] += satir.unit_amount
        sayac = self.env['atlas.zaman.sayac'].search([('user_id', '=', self.env.uid)], limit=1)
        calisanlar = []
        if self._atlas_onaylayici_mi():
            calisanlar = [{'id': c.id, 'ad': c.name} for c in self.env['hr.employee'].search(
                [('company_id', 'in', self.env.companies.ids)], order='name')]
        projeler = self.env['project.project'].search([('allow_timesheets', '=', True)], order='name')
        gorevler = self.env['project.task'].search([('project_id', 'in', projeler.ids), ('state', 'not in', ('1_done', '1_canceled'))],
                                                   order='project_id, name', limit=2000)
        return {
            'calisan': {'id': calisan.id, 'ad': calisan.name},
            'kendi': calisan.user_id == self.env.user,
            'calisanlar': calisanlar,
            'onaylayici': self._atlas_onaylayici_mi(),
            'gunler': [{'tarih': str(g), 'gun': g.day, 'hafta_ici': g.weekday(), 'beklenen': round(beklenen.get(g, 0.0), 2),
                        'bugun': g == fields.Date.context_today(self)} for g in gunler],
            'satirlar': sorted(tablo.values(), key=lambda s: (s['project_ad'], s['task_ad'])),
            'projeler': [{'id': p.id, 'ad': p.display_name} for p in projeler],
            'gorevler': [{'id': t.id, 'ad': t.name, 'project_id': t.project_id.id} for t in gorevler],
            'sayac': sayac._atlas_bilgi() if sayac else False,
            'bekleyen_onay': Line.search_count([('employee_id', '=', calisan.id), ('project_id', '!=', False),
                                                ('date', '>=', bas), ('date', '<=', bit), ('atlas_onayli', '=', False)]),
        }

    @api.model
    def atlas_hucre_kaydet(self, employee_id, project_id, task_id, tarih, saat):
        """Hücreye yazılan toplamı kayıtlara dağıtır: fark son kayda eklenir / sondan düşülür."""
        calisan = self._atlas_calisan(employee_id)
        saat = float_round(max(float(saat or 0.0), 0.0), precision_digits=2)
        if saat > 24:
            raise ValidationError(self.env._('Bir günde 24 saatten fazla girilemez.'))
        Line = self.sudo() if calisan.user_id != self.env.user and self._atlas_onaylayici_mi() else self
        alan = [('employee_id', '=', calisan.id), ('project_id', '=', int(project_id)),
                ('task_id', '=', int(task_id) if task_id else False), ('date', '=', tarih)]
        mevcut = Line.search(alan, order='id')
        onayli = mevcut.filtered('atlas_onayli')
        acik = mevcut - onayli
        if onayli and float_compare(saat, sum(mevcut.mapped('unit_amount')), precision_digits=2):
            raise UserError(self.env._('Bu gündeki kayıtlar onaylandığı için değiştirilemez.'))
        fark = saat - sum(mevcut.mapped('unit_amount'))
        if float_compare(fark, 0.0, precision_digits=2) > 0:
            if acik:
                acik[-1].unit_amount += fark
            else:
                Line.create({'employee_id': calisan.id, 'project_id': int(project_id), 'task_id': int(task_id) if task_id else False,
                             'date': tarih, 'unit_amount': fark, 'name': '/'})
        elif float_compare(fark, 0.0, precision_digits=2) < 0:
            dusulecek = -fark
            for satir in acik.sorted('id', reverse=True):
                if float_compare(satir.unit_amount, dusulecek, precision_digits=2) <= 0:
                    dusulecek -= satir.unit_amount
                    satir.unlink()
                else:
                    satir.unit_amount -= dusulecek
                    dusulecek = 0
                if float_compare(dusulecek, 0.0, precision_digits=2) <= 0:
                    break
        return True

    @api.model
    def atlas_hafta_onayla(self, baslangic, employee_id):
        if not self._atlas_onaylayici_mi():
            raise AccessError(self.env._('Zaman kayıtlarını yalnızca onaylayıcılar onaylayabilir.'))
        calisan = self._atlas_calisan(employee_id)
        bas = fields.Date.to_date(baslangic)
        satirlar = self.sudo().search([('employee_id', '=', calisan.id), ('project_id', '!=', False), ('atlas_onayli', '=', False),
                                       ('date', '>=', bas), ('date', '<=', bas + timedelta(days=6))])
        satirlar.action_atlas_onayla()
        return len(satirlar)

    # -------------------------------------------------------------------------
    # Hatırlatmalar
    # -------------------------------------------------------------------------

    @api.model
    def _cron_atlas_hatirlatma(self):
        bugun = fields.Date.context_today(self)
        bas = bugun - timedelta(days=bugun.weekday() + 7)
        bit = bas + timedelta(days=6)
        sablon = self.env.ref('atlas_zaman.mail_template_zaman_eksik')
        for sirket in self.env['res.company'].search([('atlas_zaman_hatirlatma', '=', True)]):
            calisanlar = self.env['hr.employee'].search([('company_id', '=', sirket.id), ('user_id', '!=', False),
                                                         ('user_id.share', '=', False)])
            girilen = defaultdict(float)
            for calisan, toplam in self.sudo()._read_group(
                    [('employee_id', 'in', calisanlar.ids), ('project_id', '!=', False), ('date', '>=', bas), ('date', '<=', bit)],
                    ['employee_id'], ['unit_amount:sum']):
                girilen[calisan.id] = toplam
            for calisan in calisanlar:
                beklenen = sum(self._atlas_beklenen(calisan, bas, bit).values())
                if beklenen and girilen[calisan.id] < beklenen * 0.9:
                    sablon.with_context(atlas_bas=bas, atlas_bit=bit, atlas_girilen=girilen[calisan.id],
                                        atlas_beklenen=beklenen).send_mail(calisan.id, force_send=False)
        onay_sablon = self.env.ref('atlas_zaman.mail_template_zaman_onay')
        for sirket in self.env['res.company'].search([('atlas_zaman_onay_hatirlatma', '=', True)]):
            bekleyen = self.sudo()._read_group(
                [('company_id', '=', sirket.id), ('project_id', '!=', False), ('atlas_onayli', '=', False), ('date', '<=', bit),
                 ('manager_id.user_id', '!=', False)],
                ['manager_id'], ['__count'])
            for yonetici, sayi in bekleyen:
                onay_sablon.with_context(atlas_sayi=sayi).send_mail(yonetici.id, force_send=False)


class AtlasZamanSayac(models.Model):
    _name = 'atlas.zaman.sayac'
    _description = 'Zaman Sayacı'

    user_id = fields.Many2one('res.users', string='Kullanıcı', required=True, default=lambda self: self.env.user, index=True)
    employee_id = fields.Many2one('hr.employee', string='Çalışan', required=True)
    project_id = fields.Many2one('project.project', string='Proje', required=True)
    task_id = fields.Many2one('project.task', string='Görev')
    aciklama = fields.Char(string='Açıklama')
    baslangic = fields.Datetime(string='Başlangıç', required=True, default=fields.Datetime.now)

    _kullanici_uniq = models.UniqueIndex('(user_id)')

    def _atlas_bilgi(self):
        self.ensure_one()
        return {'id': self.id, 'project_id': self.project_id.id, 'project_ad': self.project_id.display_name,
                'task_id': self.task_id.id, 'task_ad': self.task_id.name or '', 'aciklama': self.aciklama or '',
                'baslangic': fields.Datetime.to_string(self.baslangic)}

    @api.model
    def atlas_durum(self):
        sayac = self.search([('user_id', '=', self.env.uid)], limit=1)
        return sayac._atlas_bilgi() if sayac else False

    @api.model
    def atlas_baslat(self, project_id, task_id=False, aciklama=False):
        mevcut = self.search([('user_id', '=', self.env.uid)], limit=1)
        if mevcut:
            mevcut.atlas_durdur()
        calisan = self.env['account.analytic.line']._atlas_calisan()
        if task_id and not project_id:
            project_id = self.env['project.task'].browse(int(task_id)).project_id.id
        sayac = self.create({'employee_id': calisan.id, 'project_id': int(project_id), 'task_id': int(task_id) if task_id else False,
                             'aciklama': aciklama or False})
        return sayac._atlas_bilgi()

    def _sure_saat(self, bitis=None):
        self.ensure_one()
        dakika = ((bitis or fields.Datetime.now()) - self.baslangic).total_seconds() / 60
        sirket = self.employee_id.company_id or self.env.company
        if sirket.atlas_zaman_yuvarlama > 0:
            dakika = math.ceil(dakika / sirket.atlas_zaman_yuvarlama) * sirket.atlas_zaman_yuvarlama
        dakika = max(dakika, sirket.atlas_zaman_minimum or 0)
        return round(dakika / 60, 2)

    def atlas_durdur(self):
        """Sayacı durdurur ve süreyi zaman kaydına yazar."""
        satirlar = self.env['account.analytic.line']
        for sayac in self:
            if sayac.user_id != self.env.user and not self.env.su:
                raise AccessError(self.env._('Başkasının sayacını durduramazsınız.'))
            satirlar |= self.env['account.analytic.line'].create({
                'employee_id': sayac.employee_id.id, 'project_id': sayac.project_id.id, 'task_id': sayac.task_id.id,
                'date': fields.Date.context_today(sayac, sayac.baslangic), 'unit_amount': sayac._sure_saat(),
                'name': sayac.aciklama or '/',
            })
        self.unlink()
        return [{'id': s.id, 'saat': s.unit_amount} for s in satirlar]

    def atlas_iptal(self):
        self.filtered(lambda s: s.user_id == self.env.user or self.env.su).unlink()
        return True


class ProjectTask(models.Model):
    _inherit = 'project.task'

    atlas_sayac_calisiyor = fields.Boolean(compute='_compute_atlas_sayac')

    @api.depends_context('uid')
    def _compute_atlas_sayac(self):
        sayac = self.env['atlas.zaman.sayac'].search([('user_id', '=', self.env.uid)], limit=1)
        for task in self:
            task.atlas_sayac_calisiyor = bool(sayac) and sayac.task_id == task

    def action_atlas_sayac_baslat(self):
        self.ensure_one()
        if not self.project_id.allow_timesheets:
            raise UserError(self.env._('%s projesinde zaman kaydı kapalı.', self.project_id.name))
        self.env['atlas.zaman.sayac'].atlas_baslat(self.project_id.id, self.id)
        return True

    def action_atlas_sayac_durdur(self):
        sayac = self.env['atlas.zaman.sayac'].search([('user_id', '=', self.env.uid)], limit=1)
        satirlar = sayac.atlas_durdur()
        saat = satirlar[0]['saat'] if satirlar else 0
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('%s saat zaman kaydına yazıldı.', f'{saat:.2f}'),
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
