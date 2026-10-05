"""Etkileşimli finansal rapor motoru.

Her rapor türü bir "işleyici" sınıfıdır: kolonları, kök satırları ve bir satırın alt satırlarını üretir.
Satır sözlüğü:
    anahtar   : benzersiz yol ("tanim:5|hesap:120")
    ad        : görünen ad
    seviye    : girinti
    acilabilir: alt satırı var mı
    acik      : açık gösteriliyor mu
    sinif     : baslik / toplam / normal / kalem / daha
    degerler  : kolon başına değer (sayı, metin ya da None)
    denetim   : kolon başına {'model', 'domain'} ya da None (tutara tıklayınca açılan kayıtlar)
    bicim     : para / yuzde / oran / gun (tanım satırları için)
"""
import re
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tools.safe_eval import safe_eval

SAYFA = 100
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
YASLANDIRMA = [('vadesiz', 'Vadesi Gelmemiş', None, 0), ('g30', '1-30', 1, 30), ('g60', '31-60', 31, 60), ('g90', '61-90', 61, 90),
               ('g120', '91-120', 91, 120), ('eski', '120+', 121, None)]


def kalem_adi(kalem, *ekler):
    """Fiş no + (fiş nosundan farklıysa) açıklama + ekler."""
    parcalar = [kalem.move_id.name or '']
    if kalem.name and kalem.name != kalem.move_id.name:
        parcalar.append(kalem.name)
    parcalar += [e for e in ekler if e]
    return ' '.join(parcalar)


def kolon(ad, tur='para'):
    return {'ad': ad, 'tur': tur}


def kod_uyar(kod, tanim):
    """'600,601,!6019' → 600 ve 601 ile başlayan, 6019 ile başlamayan kodlar."""
    if not kod:
        return False
    dahil = haric = False
    for parca in (tanim or '').replace(' ', '').split(','):
        if not parca:
            continue
        if parca.startswith('!'):
            if kod.startswith(parca[1:]):
                haric = True
        elif kod.startswith(parca):
            dahil = True
    return dahil and not haric


def _tarih(deger, varsayilan):
    if not deger:
        return varsayilan
    return fields.Date.to_date(deger)


def donem_etiketi(bas, bit, tek):
    if tek or not bas:
        return bit.strftime('%d.%m.%Y')
    if bas.day == 1 and (bit + timedelta(days=1)).day == 1:
        aylar = (bit.year - bas.year) * 12 + bit.month - bas.month + 1
        if aylar == 12 and bas.month == 1:
            return str(bas.year)
        if aylar == 1:
            return f'{AYLAR[bas.month - 1]} {bas.year}'
        if aylar == 3 and bas.month in (1, 4, 7, 10):
            return f'{(bas.month - 1) // 3 + 1}. Çeyrek {bas.year}'
    return f'{bas.strftime("%d.%m.%Y")} - {bit.strftime("%d.%m.%Y")}'


class Baglam:
    """Bir rapor isteğinin seçenekleri, dönemleri ve ortak yardımcıları."""

    def __init__(self, rapor, secenekler):
        self.rapor = rapor
        self.env = rapor.env
        s = dict(secenekler or {})
        bugun = fields.Date.context_today(rapor)
        self.sirketler = self.env.companies
        self.sirket = self.env.company
        self.para = self.sirket.currency_id
        self.tek = rapor.tarih_modu == 'tek'
        yil_sonu = rapor.env.company.compute_fiscalyear_dates(bugun)['date_to']
        bit = _tarih(s.get('tarih_bit'), bugun if self.tek else yil_sonu)
        bas = _tarih(s.get('tarih_bas'), rapor.env.company.compute_fiscalyear_dates(bit)['date_from'])
        if bas > bit:
            bas = bit
        kars = s.get('karsilastirma') or {}
        tur = kars.get('tur') if rapor.karsilastirma else 'yok'
        adet = max(0, min(int(kars.get('adet') or 1), 12)) if tur in ('onceki', 'gecen_yil') else 0
        self.donemler = [(bas, bit)]
        for i in range(1, adet + 1):
            if tur == 'gecen_yil':
                self.donemler.append((bas - relativedelta(years=i), bit - relativedelta(years=i)))
            else:
                bas0, bit0 = self.donemler[-1]
                if bas0.day == 1 and (bit0 + timedelta(days=1)).day == 1:
                    aylar = (bit0.year - bas0.year) * 12 + bit0.month - bas0.month + 1
                    yeni_bas = bas0 - relativedelta(months=aylar)
                    self.donemler.append((yeni_bas, bas0 - timedelta(days=1)))
                else:
                    gun = (bit0 - bas0).days + 1
                    self.donemler.append((bas0 - timedelta(days=gun), bas0 - timedelta(days=1)))
        self.etiketler = [donem_etiketi(b, e, self.tek) for b, e in self.donemler]
        self.buyume = bool(s.get('buyume')) and len(self.donemler) == 2
        self.taslak = bool(s.get('taslak'))
        self.sifir_gizle = s.get('sifir_gizle', True)
        self.tumunu_ac = bool(s.get('tumunu_ac'))
        self.acik = set(s.get('acik') or [])
        self.kapali = set(s.get('kapali') or [])
        self.yevmiye_ids = [int(i) for i in s.get('yevmiye_ids') or []]
        self.partner_ids = [int(i) for i in s.get('partner_ids') or []]
        self.analitik_ids = [int(i) for i in s.get('analitik_ids') or []]
        self.hesap_filtre = (s.get('hesap_filtre') or '').strip()
        self.seviye = str(s.get('seviye') or rapor.varsayilan_seviye or '3')
        self.cari_turu = s.get('cari_turu') or 'alacak'
        self.arama = (s.get('arama') or '').strip().lower()
        self.secenekler = {
            'tarih_bas': fields.Date.to_string(bas), 'tarih_bit': fields.Date.to_string(bit),
            'karsilastirma': {'tur': tur or 'yok', 'adet': adet or 1}, 'buyume': self.buyume, 'taslak': self.taslak,
            'sifir_gizle': self.sifir_gizle, 'tumunu_ac': self.tumunu_ac, 'acik': sorted(self.acik), 'kapali': sorted(self.kapali),
            'yevmiye_ids': self.yevmiye_ids, 'partner_ids': self.partner_ids, 'analitik_ids': self.analitik_ids,
            'hesap_filtre': self.hesap_filtre, 'seviye': self.seviye, 'cari_turu': self.cari_turu, 'arama': s.get('arama') or '',
        }
        self._hesap_kod = {}

    # ---------------------------------------------------------------- alanlar
    def taban(self, kapanis_haric=None, partner=True):
        durum = ['posted', 'draft'] if self.taslak else ['posted']
        alan = [('company_id', 'in', self.sirketler.ids), ('parent_state', 'in', durum),
                ('display_type', 'not in', ('line_section', 'line_note'))]
        if self.yevmiye_ids:
            alan.append(('journal_id', 'in', self.yevmiye_ids))
        if partner and self.partner_ids:
            alan.append(('partner_id', 'in', self.partner_ids))
        if self.analitik_ids:
            alan.append(('analytic_distribution', 'in', self.analitik_ids))
        return alan

    def kapanis_alani(self, kesim):
        """Kesim tarihinden sonraki kapanış fişleri hariç (önceki yılların kapanışı devir için dahil)."""
        if not self.rapor.kapanis_haric or 'atlas_fis_turu' not in self.env['account.move']._fields:
            return []
        return ['|', ('move_id.atlas_fis_turu', '!=', 'kapanis'), ('date', '<', kesim)]

    def mali_yil_basi(self, tarih):
        return self.sirket.compute_fiscalyear_dates(tarih)['date_from']

    def tarih_alani(self, donem, tur):
        bas, bit = donem
        if tur in ('bakiye',):
            return [('date', '<=', bit)] + self.kapanis_alani(self.mali_yil_basi(bit))
        if tur == 'acilis':
            return [('date', '<', bas)] + self.kapanis_alani(self.mali_yil_basi(bas))
        if tur == 'mali_yil':
            fy = self.mali_yil_basi(bit)
            return [('date', '>=', fy), ('date', '<=', bit)] + self.kapanis_alani(fy)
        if tur == 'mali_yil_oncesi':
            fy = self.mali_yil_basi(bit)
            return [('date', '<', fy)] + self.kapanis_alani(fy)
        return [('date', '>=', bas), ('date', '<=', bit)] + self.kapanis_alani(bas)

    def hesap_kodu(self, hesap):
        if hesap.id not in self._hesap_kod:
            self._hesap_kod[hesap.id] = hesap.with_company(self.sirket).code or ''
        return self._hesap_kod[hesap.id]

    def toplamlar(self, alan, grup=('account_id',)):
        """{grup değeri(leri): (bakiye, borç, alacak)}"""
        sonuc = {}
        for satir in self.env['account.move.line']._read_group(alan, list(grup), ['balance:sum', 'debit:sum', 'credit:sum']):
            anahtar = satir[0] if len(grup) == 1 else tuple(satir[:len(grup)])
            sonuc[anahtar] = tuple(x or 0.0 for x in satir[len(grup):])
        return sonuc

    def hesap_filtresine_uyar(self, kod):
        if not self.hesap_filtre:
            return True
        if '-' in self.hesap_filtre and ',' not in self.hesap_filtre:
            ilk, son = [p.strip() for p in self.hesap_filtre.split('-', 1)]
            return ilk <= kod[:len(ilk)] and kod[:len(son)] <= son
        return kod_uyar(kod, self.hesap_filtre)

    def denetim(self, alan, model='account.move.line'):
        return {'model': model, 'domain': alan}

    def acik_mi(self, anahtar, varsayilan=False):
        if anahtar in self.kapali:
            return False
        return self.tumunu_ac or anahtar in self.acik or varsayilan


