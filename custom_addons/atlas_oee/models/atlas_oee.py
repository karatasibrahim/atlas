from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.atlas_rapor.wizard.atlas_rapor_wizard import col


def _oran(pay, payda):
    return round(100.0 * pay / payda, 1) if payda else None


class AtlasRaporWizard(models.TransientModel):
    _inherit = 'atlas.rapor.wizard'

    rapor_turu = fields.Selection(selection_add=[('oee', 'OEE (Toplam Ekipman Etkinliği)')], ondelete={'oee': 'cascade'})
    workcenter_ids = fields.Many2many('mrp.workcenter', string='İş Merkezleri', help='Boşsa tümü.')

    def _oee_aralik(self):
        tz_bas = datetime.combine(self.date_from, time())
        tz_bit = datetime.combine(self.date_to + timedelta(days=1), time())
        # Kullanıcı saat diliminde gün sınırları → UTC
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self.env.user.tz or 'Europe/Istanbul')
        donustur = lambda dt: dt.replace(tzinfo=tz).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        return donustur(tz_bas), donustur(tz_bit)

    def _oee_veri(self):
        """{workcenter: {...}} ve duruş nedenleri listesi."""
        self._require_date_from()
        bas, bit = self._oee_aralik()
        merkezler = self.workcenter_ids or self.env['mrp.workcenter'].search(
            [('company_id', 'in', (False, self.company_id.id))])
        loglar = self.env['mrp.workcenter.productivity'].search([
            ('workcenter_id', 'in', merkezler.ids), ('date_start', '<', bit),
            '|', ('date_end', '=', False), ('date_end', '>', bas)])
        simdi = fields.Datetime.now()
        veri = {wc: defaultdict(float) for wc in merkezler}
        nedenler = defaultdict(lambda: [0.0, 0])
        for log in loglar:
            # Dönem dışına taşan kısım kırpılır
            s, e = max(log.date_start, bas), min(log.date_end or simdi, bit)
            if e <= s:
                continue
            dk = (e - s).total_seconds() / 60.0
            d = veri[log.workcenter_id]
            if log.loss_type in ('productive', 'performance'):
                d['calisma'] += dk
            elif log.loss_type in ('availability', 'quality'):
                d['durus'] += dk
                nedenler[(log.workcenter_id, log.loss_id)][0] += dk
                nedenler[(log.workcenter_id, log.loss_id)][1] += 1
        # Dönemde biten iş emirleri: ideal süre ve adetler
        bitenler = self.env['mrp.workorder'].search([
            ('workcenter_id', 'in', merkezler.ids), ('state', '=', 'done'),
            ('date_finished', '>=', bas), ('date_finished', '<', bit)])
        for wo in bitenler:
            d = veri[wo.workcenter_id]
            toplam_adet = wo.qty_produced + wo.atlas_hatali_adet
            if wo.qty_production:
                d['ideal'] += wo.duration_expected * toplam_adet / wo.qty_production
            d['saglam'] += wo.qty_produced
            d['hatali'] += wo.atlas_hatali_adet
            d['is_emri'] += 1
        return veri, nedenler

    def _report_oee(self):
        veri, nedenler = self._oee_veri()
        rows = []
        toplam = defaultdict(float)

        def satir(etiket, d, stil='detail', kod=''):
            planlanan = d['calisma'] + d['durus']
            k = d['calisma'] / planlanan if planlanan else 0.0
            p = d['ideal'] / d['calisma'] if d['calisma'] else 0.0
            adet = d['saglam'] + d['hatali']
            ka = d['saglam'] / adet if adet else (1.0 if d['calisma'] else 0.0)
            oee = k * min(p, 1.0) * ka
            return self._row([kod, etiket, round(planlanan / 60, 2), round(d['calisma'] / 60, 2), round(d['durus'] / 60, 2),
                              _oran(d['calisma'], planlanan), _oran(d['ideal'], d['calisma']),
                              int(d['saglam']) if d['saglam'] == int(d['saglam']) else d['saglam'],
                              int(d['hatali']) if d['hatali'] == int(d['hatali']) else d['hatali'],
                              _oran(d['saglam'], adet) if adet else None,
                              round(100 * oee, 1) if planlanan else None], stil)

        for wc in sorted(veri, key=lambda w: w.name):
            d = veri[wc]
            if self.sadece_hareketli and not (d['calisma'] or d['durus'] or d['is_emri']):
                continue
            rows.append(satir(wc.name, d, kod=wc.code or ''))
            for anahtar, deger in d.items():
                toplam[anahtar] += deger
        rows.append(satir('TOPLAM', toplam, 'total'))
        # Duruş nedenleri (Pareto)
        if nedenler:
            toplam_durus = sum(v[0] for v in nedenler.values())
            rows.append(self._row(['', 'DURUŞ NEDENLERİ (PARETO)'] + [None] * 9, 'group'))
            birikimli = 0.0
            for (wc, loss), (dk, adet) in sorted(nedenler.items(), key=lambda kv: -kv[1][0]):
                birikimli += dk
                rows.append(self._row([wc.code or wc.name, f'{loss.name} ({adet} kez)', None, None, round(dk / 60, 2),
                                       None, None, None, None, None, None]))
                rows[-1]['cells'][5] = _oran(dk, toplam_durus)
                rows[-1]['cells'][6] = _oran(birikimli, toplam_durus)
        return {
            'title': 'OEE — Toplam Ekipman Etkinliği',
            'columns': [col('Kod', 'text', 10), col('İş Merkezi', 'text', 30), col('Planlanan (sa)', 'number', 12),
                        col('Çalışma (sa)', 'number', 12), col('Duruş (sa)', 'number', 11), col('Kullanılabilirlik %', 'number', 13),
                        col('Performans %', 'number', 12), col('Sağlam', 'number', 9), col('Hatalı', 'number', 9),
                        col('Kalite %', 'number', 10), col('OEE %', 'number', 10)],
            'rows': rows,
            'landscape': True,
        }
