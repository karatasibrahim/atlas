"""Kural tabanlı sınıflandırıcı: anahtar kelime eşleşmesiyle kategori, önem, etkilenen modüller ve aksiyon bayrakları."""
import re

from .metin import kucult

ONEM_SIRA = {'dusuk': 1, 'orta': 2, 'yuksek': 3, 'kritik': 4}


def kelimeler(metin):
    """Virgül/satır ile ayrılmış anahtar kelimeler → normalleştirilmiş liste."""
    return [kucult(p) for p in re.split(r'[,\n;]', metin or '') if p.strip()]


def _desen(kelime):
    # Kelime başında sınır; sonda Türkçe ekler serbest ("e-fatura" → "e-faturaların")
    return re.compile(r'(?<![\w])' + re.escape(kelime))


class Kural:
    def __init__(self, kimlik, anahtarlar, haric=(), agirlik=1.0, birlikte=(), yalniz_baslik=False, **veri):
        self.kimlik = kimlik
        self.anahtarlar = [(k, _desen(k)) for k in anahtarlar if k]
        self.haric = [_desen(k) for k in haric if k]
        self.birlikte = [_desen(k) for k in birlikte if k]
        self.yalniz_baslik = yalniz_baslik
        self.agirlik = agirlik or 1.0
        self.veri = veri  # kategori_id, onem, modul_ids, gelistirme, ayar, kullanici, kirici, ad

    def eslesme(self, baslik, govde):
        metin = baslik if self.yalniz_baslik else baslik + ' ' + govde
        if any(d.search(metin) for d in self.haric):
            return 0, []
        if self.birlikte and not any(d.search(metin) for d in self.birlikte):
            return 0, []
        bulunan = [k for k, d in self.anahtarlar if d.search(metin)]
        if not bulunan:
            return 0, []
        puan = sum(2.0 if d.search(baslik) else 1.0 for k, d in self.anahtarlar if k in bulunan) * self.agirlik
        return puan, bulunan


def siniflandir(baslik, govde, kurallar):
    """Döndürür: None (eşleşme yok) ya da sonuç sözlüğü."""
    b, g = kucult(baslik), kucult(govde)[:20000]
    sonuclar = []
    for kural in kurallar:
        puan, bulunan = kural.eslesme(b, g)
        if puan:
            sonuclar.append((puan, kural, bulunan))
    if not sonuclar:
        return None
    sonuclar.sort(key=lambda s: -s[0])
    en_iyi = sonuclar[0][1]
    onem = max((s[1].veri.get('onem') or 'dusuk' for s in sonuclar), key=lambda o: ONEM_SIRA.get(o, 0))
    toplam = sum(s[0] for s in sonuclar)
    baslikta = any(any(d.search(b) for _, d in s[1].anahtarlar) for s in sonuclar)
    guven = min(95.0, 45.0 + 10.0 * min(toplam, 4) + (10.0 if baslikta else 0))
    moduller = []
    for s in sonuclar:
        for m in s[1].veri.get('modul_ids') or []:
            if m not in moduller:
                moduller.append(m)
    bayrak = lambda ad: any(s[1].veri.get(ad) for s in sonuclar)
    return {
        'kategori_id': en_iyi.veri.get('kategori_id'),
        'onem': onem,
        'modul_ids': moduller,
        'gelistirme': bayrak('gelistirme'),
        'ayar': bayrak('ayar'),
        'kullanici': bayrak('kullanici'),
        'kirici': bayrak('kirici'),
        'guven': guven,
        'kural_ids': [s[1].kimlik for s in sonuclar],
        'aciklama': '; '.join(f"{s[1].veri.get('ad', s[1].kimlik)}: {', '.join(s[2][:5])}" for s in sonuclar[:6]),
    }