class Isleyici:
    """Rapor türü temel sınıfı."""
    sayfalama = False

    def __init__(self, b):
        self.b = b
        self.env = b.env

    def kolonlar(self):
        raise NotImplementedError

    def kok(self):
        raise NotImplementedError

    def cocuklar(self, anahtar, offset=0):
        return []

    def varsayilan_acik(self, satir):
        return False

    def satir(self, anahtar, ad, seviye, degerler, denetim=None, acilabilir=False, sinif='normal', **ek):
        s = {'anahtar': anahtar, 'ad': ad, 'seviye': seviye, 'degerler': degerler, 'denetim': denetim or [None] * len(degerler),
             'acilabilir': acilabilir, 'sinif': sinif, 'acik': False}
        s.update(ek)
        return s

    @staticmethod
    def bos_mu(satir):
        return all(not v for v in satir['degerler'] if isinstance(v, (int, float)) and not isinstance(v, bool))

    def genislet(self, satirlar):
        """Açık satırların alt satırlarını (özyinelemeli) ekler."""
        sonuc = []
        for s in satirlar:
            if self.b.sifir_gizle and s['sinif'] in ('normal', 'kalem') and not s.get('sifir_goster') and self.bos_mu(s):
                continue
            if self.b.arama and s['sinif'] == 'normal' and s['seviye'] > 0 and self.b.arama not in s['ad'].lower() \
                    and not s['acilabilir']:
                continue
            sonuc.append(s)
            if s['acilabilir'] and self.b.acik_mi(s['anahtar'], self.varsayilan_acik(s)):
                s['acik'] = True
                sonuc.extend(self.genislet(self.cocuklar(s['anahtar'])))
        return sonuc


# ====================================================================== Tanımlı satırlar (Bilanço, Gelir, Yönetici Özeti)
class Tanim(Isleyici):

    def __init__(self, b):
        super().__init__(b)
        self.satirlar = b.rapor.satir_ids.sorted(lambda s: (s.sira, s.id))
        self.kodlu = {s.kod: s for s in self.satirlar if s.kod}
        self._toplam_onbellek = {}
        self._deger = {}

    def kolonlar(self):
        k = [kolon(e) for e in self.b.etiketler]
        if self.b.buyume:
            k.append(kolon('%', 'yuzde'))
        return k

    def _hesap_toplamlari(self, di, tur):
        anahtar = (di, tur)
        if anahtar not in self._toplam_onbellek:
            alan = self.b.taban() + self.b.tarih_alani(self.b.donemler[di], tur)
            self._toplam_onbellek[anahtar] = self.b.toplamlar(alan)
        return self._toplam_onbellek[anahtar]

    def _hesaplar(self, satir, di):
        """Satırın hesap tanımına uyan {hesap: (bakiye, borç, alacak)}"""
        return {h: v for h, v in self._hesap_toplamlari(di, satir.donem_turu).items()
                if h and kod_uyar(self.b.hesap_kodu(h), satir.hesaplar)}

    @staticmethod
    def _secim(satir, deger):
        bakiye, borc, alacak = deger
        if satir.donem_turu == 'borc':
            return borc
        if satir.donem_turu == 'alacak':
            return alacak
        return bakiye

    def deger(self, satir, di):
        anahtar = (satir.id, di)
        if anahtar in self._deger:
            return self._deger[anahtar]
        self._deger[anahtar] = 0.0  # döngüsel formüllere karşı
        if satir.motor == 'hesap':
            v = satir.isaret * sum(self._secim(satir, d) for d in self._hesaplar(satir, di).values())
        elif satir.motor == 'toplam':
            v = sum(self.deger(c, di) for c in self.satirlar.filtered(lambda c: c.parent_id == satir) if c.bicim == 'para')
        elif satir.motor == 'formul':
            bas, bit = self.b.donemler[di]
            degiskenler = {'GUN': (bit - bas).days + 1, 'abs': abs, 'min': min, 'max': max}
            for kod in set(re.findall(r'\b[A-Z][A-Z0-9_]*\b', satir.formul or '')):
                if kod in self.kodlu:
                    degiskenler[kod] = self.deger(self.kodlu[kod], di)
            try:
                v = float(safe_eval(satir.formul or '0', degiskenler))
            except ZeroDivisionError:
                v = 0.0
        else:
            v = 0.0
        self._deger[anahtar] = v
        return v

    def _degerler(self, satir_degerleri):
        if self.b.buyume:
            simdi, once = satir_degerleri[0], satir_degerleri[1]
            satir_degerleri = satir_degerleri + [((simdi - once) / abs(once) * 100) if once else None]
        return satir_degerleri

    def _denetim(self, satir, di):
        if satir.motor != 'hesap':
            return None
        hesaplar = [h.id for h in self._hesaplar(satir, di)]
        return self.b.denetim(self.b.taban() + self.b.tarih_alani(self.b.donemler[di], satir.donem_turu) + [('account_id', 'in', hesaplar)])

    def kok(self):
        sonuc = []
        for s in self.satirlar:
            if s.gizli:
                continue
            seviye = 0
            ust = s.parent_id
            while ust:
                seviye += 1
                ust = ust.parent_id
            degerler = [self.deger(s, i) for i in range(len(self.b.donemler))]
            sinif = 'baslik' if s.motor == 'baslik' else ('toplam' if s.kalin else 'normal')
            if s.motor == 'baslik':
                degerler = [None] * len(degerler)
            satir = self.satir(f'tanim:{s.id}', s.name, seviye, self._degerler(degerler),
                               [self._denetim(s, i) for i in range(len(self.b.donemler))] + ([None] if self.b.buyume else []),
                               acilabilir=s.motor == 'hesap' and s.acilabilir, sinif=sinif, bicim=s.bicim,
                               sifir_goster=not s.gizle_sifir)
            if s.gizle_sifir and all(not v for v in degerler):
                continue
            sonuc.append(satir)
        return sonuc

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if not son.startswith('tanim:'):
            return []
        satir = self.b.rapor.satir_ids.browse(int(son.split(':')[1]))
        hesaplar = {}
        for di in range(len(self.b.donemler)):
            for h, d in self._hesaplar(satir, di).items():
                hesaplar.setdefault(h, [0.0] * len(self.b.donemler))[di] = satir.isaret * self._secim(satir, d)
        sonuc = []
        for h in sorted(hesaplar, key=self.b.hesap_kodu):
            alan = [self.b.denetim(self.b.taban() + self.b.tarih_alani(self.b.donemler[di], satir.donem_turu) + [('account_id', '=', h.id)])
                    for di in range(len(self.b.donemler))]
            sonuc.append(self.satir(f'{anahtar}|hesap:{h.id}', f'{self.b.hesap_kodu(h)} {h.name}', 0, self._degerler(hesaplar[h]),
                                    alan + ([None] if self.b.buyume else []), bicim=satir.bicim, girinti=1))
        return sonuc


