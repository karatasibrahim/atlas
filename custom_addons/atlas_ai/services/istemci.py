"""Anthropic Messages API istemcisi (SDK'sız): metin/PDF/görsel içerik ve araçla zorunlu yapılandırılmış çıktı."""
import base64
import json
import time

import requests

API_URL = 'https://api.anthropic.com/v1/messages'
VARSAYILAN_MODEL = 'claude-sonnet-5'
GORSEL_TURLERI = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
EN_FAZLA_BOYUT = 30 * 1024 * 1024


class AiHatasi(Exception):
    pass


def dosya_blogu(icerik, mimetype):
    """PDF → document bloğu, görsel → image bloğu, metin → text bloğu."""
    if len(icerik) > EN_FAZLA_BOYUT:
        raise AiHatasi('Dosya çok büyük (30 MB sınırı)')
    veri = base64.b64encode(icerik).decode()
    if mimetype == 'application/pdf':
        return {'type': 'document', 'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': veri}}
    if mimetype in GORSEL_TURLERI:
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': mimetype, 'data': veri}}
    if mimetype and mimetype.startswith('text/'):
        return {'type': 'text', 'text': icerik.decode('utf-8', 'replace')[:100000]}
    raise AiHatasi(f'Desteklenmeyen dosya türü: {mimetype or "bilinmiyor"} (PDF, JPEG, PNG, WEBP, GIF ya da metin)')


def sor(anahtar, model, sistem, icerik, arac=None, en_fazla_token=4096, zaman_asimi=120, oturum=None):
    """icerik: içerik blokları listesi ya da metin. arac: {'name', 'description', 'input_schema'} verilirse
    model bu aracı çağırmaya zorlanır ve aracın girdisi (dict) döner; yoksa metin döner.
    Dönüş: (sonuç, kullanım{'giris', 'cikis', 'sure_ms'})"""
    if not anahtar:
        raise AiHatasi('Yapay zekâ API anahtarı tanımlı değil (Ayarlar > Yapay Zekâ)')
    if isinstance(icerik, str):
        icerik = [{'type': 'text', 'text': icerik}]
    govde = {'model': model or VARSAYILAN_MODEL, 'max_tokens': en_fazla_token, 'system': sistem,
             'messages': [{'role': 'user', 'content': icerik}]}
    if arac:
        govde['tools'] = [arac]
        govde['tool_choice'] = {'type': 'tool', 'name': arac['name']}
    basla = time.monotonic()
    try:
        r = (oturum or requests).post(API_URL, json=govde, timeout=zaman_asimi, headers={
            'x-api-key': anahtar, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    except requests.RequestException as e:
        raise AiHatasi(f'Bağlantı hatası: {e}') from e
    if r.status_code != 200:
        try:
            mesaj = r.json().get('error', {}).get('message') or r.text
        except ValueError:
            mesaj = r.text
        raise AiHatasi(f'HTTP {r.status_code}: {str(mesaj)[:400]}')
    try:
        veri = r.json()
    except ValueError as e:
        raise AiHatasi('Yanıt JSON değil') from e
    kullanim = {'giris': (veri.get('usage') or {}).get('input_tokens', 0), 'cikis': (veri.get('usage') or {}).get('output_tokens', 0),
                'sure_ms': int((time.monotonic() - basla) * 1000)}
    bloklar = veri.get('content') or []
    if arac:
        for b in bloklar:
            if b.get('type') == 'tool_use' and b.get('name') == arac['name']:
                return b.get('input') or {}, kullanim
        # Bazı durumlarda model JSON'u metin olarak döndürebilir
        metin = ''.join(b.get('text', '') for b in bloklar if b.get('type') == 'text')
        try:
            return json.loads(metin[metin.index('{'):metin.rindex('}') + 1]), kullanim
        except ValueError as e:
            raise AiHatasi('Yanıtta beklenen yapılandırılmış veri yok') from e
    return ''.join(b.get('text', '') for b in bloklar if b.get('type') == 'text'), kullanim
