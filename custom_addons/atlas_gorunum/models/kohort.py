from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
DONEM_SAYISI = {'day': 15, 'week': 15, 'month': 15, 'year': 10}


def _bas(t, aralik):
    if aralik == 'week':
        return t - timedelta(days=t.weekday())
    if aralik == 'month':
        return t.replace(day=1)
    if aralik == 'year':
        return t.replace(month=1, day=1)
    return t


def _adim(aralik, n=1):
    return {'day': relativedelta(days=n), 'week': relativedelta(weeks=n), 'month': relativedelta(months=n),
            'year': relativedelta(years=n)}[aralik]


def _etiket(t, aralik):
    if aralik == 'week':
        return f'{t.isocalendar()[1]}. hafta {t.isocalendar()[0]}'
    if aralik == 'month':
        return f'{AYLAR[t.month - 1]} {t.year}'
    if aralik == 'year':
        return str(t.year)
    return t.strftime('%d.%m.%Y')


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def atlas_kohort_verisi(self, domain, date_start, date_stop, interval='month', measure='__count', mode='retention'):
        """Kohort tablosu: başlangıç tarihine göre gruplar; her sonraki dönemde kalan (retention) ya da ayrılan (churn) oran."""
        if interval not in DONEM_SAYISI or mode not in ('retention', 'churn'):
            raise UserError(self.env._('Geçersiz kohort parametresi.'))
        for ad in (date_start, date_stop) + ((measure,) if measure != '__count' else ()):
            if ad not in self._fields:
                raise UserError(self.env._('Alan yok: %s', ad))
        okunacak = [date_start, date_stop] + ([measure] if measure != '__count' else [])
        kayitlar = self.search_read(domain or [], okunacak, limit=50000)

        def gun(deger):
            if not deger:
                return None
            if isinstance(deger, datetime):
                return fields.Datetime.context_timestamp(self, deger).date()
            if isinstance(deger, date):
                return deger
            d = fields.Datetime.to_datetime(deger) if len(str(deger)) > 10 else fields.Date.to_date(deger)
            return gun(d)

        gruplar = {}
        for k in kayitlar:
            bas = gun(k[date_start])
            if not bas:
                continue
            gruplar.setdefault(_bas(bas, interval), []).append((gun(k[date_stop]), 1.0 if measure == '__count' else (k[measure] or 0.0)))
        bugun = fields.Date.context_today(self)
        n = DONEM_SAYISI[interval]
        satirlar = []
        sutun_toplam = [[] for _ in range(n)]
        for kohort in sorted(gruplar):
            uyeler = gruplar[kohort]
            toplam = sum(v for _b, v in uyeler)
            hucreler = []
            for i in range(n):
                donem_bas = kohort + _adim(interval, i)
                donem_bit = kohort + _adim(interval, i + 1)
                if donem_bas > bugun:
                    hucreler.append(None)
                    continue
                ayrilan = sum(v for bitis, v in uyeler if bitis and bitis < donem_bit)
                deger = ayrilan if mode == 'churn' else toplam - ayrilan
                yuzde = round(100.0 * deger / toplam, 1) if toplam else 0.0
                hucreler.append({'deger': deger, 'yuzde': yuzde, 'bit': fields.Date.to_string(donem_bit)})
                sutun_toplam[i].append(yuzde)
            satirlar.append({'bas': fields.Date.to_string(kohort), 'bit': fields.Date.to_string(kohort + _adim(interval)),
                             'etiket': _etiket(kohort, interval), 'deger': toplam, 'adet': len(uyeler), 'hucreler': hucreler})
        ortalama = [round(sum(s) / len(s), 1) if s else None for s in sutun_toplam]
        return {'satirlar': satirlar, 'ortalama': ortalama, 'donem_sayisi': n,
                'toplam': sum(s['deger'] for s in satirlar)}