# ====================================================================== Mizan
class Mizan(Isleyici):

    def kolonlar(self):
        return [kolon('Açılış Bakiyesi'), kolon('Dönem Borç'), kolon('Dönem Alacak'), kolon('Toplam Borç'), kolon('Toplam Alacak'),
                kolon('Borç Bakiye'), kolon('Alacak Bakiye')]

    def _veri(self):
        if not hasattr(self, '_v'):
            bas, bit = self.b.donemler[0]
            acilis = self.b.toplamlar(self.b.taban() + self.b.tarih_alani((bas, bit), 'acilis'))
            donem = self.b.toplamlar(self.b.taban() + self.b.tarih_alani((bas, bit), 'hareket'))
            veri = {}
            for h in set(acilis) | set(donem):
                if not h:
                    continue
                kod = self.b.hesap_kodu(h)
                if not self.b.hesap_filtresine_uyar(kod):
                    continue
                a = acilis.get(h, (0, 0, 0))
                d = donem.get(h, (0, 0, 0))
                veri[h] = (kod, a[0], d[1], d[2], a[1] + d[1], a[2] + d[2])
            self._v = veri
            from odoo.addons.atlas_rapor.models.tdhp import tdhp_names
            self._adlar = tdhp_names()
        return self._v

    def _toplam_satir(self, anahtar, ad, seviye, kalemler, acilabilir, alan_on):
        acilis = sum(k[1] for k in kalemler)
        borc = sum(k[2] for k in kalemler)
        alacak = sum(k[3] for k in kalemler)
        tb = sum(k[4] for k in kalemler)
        ta = sum(k[5] for k in kalemler)
        bakiye = tb - ta
        degerler = [acilis, borc, alacak, tb, ta, bakiye if bakiye > 0 else 0.0, -bakiye if bakiye < 0 else 0.0]
        bas, bit = self.b.donemler[0]
        tum = self.b.taban() + self.b.tarih_alani((bas, bit), 'bakiye') + alan_on
        donem = self.b.taban() + self.b.tarih_alani((bas, bit), 'hareket') + alan_on
        acil = self.b.taban() + self.b.tarih_alani((bas, bit), 'acilis') + alan_on
        denetim = [self.b.denetim(acil), self.b.denetim(donem), self.b.denetim(donem)] + [self.b.denetim(tum)] * 4
        return self.satir(anahtar, ad, seviye, degerler, denetim, acilabilir=acilabilir,
                          sinif='normal' if not acilabilir or seviye >= 3 else 'toplam')

    def _grup(self, onek):
        return [(h, v) for h, v in self._veri().items() if v[0].startswith(onek)]

    def kok(self):
        veri = self._veri()
        siniflar = sorted({v[0][:1] for v in veri.values() if v[0]})
        sonuc = [self._seviye_satiri('', s, 1) for s in siniflar]
        kalemler = list(veri.values())
        if kalemler:
            sonuc.append(self.satir('toplam', 'GENEL TOPLAM', 0, [sum(k[1] for k in kalemler), sum(k[2] for k in kalemler),
                                    sum(k[3] for k in kalemler), sum(k[4] for k in kalemler), sum(k[5] for k in kalemler),
                                    sum(max(k[4] - k[5], 0) for k in kalemler), sum(max(k[5] - k[4], 0) for k in kalemler)],
                                    sinif='toplam', sifir_goster=True))
        return sonuc

    def _seviye_satiri(self, ust, onek, seviye):
        grup = self._grup(onek)
        ad = self._adlar.get(onek, '')
        if isinstance(ad, (tuple, list)):
            ad = ad[0]
        hesaplar = [h for h, _v in grup]
        tek_hesap = len(grup) == 1 and grup[0][1][0] == onek
        acilabilir = not tek_hesap and (seviye < 3 or any(len(v[0]) > 3 for _h, v in grup))
        anahtar = f'{ust}|grup:{onek}' if ust else f'grup:{onek}'
        return self._toplam_satir(anahtar, f'{onek} {ad}'.strip(), seviye - 1, [v for _h, v in grup], acilabilir,
                                  [('account_id', 'in', hesaplar)])

    def varsayilan_acik(self, satir):
        if not satir['anahtar'].split('|')[-1].startswith('grup:'):
            return False
        onek = satir['anahtar'].split('|')[-1][5:]
        return len(onek) < int(self.b.seviye if self.b.seviye != '4' else 4) or self.b.seviye == '4'

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if not son.startswith('grup:'):
            return []
        onek = son[5:]
        if len(onek) < 3:
            alt = sorted({v[0][:len(onek) + 1] for _h, v in self._grup(onek) if len(v[0]) > len(onek)})
            return [self._seviye_satiri(anahtar, a, len(a)) for a in alt]
        sonuc = []
        for h, v in sorted(self._grup(onek), key=lambda x: x[1][0]):
            if v[0] == onek:
                continue
            sonuc.append(self._toplam_satir(f'{anahtar}|hesap:{h.id}', f'{v[0]} {h.name}', 3, [v], False, [('account_id', '=', h.id)]))
        return sonuc


