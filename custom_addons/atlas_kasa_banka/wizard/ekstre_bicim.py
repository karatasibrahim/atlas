"""Banka ekstresi dosya biçimleri: CSV, ISO 20022 CAMT.053 (XML), OFX, SWIFT MT940.

Her ayrıştırıcı (hareketler, açılış bakiyesi, kapanış bakiyesi) döndürür; hareket sözlüğü
{'date', 'amount', 'aciklama', 'referans', 'bakiye'} (Excel içe aktarmasıyla aynı biçim).
"""
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from lxml import etree


class BicimHatasi(Exception):
    pass


def metin_coz(icerik):
    for kod in ('utf-8-sig', 'windows-1254', 'iso-8859-9'):
        try:
            return icerik.decode(kod)
        except UnicodeDecodeError:
            continue
    return icerik.decode('utf-8', 'replace')


def bicim_bul(dosya_adi, icerik):
    ad = (dosya_adi or '').lower()
    bas = icerik[:600].lstrip()
    if ad.endswith(('.xlsx', '.xlsm')) or icerik[:2] == b'PK':
        return 'xlsx'
    if ad.endswith('.ofx') or b'<OFX>' in icerik[:2000].upper() or b'OFXHEADER' in bas[:200].upper():
        return 'ofx'
    if ad.endswith(('.xml', '.camt', '.053')) or b'camt.053' in icerik[:3000]:
        return 'camt'
    if ad.endswith(('.sta', '.mt940', '.940')) or re.search(rb':20:.*\n.*:25:', icerik[:2000]) or b':61:' in icerik[:5000]:
        return 'mt940'
    if ad.endswith(('.csv', '.txt')):
        return 'csv'
    raise BicimHatasi('Dosya biçimi tanınmadı (desteklenen: .xlsx, .csv, CAMT.053 .xml, .ofx, MT940 .sta)')


def csv_satirlari(icerik):
    metin = metin_coz(icerik)
    ornek = metin[:4000]
    try:
        lehce = csv.Sniffer().sniff(ornek, delimiters=';,\t|')
    except csv.Error:
        lehce = csv.excel
        lehce.delimiter = ';' if ornek.count(';') > ornek.count(',') else ','
    return [row for row in csv.reader(io.StringIO(metin), lehce) if any(c.strip() for c in row)]


def ilk(*ogeler):
    """lxml öğeleri çocuğu yoksa False sayılır; 'a or b' yerine None kontrolü."""
    return next((o for o in ogeler if o is not None), None)


def _sayi(deger):
    return float(Decimal(str(deger).strip().replace(',', '.'))) if deger not in (None, '') else 0.0


