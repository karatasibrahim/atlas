"""İsteğe bağlı yapay zekâ sınıflandırma önerisi (Anthropic Messages API).

Sonuç her zaman "AI önerisi" olarak işaretlenir ve insan incelemesine düşer; ERP'de hiçbir şeyi değiştirmez.
"""
import json
import re

import requests

API_URL = 'https://api.anthropic.com/v1/messages'
VARSAYILAN_MODEL = 'claude-sonnet-5'

SISTEM = (
    "Türkiye'deki resmî kurum duyurularını ve mevzuat değişikliklerini bir ERP (Odoo tabanlı Atlas) açısından "
    "değerlendiren bir uyum analistisin. Yalnızca istenen JSON nesnesini döndür, başka metin yazma."
)


class AiHatasi(Exception):
    pass


def istem_olustur(baslik, metin, kaynak, kategoriler, moduller):
    return (
        f"Kaynak: {kaynak}\nBaşlık: {baslik}\nMetin:\n{metin[:12000]}\n\n"
        f"Kategoriler (kod: ad): {json.dumps(kategoriler, ensure_ascii=False)}\n"
        f"ERP modülleri (teknik ad: açıklama): {json.dumps(moduller, ensure_ascii=False)}\n\n"
        "Şu alanlarla JSON döndür:\n"
        '{"kategori": "<kod veya null>", "onem": "dusuk|orta|yuksek|kritik", "moduller": ["<teknik ad>"], '
        '"yururluk_tarihi": "YYYY-AA-GG veya null", "ozet": "<en çok 3 cümle Türkçe özet: ERP\'ye etkisi>", '
        '"gelistirme_gerekli": bool, "ayar_gerekli": bool, "kullanici_aksiyonu": bool, "kirici_degisiklik": bool, '
        '"ilgisiz": bool, "guven": 0-100}\n'
        "ERP'yi (fatura, e-belge, bordro, SGK, vergi oranı, beyanname, KVKK, ticaret sicili …) etkilemeyen duyurular için "
        '"ilgisiz": true ver.'
    )


def yanit_coz(metin):
    m = re.search(r'\{.*\}', metin or '', re.DOTALL)
    if not m:
        raise AiHatasi('Yanıtta JSON bulunamadı')
    try:
        veri = json.loads(m.group(0))
    except ValueError as e:
        raise AiHatasi(f'Geçersiz JSON: {e}') from e
    onem = veri.get('onem') if veri.get('onem') in ('dusuk', 'orta', 'yuksek', 'kritik') else 'orta'
    try:
        guven = max(0.0, min(100.0, float(veri.get('guven') or 0)))
    except (TypeError, ValueError):
        guven = 0.0
    return {
        'kategori': veri.get('kategori'),
        'onem': onem,
        'moduller': [m for m in (veri.get('moduller') or []) if isinstance(m, str)],
        'yururluk_tarihi': veri.get('yururluk_tarihi') if isinstance(veri.get('yururluk_tarihi'), str) else None,
        'ozet': str(veri.get('ozet') or '')[:2000],
        'gelistirme': bool(veri.get('gelistirme_gerekli')),
        'ayar': bool(veri.get('ayar_gerekli')),
        'kullanici': bool(veri.get('kullanici_aksiyonu')),
        'kirici': bool(veri.get('kirici_degisiklik')),
        'ilgisiz': bool(veri.get('ilgisiz')),
        'guven': guven,
    }


def sor(anahtar, model, istem, zaman_asimi=60, oturum=None):
    if not anahtar:
        raise AiHatasi('API anahtarı tanımlı değil')
    r = (oturum or requests).post(
        API_URL, timeout=zaman_asimi,
        headers={'x-api-key': anahtar, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': model or VARSAYILAN_MODEL, 'max_tokens': 1024, 'system': SISTEM,
              'messages': [{'role': 'user', 'content': istem}]},
    )
    if r.status_code != 200:
        raise AiHatasi(f'HTTP {r.status_code}: {r.text[:300]}')
    try:
        parcalar = r.json().get('content') or []
    except ValueError as e:
        raise AiHatasi('Yanıt JSON değil') from e
    return yanit_coz(''.join(p.get('text', '') for p in parcalar if p.get('type') == 'text'))