# ====================================================================== Büyük defter ve cari defter
class Defter(Isleyici):
    """Hesap (ya da cari) satırları → açılış + yevmiye kalemleri (yürüyen bakiye, sayfalı)."""
    sayfalama = True
    grup_alani = 'account_id'

    def kolonlar(self):
        return [kolon('Tarih', 'tarih'), kolon('Fiş', 'metin'), kolon('Açıklama', 'metin'), kolon('Cari', 'metin'),
                kolon('Borç'), kolon('Alacak'), kolon('Bakiye')]

    def ek_alan(self):
        return []

    def _gruplar(self):
        bas, bit = self.b.donemler[0]
        taban = self.b.taban() + self.ek_alan()
        acilis = self.b.toplamlar(taban + self.b.tarih_alani((bas, bit), 'acilis'), (self.grup_alani,))
        donem = self.b.toplamlar(taban + self.b.tarih_alani((bas, bit), 'hareket'), (self.grup_alani,))
        return acilis, donem

    def grup_adi(self, kayit):
        return f'{self.b.hesap_kodu(kayit)} {kayit.name}'

    def grup_uyar(self, kayit):
        return self.b.hesap_filtresine_uyar(self.b.hesap_kodu(kayit))

    def sirala(self, kayitlar):
        return sorted(kayitlar, key=self.b.hesap_kodu)

    def kok(self):
        acilis, donem = self._gruplar()
        kayitlar = [k for k in set(acilis) | set(donem) if k and self.grup_uyar(k)]
        sonuc = []
        toplam = [0.0, 0.0, 0.0]
        bas, bit = self.b.donemler[0]
        for k in self.sirala(kayitlar):
            a = acilis.get(k, (0, 0, 0))
            d = donem.get(k, (0, 0, 0))
            bakiye = a[0] + d[0]
            alan = self.b.taban() + self.ek_alan() + [(self.grup_alani, '=', k.id)]
            sonuc.append(self.satir(f'{self.on_ek}:{k.id}', self.grup_adi(k), 0, [None, None, None, None, d[1], d[2], bakiye],
                                    [None] * 4 + [self.b.denetim(alan + self.b.tarih_alani((bas, bit), 'hareket'))] * 2 +
                                    [self.b.denetim(alan + self.b.tarih_alani((bas, bit), 'bakiye'))], acilabilir=True))
            toplam[0] += d[1]
            toplam[1] += d[2]
            toplam[2] += bakiye
        if sonuc:
            sonuc.append(self.satir('toplam', 'TOPLAM', 0, [None, None, None, None] + toplam, sinif='toplam', sifir_goster=True))
        return sonuc

    on_ek = 'hesap'

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        tur, _, kimlik = son.partition(':')
        if tur not in (self.on_ek, 'daha'):
            return []
        if tur == 'daha':
            kimlik, offset = kimlik.split('@')
            offset = int(offset)
            anahtar = anahtar.rsplit('|', 1)[0]
        kimlik = int(kimlik)
        bas, bit = self.b.donemler[0]
        taban = self.b.taban() + self.ek_alan() + [(self.grup_alani, '=', kimlik)]
        Aml = self.env['account.move.line']
        sonuc = []
        acilis = sum(Aml.search(taban + self.b.tarih_alani((bas, bit), 'acilis')).mapped('balance')) if offset == 0 else 0
        donem_alani = taban + self.b.tarih_alani((bas, bit), 'hareket')
        if offset == 0:
            yuruyen = acilis
            sonuc.append(self.satir(f'{anahtar}|acilis', 'Açılış Bakiyesi', 1, [None, None, None, None, None, None, acilis],
                                    [None] * 6 + [self.b.denetim(taban + self.b.tarih_alani((bas, bit), 'acilis'))], sinif='kalem',
                                    sifir_goster=True))
        else:
            onceki = Aml.search(donem_alani, order='date, move_name, id', limit=offset)
            yuruyen = sum(Aml.search(taban + self.b.tarih_alani((bas, bit), 'acilis')).mapped('balance')) + sum(onceki.mapped('balance'))
        kalemler = Aml.search(donem_alani, order='date, move_name, id', limit=SAYFA + 1, offset=offset)
        for k in kalemler[:SAYFA]:
            yuruyen += k.balance
            sonuc.append(self.satir(f'{anahtar}|kalem:{k.id}', k.name or k.move_id.name, 1,
                                    [fields.Date.to_string(k.date), k.move_id.name, k.name or '', self.dorduncu(k),
                                     k.debit, k.credit, yuruyen],
                                    [None] * 4 + [self.b.denetim([('id', '=', k.id)])] * 3, sinif='kalem', sifir_goster=True,
                                    kayit={'model': 'account.move', 'id': k.move_id.id}))
        if len(kalemler) > SAYFA:
            sonuc.append(self.satir(f'{anahtar}|daha:{kimlik}@{offset + SAYFA}', 'Daha fazla yükle…', 1, [None] * 7, sinif='daha'))
        return sonuc

    def dorduncu(self, k):
        return k.partner_id.name or ''


class Muavin(Defter):
    pass


class CariDefter(Defter):
    grup_alani = 'partner_id'
    on_ek = 'cari'

    def kolonlar(self):
        return [kolon('Tarih', 'tarih'), kolon('Fiş', 'metin'), kolon('Açıklama', 'metin'), kolon('Hesap', 'metin'),
                kolon('Borç'), kolon('Alacak'), kolon('Bakiye')]

    def ek_alan(self):
        turler = {'alacak': ['asset_receivable'], 'borc': ['liability_payable'],
                  'hepsi': ['asset_receivable', 'liability_payable']}[self.b.cari_turu]
        return [('account_id.account_type', 'in', turler), ('partner_id', '!=', False)]

    def grup_adi(self, kayit):
        return kayit.display_name

    def grup_uyar(self, kayit):
        return not self.b.arama or self.b.arama in (kayit.display_name or '').lower()

    def sirala(self, kayitlar):
        return sorted(kayitlar, key=lambda p: (p.display_name or '').lower())

    def dorduncu(self, k):
        return self.b.hesap_kodu(k.account_id)


# ====================================================================== Yaşlandırma
class Yaslandirma(Isleyici):
    hesap_turu = 'asset_receivable'
    isaret = 1

    def kolonlar(self):
        return [kolon('Vade', 'tarih')] + [kolon(e) for _k, e, _a, _b in YASLANDIRMA] + [kolon('Toplam')]

    def _acik_kalemler(self):
        if hasattr(self, '_kalemler'):
            return self._kalemler
        tarih = self.b.donemler[0][1]
        durum = ('posted', 'draft') if self.b.taslak else ('posted',)
        kosul, parametre = '', []
        if self.b.partner_ids:
            kosul += ' AND l.partner_id IN %s'
            parametre.append(tuple(self.b.partner_ids))
        if self.b.yevmiye_ids:
            kosul += ' AND l.journal_id IN %s'
            parametre.append(tuple(self.b.yevmiye_ids))
        self.env['account.move.line'].flush_model()
        self.env['account.partial.reconcile'].flush_model()
        self.env.cr.execute(f"""
            SELECT * FROM (
                SELECT l.id, l.partner_id, l.date, COALESCE(l.date_maturity, l.date) AS vade,
                       l.balance
                       - COALESCE((SELECT SUM(p.amount) FROM account_partial_reconcile p
                                   WHERE p.debit_move_id = l.id AND p.max_date <= %s), 0)
                       + COALESCE((SELECT SUM(p.amount) FROM account_partial_reconcile p
                                   WHERE p.credit_move_id = l.id AND p.max_date <= %s), 0) AS kalan
                  FROM account_move_line l
                  JOIN account_account a ON a.id = l.account_id
                 WHERE a.account_type = %s AND l.date <= %s AND l.parent_state IN %s AND l.company_id IN %s {kosul}
            ) x WHERE ROUND(x.kalan::numeric, 2) != 0
        """, [tarih, tarih, self.hesap_turu, tarih, durum, tuple(self.b.sirketler.ids)] + parametre)
        self._kalemler = self.env.cr.dictfetchall()
        return self._kalemler

    def _kova(self, vade):
        gun = (self.b.donemler[0][1] - vade).days
        for i, (_k, _e, a, z) in enumerate(YASLANDIRMA):
            if a is None and gun <= 0:
                return i
            if a is not None and gun >= a and (z is None or gun <= z):
                return i
        return 0

    def _degerler(self, kalemler):
        kovalar = [0.0] * len(YASLANDIRMA)
        for k in kalemler:
            kovalar[self._kova(k['vade'])] += self.isaret * k['kalan']
        return [None] + kovalar + [sum(kovalar)]

    def kok(self):
        gruplar = {}
        for k in self._acik_kalemler():
            gruplar.setdefault(k['partner_id'], []).append(k)
        Partner = self.env['res.partner']
        sonuc = []
        for pid in sorted(gruplar, key=lambda p: (Partner.browse(p).display_name or '').lower() if p else 'zzz'):
            ad = Partner.browse(pid).display_name if pid else 'Carisiz'
            if self.b.arama and self.b.arama not in (ad or '').lower():
                continue
            ids = [k['id'] for k in gruplar[pid]]
            sonuc.append(self.satir(f'cari:{pid or 0}', ad, 0, self._degerler(gruplar[pid]),
                                    [None] + [self.b.denetim([('id', 'in', ids)])] * (len(YASLANDIRMA) + 1), acilabilir=True))
        tum = self._acik_kalemler()
        if tum:
            sonuc.append(self.satir('toplam', 'TOPLAM', 0, self._degerler(tum), sinif='toplam', sifir_goster=True))
        return sonuc

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if not son.startswith('cari:'):
            return []
        pid = int(son[5:]) or None
        Aml = self.env['account.move.line']
        sonuc = []
        for k in sorted((k for k in self._acik_kalemler() if k['partner_id'] == pid), key=lambda k: (k['vade'], k['id'])):
            kalem = Aml.browse(k['id'])
            degerler = self._degerler([k])
            degerler[0] = fields.Date.to_string(k['vade'])
            sonuc.append(self.satir(f'{anahtar}|kalem:{k["id"]}', kalem_adi(kalem), 1, degerler,
                                    [None] + [self.b.denetim([('id', '=', k['id'])])] * (len(YASLANDIRMA) + 1), sinif='kalem',
                                    kayit={'model': 'account.move', 'id': kalem.move_id.id}))
        return sonuc