def camt(icerik):
    try:
        kok = etree.fromstring(icerik, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except etree.XMLSyntaxError as e:
        raise BicimHatasi(f'XML okunamadı: {e}') from e
    ad = lambda el: etree.QName(el).localname
    bul = lambda el, *yol: next(iter(_yol(el, yol)), None)

    def _yol(el, yol):
        aday = [el]
        for parca in yol:
            aday = [c for a in aday for c in a if isinstance(c.tag, str) and ad(c) == parca]
        return aday

    ekstreler = [e for e in kok.iter() if isinstance(e.tag, str) and ad(e) in ('Stmt', 'Rpt')]
    if not ekstreler:
        raise BicimHatasi('CAMT dosyasında ekstre (Stmt) bulunamadı')
    hareketler, acilis, kapanis = [], None, None
    for stmt in ekstreler:
        for bal in _yol(stmt, ['Bal']):
            tur = bul(bal, 'Tp', 'CdOrPrtry', 'Cd')
            tutar = bul(bal, 'Amt')
            if tur is None or tutar is None:
                continue
            ind = bul(bal, 'CdtDbtInd')
            isaret = -1 if ind is not None and ind.text == 'DBIT' else 1
            if tur.text in ('OPBD', 'PRCD') and acilis is None:
                acilis = isaret * _sayi(tutar.text)
            if tur.text in ('CLBD',):
                kapanis = isaret * _sayi(tutar.text)
        for ntry in _yol(stmt, ['Ntry']):
            tutar = bul(ntry, 'Amt')
            if tutar is None:
                continue
            ind = bul(ntry, 'CdtDbtInd')
            isaret = -1 if ind is not None and ind.text == 'DBIT' else 1
            tarih_el = ilk(bul(ntry, 'BookgDt', 'Dt'), bul(ntry, 'BookgDt', 'DtTm'), bul(ntry, 'ValDt', 'Dt'))
            if tarih_el is None:
                continue
            tarih = date.fromisoformat(tarih_el.text[:10])
            aciklamalar = [e.text for e in ntry.iter() if isinstance(e.tag, str) and ad(e) in ('Ustrd', 'AddtlNtryInf', 'AddtlTxInf') and e.text]
            karsi = [e.text for e in ntry.iter() if isinstance(e.tag, str) and ad(e) == 'Nm' and e.text]
            ref = ilk(bul(ntry, 'AcctSvcrRef'), bul(ntry, 'NtryRef'))
            refs = [e.text for e in ntry.iter() if isinstance(e.tag, str) and ad(e) in ('EndToEndId', 'TxId') and e.text and e.text != 'NOTPROVIDED']
            hareketler.append({'date': tarih, 'amount': isaret * _sayi(tutar.text),
                               'aciklama': ' '.join(dict.fromkeys(karsi[:1] + aciklamalar))[:500] or None,
                               'referans': (ref.text if ref is not None else None) or (refs[0] if refs else None), 'bakiye': None})
    return hareketler, acilis, kapanis


def ofx(icerik):
    metin = metin_coz(icerik)
    govde = metin[metin.upper().find('<OFX>'):] if '<OFX>' in metin.upper() else metin

    def alan(blok, etiket):
        m = re.search(rf'<{etiket}>([^<\r\n]*)', blok, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def tarih(deger):
        return datetime.strptime(deger[:8], '%Y%m%d').date()

    hareketler = []
    for blok in re.findall(r'<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))', govde, re.IGNORECASE | re.DOTALL):
        tutar, tarih_d = alan(blok, 'TRNAMT'), alan(blok, 'DTPOSTED')
        if not (tutar and tarih_d):
            continue
        aciklama = ' '.join(p for p in (alan(blok, 'NAME'), alan(blok, 'MEMO')) if p)
        hareketler.append({'date': tarih(tarih_d), 'amount': _sayi(tutar), 'aciklama': aciklama or None,
                           'referans': alan(blok, 'FITID') or alan(blok, 'CHECKNUM'), 'bakiye': None})
    if not hareketler:
        raise BicimHatasi('OFX dosyasında hareket (STMTTRN) bulunamadı')
    kapanis_blok = re.search(r'<LEDGERBAL>(.*?)(?:</LEDGERBAL>|$)', govde, re.IGNORECASE | re.DOTALL)
    kapanis = _sayi(alan(kapanis_blok.group(1), 'BALAMT')) if kapanis_blok and alan(kapanis_blok.group(1), 'BALAMT') else None
    acilis = (kapanis - sum(h['amount'] for h in hareketler)) if kapanis is not None else None
    return hareketler, acilis, kapanis


def _mt_tutar(deger):
    return float(deger.replace(',', '.'))


def mt940(icerik):
    metin = metin_coz(icerik).replace('\r\n', '\n')
    # Alanları ":NN:" etiketlerine göre böl (çok satırlı :86: dahil)
    alanlar = re.findall(r'^:(\d{2}[A-Z]?):(.*?)(?=^:\d{2}[A-Z]?:|^-\}|\Z)', metin, re.MULTILINE | re.DOTALL)
    hareketler, acilis, kapanis = [], None, None
    son = None
    for etiket, deger in alanlar:
        deger = deger.strip()
        if etiket in ('60F', '60M') and acilis is None:
            m = re.match(r'([CD])(\d{6})([A-Z]{3})([\d,]+)', deger)
            if m:
                acilis = (_mt_tutar(m.group(4))) * (-1 if m.group(1) == 'D' else 1)
        elif etiket in ('62F', '62M'):
            m = re.match(r'([CD])(\d{6})([A-Z]{3})([\d,]+)', deger)
            if m:
                kapanis = (_mt_tutar(m.group(4))) * (-1 if m.group(1) == 'D' else 1)
        elif etiket == '61':
            m = re.match(r'(\d{6})(\d{4})?(R?[CD])([A-Z])?([\d,]+)([A-Z]\w{3})?([^/\n]*)(?://([^\n]*))?', deger)
            if not m:
                continue
            tarih = datetime.strptime(m.group(1), '%y%m%d').date()
            isaret = -1 if m.group(3) in ('D', 'RC') else 1
            son = {'date': tarih, 'amount': isaret * _mt_tutar(m.group(5)), 'aciklama': None,
                   'referans': (m.group(7) or '').strip() or (m.group(8) or '').strip() or None, 'bakiye': None}
            hareketler.append(son)
        elif etiket == '86' and son is not None:
            aciklama = ' '.join(deger.split())
            aciklama = re.sub(r'\?\d{2}', ' ', aciklama)  # bazı bankaların alt alan ayırıcıları (?20, ?21 …)
            son['aciklama'] = ' '.join(aciklama.split())[:500]
    if not hareketler:
        raise BicimHatasi('MT940 dosyasında hareket (:61:) bulunamadı')
    return hareketler, acilis, kapanis