class YaslandirmaBorc(Yaslandirma):
    hesap_turu = 'liability_payable'
    isaret = -1


# ====================================================================== Nakit akış
class NakitAkis(Isleyici):
    """Doğrudan yöntem: nakit hesaplarına dokunan fişlerde karşı hesapların tutarı, karşı hesabın koduna göre sınıflanır."""

    def kolonlar(self):
        k = [kolon(e) for e in self.b.etiketler]
        if self.b.buyume:
            k.append(kolon('%', 'yuzde'))
        return k

    def _nakit_hesaplari(self):
        if not hasattr(self, '_nh'):
            tum = self.env['account.account'].search([('company_ids', 'in', self.b.sirketler.ids)])
            self._nh = tum.filtered(lambda h: kod_uyar(self.b.hesap_kodu(h), self.b.rapor.nakit_hesaplari or '100,102,108'))
        return self._nh

    def _karsi(self, di):
        """{hesap: nakit etkisi} — nakit hesaplarına dokunan fişlerin nakit dışı satırları."""
        if not hasattr(self, '_k'):
            self._k = {}
        if di in self._k:
            return self._k[di]
        nakit = self._nakit_hesaplari()
        alan = self.b.taban(partner=False) + self.b.tarih_alani(self.b.donemler[di], 'hareket')
        fisler = self.env['account.move.line'].search(alan + [('account_id', 'in', nakit.ids)]).move_id
        sonuc = {}
        if fisler:
            for h, (bakiye, _b, _a) in self.b.toplamlar([('move_id', 'in', fisler.ids), ('account_id', 'not in', nakit.ids),
                                                         ('display_type', 'not in', ('line_section', 'line_note'))]).items():
                sonuc[h] = -bakiye
        self._k[di] = sonuc
        return sonuc

    def _nakit_bakiye(self, di, tur):
        alan = self.b.taban(partner=False) + [('account_id', 'in', self._nakit_hesaplari().ids)]
        bas, bit = self.b.donemler[di]
        alan += [('date', '<', bas)] if tur == 'acilis' else [('date', '<=', bit)]
        return sum(v[0] for v in self.b.toplamlar(alan).values())

    def _kategori_hesaplari(self, satir, di):
        diger_tanimlar = [s.hesaplar for s in self.b.rapor.satir_ids if s.motor == 'nakit' and s.hesaplar and s != satir]
        sonuc = {}
        for h, v in self._karsi(di).items():
            kod = self.b.hesap_kodu(h)
            if satir.hesaplar:
                if kod_uyar(kod, satir.hesaplar):
                    sonuc[h] = v
            elif not any(kod_uyar(kod, t) for t in diger_tanimlar):  # tanımsız kalanlar ("diğer")
                sonuc[h] = v
        return sonuc

    def _deger(self, satir, di, onbellek):
        if (satir.id, di) in onbellek:
            return onbellek[(satir.id, di)]
        if satir.motor == 'nakit':
            v = sum(self._kategori_hesaplari(satir, di).values())
        elif satir.motor == 'nakit_acilis':
            v = self._nakit_bakiye(di, 'acilis')
        elif satir.motor == 'nakit_kapanis':
            v = self._nakit_bakiye(di, 'kapanis')
        elif satir.motor == 'toplam':
            v = sum(self._deger(c, di, onbellek) for c in self.b.rapor.satir_ids.filtered(lambda c: c.parent_id == satir))
        elif satir.motor == 'formul':
            kodlu = {s.kod: s for s in self.b.rapor.satir_ids if s.kod}
            degiskenler = {k: self._deger(s, di, onbellek) for k, s in kodlu.items() if k in (satir.formul or '')}
            try:
                v = float(safe_eval(satir.formul or '0', degiskenler))
            except ZeroDivisionError:
                v = 0.0
        else:
            v = 0.0
        onbellek[(satir.id, di)] = v
        return v

    def kok(self):
        onbellek = {}
        sonuc = []
        for s in self.b.rapor.satir_ids.sorted(lambda s: (s.sira, s.id)):
            seviye = 1 if s.parent_id else 0
            degerler = [self._deger(s, di, onbellek) for di in range(len(self.b.donemler))]
            if s.motor == 'baslik':
                degerler = [None] * len(degerler)
            if self.b.buyume:
                simdi, once = degerler[0] or 0, degerler[1] or 0
                degerler.append(((simdi - once) / abs(once) * 100) if once else None)
            denetim = [None] * len(degerler)
            if s.motor == 'nakit':
                for di in range(len(self.b.donemler)):
                    hesaplar = list(self._kategori_hesaplari(s, di))
                    fisler = self.env['account.move.line'].search(
                        self.b.taban(partner=False) + self.b.tarih_alani(self.b.donemler[di], 'hareket') +
                        [('account_id', 'in', self._nakit_hesaplari().ids)]).move_id
                    denetim[di] = self.b.denetim([('move_id', 'in', fisler.ids), ('account_id', 'in', [h.id for h in hesaplar])])
            sinif = 'baslik' if s.motor == 'baslik' else ('toplam' if s.kalin else 'normal')
            if s.gizle_sifir and not any(degerler[:len(self.b.donemler)]):
                continue
            sonuc.append(self.satir(f'tanim:{s.id}', s.name, seviye, degerler, denetim, acilabilir=s.motor == 'nakit',
                                    sinif=sinif, sifir_goster=True))
        return sonuc

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if not son.startswith('tanim:'):
            return []
        satir = self.b.rapor.satir_ids.browse(int(son[6:]))
        hesaplar = {}
        for di in range(len(self.b.donemler)):
            for h, v in self._kategori_hesaplari(satir, di).items():
                hesaplar.setdefault(h, [0.0] * len(self.b.donemler))[di] = v
        sonuc = []
        for h in sorted(hesaplar, key=self.b.hesap_kodu):
            degerler = hesaplar[h]
            if self.b.buyume:
                degerler = degerler + [((degerler[0] - degerler[1]) / abs(degerler[1]) * 100) if degerler[1] else None]
            sonuc.append(self.satir(f'{anahtar}|hesap:{h.id}', f'{self.b.hesap_kodu(h)} {h.name}', 2, degerler))
        return sonuc


# ====================================================================== Gerçekleşmemiş kur farkları
class KurFarki(Isleyici):

    def kolonlar(self):
        return [kolon('Döviz Tutarı', 'doviz'), kolon('Defter Değeri'), kolon('Kur', 'oran'), kolon('Değerlenmiş Tutar'), kolon('Kur Farkı')]

    def _veri(self):
        if hasattr(self, '_v'):
            return self._v
        tarih = self.b.donemler[0][1]
        Aml = self.env['account.move.line']
        alan = self.b.taban() + [('date', '<=', tarih), ('currency_id', '!=', self.b.para.id)]
        # Cari hesaplar: açık kalan; dövizli hesaplar (banka/kasa): bakiye
        cari = Aml.search(alan + [('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
                                  ('reconciled', '=', False), ('amount_residual_currency', '!=', 0)])
        dovizli = Aml.search(alan + [('account_id.currency_id', '!=', False), ('account_id.currency_id', '!=', self.b.para.id),
                                     ('account_id.account_type', 'not in', ('asset_receivable', 'liability_payable'))])
        veri = {}
        for k in cari:
            veri.setdefault(k.currency_id, {}).setdefault(k.account_id, []).append((k, k.amount_residual_currency, k.amount_residual))
        for k in dovizli:
            veri.setdefault(k.currency_id, {}).setdefault(k.account_id, []).append((k, k.amount_currency, k.balance))
        self._v = veri
        return veri

    def _kur(self, para):
        """Değerleme günü dahil en son kur (Atlas kur değerlemesiyle aynı kural)."""
        kur = self.env['res.currency.rate'].search([('currency_id', '=', para.id), ('name', '<=', self.b.donemler[0][1]),
                                                    ('company_id', 'in', (self.b.sirket.root_id.id, False))], order='name desc', limit=1)
        if kur:
            return kur.inverse_company_rate
        return para._get_conversion_rate(para, self.b.para, self.b.sirket, self.b.donemler[0][1])

    def _degerler(self, para, kalemler):
        doviz = sum(k[1] for k in kalemler)
        defter = sum(k[2] for k in kalemler)
        kur = self._kur(para)
        degerlenmis = self.b.para.round(doviz * kur)
        return [doviz, defter, kur, degerlenmis, degerlenmis - defter]

    def kok(self):
        sonuc = []
        toplam_fark = 0.0
        for para, hesaplar in sorted(self._veri().items(), key=lambda x: x[0].name):
            kalemler = [k for ks in hesaplar.values() for k in ks]
            degerler = self._degerler(para, kalemler)
            toplam_fark += degerler[4]
            sonuc.append(self.satir(f'doviz:{para.id}', f'{para.name} (1 {para.name} = {degerler[2]:.4f} {self.b.para.name})', 0,
                                    degerler, [self.b.denetim([('id', 'in', [k[0].id for k in kalemler])])] * 5,
                                    acilabilir=True, sinif='toplam', para=para.name))
        if sonuc:
            sonuc.append(self.satir('toplam', 'TOPLAM KUR FARKI', 0, [None, None, None, None, toplam_fark], sinif='toplam', sifir_goster=True))
        return sonuc

    def varsayilan_acik(self, satir):
        return satir['anahtar'].startswith('doviz:') and '|' not in satir['anahtar']

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        tur, _, kimlik = son.partition(':')
        if tur == 'doviz':
            para = self.env['res.currency'].browse(int(kimlik))
            sonuc = []
            for hesap, kalemler in sorted(self._veri().get(para, {}).items(), key=lambda x: self.b.hesap_kodu(x[0])):
                sonuc.append(self.satir(f'{anahtar}|hesap:{hesap.id}', f'{self.b.hesap_kodu(hesap)} {hesap.name}', 1,
                                        self._degerler(para, kalemler), [self.b.denetim([('id', 'in', [k[0].id for k in kalemler])])] * 5,
                                        acilabilir=True, para=para.name))
            return sonuc
        if tur == 'hesap':
            para = self.env['res.currency'].browse(int(anahtar.split('|')[0].split(':')[1]))
            kalemler = self._veri().get(para, {}).get(self.env['account.account'].browse(int(kimlik)), [])
            return [self.satir(f'{anahtar}|kalem:{k[0].id}', kalem_adi(k[0], k[0].partner_id.name), 2,
                               self._degerler(para, [k]), [self.b.denetim([('id', '=', k[0].id)])] * 5, sinif='kalem', para=para.name,
                               kayit={'model': 'account.move', 'id': k[0].move_id.id})
                    for k in sorted(kalemler, key=lambda k: (k[0].date, k[0].id))]
        return []


# ====================================================================== Banka denkleştirme
class BankaDenklestirme(Isleyici):

    def kolonlar(self):
        return [kolon('Tarih', 'tarih'), kolon('Açıklama', 'metin'), kolon('Tutar')]

    def _yevmiyeler(self):
        alan = [('type', '=', 'bank'), ('company_id', 'in', self.b.sirketler.ids)]
        if self.b.yevmiye_ids:
            alan.append(('id', 'in', self.b.yevmiye_ids))
        return self.env['account.journal'].search(alan, order='sequence, id')

    def _bekleyen_hesaplar(self, yevmiye):
        """Ödemelerin ekstreyle eşleşene kadar beklediği hesaplar (ödeme yöntemi satırlarındaki hesaplar)."""
        hesaplar = (yevmiye.inbound_payment_method_line_ids | yevmiye.outbound_payment_method_line_ids).mapped('payment_account_id')
        # Yöntem satırında hesap yoksa Odoo şirket varsayılanını kullanır (bkz. account.payment._get_outstanding_account)
        sablon = self.env['account.chart.template'].with_context(allowed_company_ids=yevmiye.company_id.root_id.ids)
        for ref in ('account_journal_payment_debit_account_id', 'account_journal_payment_credit_account_id'):
            hesaplar |= sablon.ref(ref, raise_if_not_found=False) or self.env['account.account']
        return hesaplar

    def _hesaplar(self, yevmiye):
        tarih = self.b.donemler[0][1]
        Aml = self.env['account.move.line']
        St = self.env['account.bank.statement.line']
        durum = ['posted', 'draft'] if self.b.taslak else ['posted']
        ekstre = St.search([('journal_id', '=', yevmiye.id), ('date', '<=', tarih), ('state', 'in', durum)])
        mutabik_degil = ekstre.filtered(lambda s: not s.is_reconciled)
        bekleyen_hesap = self._bekleyen_hesaplar(yevmiye) - yevmiye.default_account_id
        bekleyen = Aml.search([('account_id', 'in', bekleyen_hesap.ids), ('journal_id', '=', yevmiye.id), ('date', '<=', tarih),
                               ('reconciled', '=', False), ('parent_state', 'in', durum)])
        banka_kalemleri = Aml.search([('account_id', '=', yevmiye.default_account_id.id), ('date', '<=', tarih),
                                      ('parent_state', 'in', durum), ('company_id', '=', yevmiye.company_id.id)])
        # Bekleyen hesaplar şirket genelinde ortak olabilir: yalnız bu yevmiyenin kalemleri
        bekleyen_tum = Aml.search([('account_id', 'in', bekleyen_hesap.ids), ('journal_id', '=', yevmiye.id), ('date', '<=', tarih),
                                   ('parent_state', 'in', durum)])
        defter = banka_kalemleri | bekleyen_tum
        # Ekstre satırından gelmeyen, banka hesabına doğrudan yazılmış kayıtlar (mahsup fişi vb.)
        dogrudan = banka_kalemleri.filtered(lambda k: not k.move_id.statement_line_id)
        return ekstre, mutabik_degil, bekleyen, defter, dogrudan

    def kok(self):
        sonuc = []
        for y in self._yevmiyeler():
            ekstre, mutabik_degil, bekleyen, defter, dogrudan = self._hesaplar(y)
            fark = sum(ekstre.mapped('amount')) + sum(bekleyen.mapped('balance')) + sum(dogrudan.mapped('balance')) - sum(defter.mapped('balance'))
            sonuc.append(self.satir(f'banka:{y.id}', f'{y.name}' + (f' ({y.bank_account_id.display_name})' if y.bank_account_id else ''), 0,
                                    [None, None, sum(defter.mapped('balance'))], [None, None, self.b.denetim([('id', 'in', defter.ids)])],
                                    acilabilir=True, sinif='toplam', fark=round(fark, 2)))
        return sonuc

    def varsayilan_acik(self, satir):
        return satir['anahtar'].startswith('banka:') and '|' not in satir['anahtar']

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        tur, _, kimlik = son.partition(':')
        if tur == 'banka':
            y = self.env['account.journal'].browse(int(kimlik))
            ekstre, mutabik_degil, bekleyen, defter, dogrudan = self._hesaplar(y)
            giris = bekleyen.filtered(lambda k: k.balance > 0)
            cikis = bekleyen.filtered(lambda k: k.balance < 0)
            ekstre_bakiye = sum(ekstre.mapped('amount'))
            beklenen = ekstre_bakiye + sum(bekleyen.mapped('balance')) + sum(dogrudan.mapped('balance'))
            defter_bakiye = sum(defter.mapped('balance'))
            St = 'account.bank.statement.line'
            return [
                self.satir(f'{anahtar}|ekstre', 'Son ekstre bakiyesi', 1, [None, f'{len(ekstre)} ekstre satırı', ekstre_bakiye],
                           [None, None, self.b.denetim([('id', 'in', ekstre.ids)], St)]),
                self.satir(f'{anahtar}|mutabik:{y.id}', 'Eşleştirilmemiş ekstre satırları', 1,
                           [None, f'{len(mutabik_degil)} satır', sum(mutabik_degil.mapped('amount'))],
                           [None, None, self.b.denetim([('id', 'in', mutabik_degil.ids)], St)], acilabilir=bool(mutabik_degil)),
                self.satir(f'{anahtar}|giris:{y.id}', '(+) Bekleyen tahsilatlar (ekstreye düşmemiş)', 1,
                           [None, f'{len(giris)} kayıt', sum(giris.mapped('balance'))],
                           [None, None, self.b.denetim([('id', 'in', giris.ids)])], acilabilir=bool(giris)),
                self.satir(f'{anahtar}|cikis:{y.id}', '(-) Bekleyen ödemeler (ekstreye düşmemiş)', 1,
                           [None, f'{len(cikis)} kayıt', sum(cikis.mapped('balance'))],
                           [None, None, self.b.denetim([('id', 'in', cikis.ids)])], acilabilir=bool(cikis)),
                self.satir(f'{anahtar}|dogrudan:{y.id}', '(±) Ekstre dışı doğrudan kayıtlar (mahsup fişi vb.)', 1,
                           [None, f'{len(dogrudan)} kayıt', sum(dogrudan.mapped('balance'))],
                           [None, None, self.b.denetim([('id', 'in', dogrudan.ids)])], acilabilir=bool(dogrudan)),
                self.satir(f'{anahtar}|beklenen', '= Beklenen defter bakiyesi', 1, [None, None, beklenen], sinif='toplam', sifir_goster=True),
                self.satir(f'{anahtar}|defter', 'Defter bakiyesi (banka + bekleyen hesapları)', 1, [None, None, defter_bakiye],
                           [None, None, self.b.denetim([('id', 'in', defter.ids)])], sifir_goster=True),
                self.satir(f'{anahtar}|fark', 'Açıklanamayan fark', 1, [None, None, round(beklenen - defter_bakiye, 2)],
                           sinif='toplam' if round(beklenen - defter_bakiye, 2) else 'normal', sifir_goster=True,
                           uyari=bool(round(beklenen - defter_bakiye, 2))),
            ]
        if tur == 'mutabik':
            y = self.env['account.journal'].browse(int(kimlik))
            _e, mutabik_degil, _b, _d, _x = self._hesaplar(y)
            return [self.satir(f'{anahtar}|st:{s.id}', s.partner_id.name or s.payment_ref or '', 2,
                               [fields.Date.to_string(s.date), s.payment_ref or '', s.amount],
                               [None, None, self.b.denetim([('id', '=', s.id)], 'account.bank.statement.line')], sinif='kalem')
                    for s in mutabik_degil.sorted(lambda s: (s.date, s.id))]
        if tur in ('giris', 'cikis', 'dogrudan'):
            y = self.env['account.journal'].browse(int(kimlik))
            _e, _m, bekleyen, _d, dogrudan = self._hesaplar(y)
            kalemler = dogrudan if tur == 'dogrudan' else bekleyen.filtered(lambda k: (k.balance > 0) == (tur == 'giris'))
            return [self.satir(f'{anahtar}|kalem:{k.id}', f'{k.move_id.name} {k.partner_id.name or ""}'.strip(), 2,
                               [fields.Date.to_string(k.date), k.name or '', k.balance], [None, None, self.b.denetim([('id', '=', k.id)])],
                               sinif='kalem', kayit={'model': 'account.move', 'id': k.move_id.id})
                    for k in kalemler.sorted(lambda k: (k.date, k.id))]
        return []


# ====================================================================== Vergi raporu
class Vergi(Isleyici):

    def kolonlar(self):
        k = []
        for e in self.b.etiketler:
            k += [kolon(f'Matrah {e}' if len(self.b.etiketler) > 1 else 'Matrah'), kolon(f'Vergi {e}' if len(self.b.etiketler) > 1 else 'Vergi')]
        return k

    def _veri(self, di):
        if not hasattr(self, '_v'):
            self._v = {}
        if di not in self._v:
            alan = self.b.taban() + self.b.tarih_alani(self.b.donemler[di], 'hareket')
            Aml = self.env['account.move.line']
            vergi = {t: v[0] for t, v in self.b.toplamlar(alan + [('tax_line_id', '!=', False)], ('tax_line_id',)).items()}
            matrah = {}
            for t, bakiye in Aml._read_group(alan + [('tax_ids', '!=', False)], ['tax_ids'], ['balance:sum']):
                matrah[t] = bakiye or 0.0
            self._v[di] = (matrah, vergi)
        return self._v[di]

    def _vergiler(self, kullanim):
        vergiler = set()
        for di in range(len(self.b.donemler)):
            matrah, vergi = self._veri(di)
            vergiler |= {t for t in list(matrah) + list(vergi) if t and t.type_tax_use == kullanim}
        return sorted(vergiler, key=lambda t: (t.sequence, t.name))

    def _degerler(self, vergiler, isaret):
        d = []
        for di in range(len(self.b.donemler)):
            matrah, vergi = self._veri(di)
            d += [isaret * sum(matrah.get(t, 0) for t in vergiler), isaret * sum(vergi.get(t, 0) for t in vergiler)]
        return d

    def _denetim(self, vergiler):
        d = []
        for di in range(len(self.b.donemler)):
            alan = self.b.taban() + self.b.tarih_alani(self.b.donemler[di], 'hareket')
            ids = [t.id for t in vergiler]
            d += [self.b.denetim(alan + [('tax_ids', 'in', ids)]), self.b.denetim(alan + [('tax_line_id', 'in', ids)])]
        return d

    def kok(self):
        sonuc = []
        for kullanim, ad, isaret in (('sale', 'Satışlar (Hesaplanan Vergi)', -1), ('purchase', 'Alışlar (İndirilecek Vergi)', 1)):
            vergiler = self._vergiler(kullanim)
            sonuc.append(self.satir(f'grup:{kullanim}', ad, 0, self._degerler(vergiler, isaret), self._denetim(vergiler),
                                    acilabilir=bool(vergiler), sinif='toplam', sifir_goster=True))
        return sonuc

    def varsayilan_acik(self, satir):
        return satir['anahtar'].startswith('grup:')

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if not son.startswith('grup:'):
            return []
        kullanim = son[5:]
        isaret = -1 if kullanim == 'sale' else 1
        return [self.satir(f'{anahtar}|vergi:{t.id}', t.name, 1, self._degerler([t], isaret), self._denetim([t]))
                for t in self._vergiler(kullanim)]


# ====================================================================== Yevmiye raporu
class Yevmiye(Isleyici):
    sayfalama = True

    def kolonlar(self):
        return [kolon('Tarih', 'tarih'), kolon('Hesap', 'metin'), kolon('Açıklama', 'metin'), kolon('Borç'), kolon('Alacak')]

    def _alan(self):
        return self.b.taban() + self.b.tarih_alani(self.b.donemler[0], 'hareket')

    def kok(self, offset=0):
        Aml = self.env['account.move.line']
        Move = self.env['account.move']
        gruplar = Aml._read_group(self._alan(), ['move_id'], ['debit:sum', 'credit:sum'])
        fisler = Move.browse([g[0].id for g in gruplar]).sorted(
            lambda m: (m.date, getattr(m, 'atlas_yevmiye_no', 0) or 0, m.name or '', m.id))
        tutar = {g[0].id: (g[1], g[2]) for g in gruplar}
        sonuc = []
        for m in fisler[offset:offset + SAYFA]:
            b_, a_ = tutar[m.id]
            no = getattr(m, 'atlas_yevmiye_no', False)
            sonuc.append(self.satir(f'fis:{m.id}', f'{m.name}' + (f'  (Yev. {no})' if no else ''), 0,
                                    [fields.Date.to_string(m.date), m.journal_id.name, m.ref or '', b_, a_],
                                    [None] * 3 + [self.b.denetim([('move_id', '=', m.id)])] * 2, acilabilir=True,
                                    kayit={'model': 'account.move', 'id': m.id}))
        if len(fisler) > offset + SAYFA:
            sonuc.append(self.satir(f'daha:{offset + SAYFA}', 'Daha fazla yükle…', 0, [None] * 5, sinif='daha'))
        if offset == 0 and fisler:
            sonuc.append(self.satir('toplam', 'TOPLAM', 0, [None, None, None, sum(v[0] for v in tutar.values()),
                                                            sum(v[1] for v in tutar.values())], sinif='toplam', sifir_goster=True))
        return sonuc

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if son.startswith('daha:'):
            return [s for s in self.kok(int(son[5:])) if s['anahtar'] != 'toplam']
        if not son.startswith('fis:'):
            return []
        m = self.env['account.move'].browse(int(son[4:]))
        return [self.satir(f'{anahtar}|kalem:{k.id}', k.name or '', 1,
                           [None, f'{self.b.hesap_kodu(k.account_id)} {k.account_id.name}', k.partner_id.name or k.name or '', k.debit, k.credit],
                           [None] * 3 + [self.b.denetim([('id', '=', k.id)])] * 2, sinif='kalem', sifir_goster=True)
                for k in m.line_ids.filtered(lambda k: k.display_type not in ('line_section', 'line_note'))]


# ====================================================================== Amortisman tablosu
class Amortisman(Isleyici):

    def kolonlar(self):
        return [kolon('Edinme', 'tarih'), kolon('Maliyet'), kolon('Dönem Başı Birikmiş'), kolon('Dönem Amortismanı'),
                kolon('Dönem Sonu Birikmiş'), kolon('Net Defter Değeri')]

    def _kiymetler(self):
        bas, bit = self.b.donemler[0]
        return self.env['atlas.sabit.kiymet'].search([
            ('company_id', 'in', self.b.sirketler.ids), ('state', '!=', 'draft'), ('edinme_tarihi', '<=', bit),
            '|', ('satis_tarihi', '=', False), ('satis_tarihi', '>=', bas)])

    def _degerler(self, kiymetler):
        bas, bit = self.b.donemler[0]
        Aml = self.env['account.move.line']
        durum = ['posted', 'draft'] if self.b.taslak else ['posted']
        maliyet = sum(kiymetler.mapped('bedel'))
        once = sonra = 0.0
        for k in kiymetler:
            kalemler = Aml.search([('atlas_amortisman_line_id.kiymet_id', '=', k.id), ('account_id', '=', k.birikmis_account_id.id),
                                   ('parent_state', 'in', durum), ('date', '<=', bit)])
            once += -sum(kalemler.filtered(lambda x: x.date < bas).mapped('balance'))
            sonra += -sum(kalemler.mapped('balance'))
        return [None, maliyet, once, sonra - once, sonra, maliyet - sonra]

    def kok(self):
        gruplar = {}
        for k in self._kiymetler():
            gruplar.setdefault(k.account_id, self.env['atlas.sabit.kiymet'])
            gruplar[k.account_id] |= k
        sonuc = []
        tum = self.env['atlas.sabit.kiymet']
        for hesap in sorted(gruplar, key=self.b.hesap_kodu):
            tum |= gruplar[hesap]
            sonuc.append(self.satir(f'hesap:{hesap.id}', f'{self.b.hesap_kodu(hesap)} {hesap.name}', 0, self._degerler(gruplar[hesap]),
                                    acilabilir=True, sinif='toplam'))
        if tum:
            sonuc.append(self.satir('toplam', 'TOPLAM', 0, self._degerler(tum), sinif='toplam', sifir_goster=True))
        return sonuc

    def varsayilan_acik(self, satir):
        return '|' not in satir['anahtar'] and satir['anahtar'].startswith('hesap:')

    def cocuklar(self, anahtar, offset=0):
        son = anahtar.split('|')[-1]
        if not son.startswith('hesap:'):
            return []
        hesap_id = int(son[6:])
        sonuc = []
        for k in self._kiymetler().filtered(lambda k: k.account_id.id == hesap_id).sorted(lambda k: (k.edinme_tarihi, k.id)):
            d = self._degerler(k)
            d[0] = fields.Date.to_string(k.edinme_tarihi)
            sonuc.append(self.satir(f'{anahtar}|kiymet:{k.id}', f'{k.kod} {k.name}', 1, d, sinif='kalem', sifir_goster=True,
                                    kayit={'model': 'atlas.sabit.kiymet', 'id': k.id}))
        return sonuc


ISLEYICILER = {
    'tanim': Tanim, 'mizan': Mizan, 'muavin': Muavin, 'cari': CariDefter, 'yaslandirma_alacak': Yaslandirma,
    'yaslandirma_borc': YaslandirmaBorc, 'nakit_akis': NakitAkis, 'kur_farki': KurFarki, 'banka': BankaDenklestirme,
    'vergi': Vergi, 'yevmiye': Yevmiye, 'amortisman': Amortisman,
}
