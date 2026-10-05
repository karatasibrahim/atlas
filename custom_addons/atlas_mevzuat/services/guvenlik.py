"""Tarama güvenliği: izinli alan listesi ve SSRF koruması (özel/iç IP adreslerine bağlanılmaz)."""
import ipaddress
import socket
from urllib.parse import urlsplit


class GuvenlikHatasi(Exception):
    pass


def alan_adlari(metin):
    """'gib.gov.tr, www.sgk.gov.tr' → {'gib.gov.tr', 'www.sgk.gov.tr'}"""
    return {p.strip().lower().lstrip('.') for p in (metin or '').replace('\n', ',').replace(' ', ',').split(',') if p.strip()}


def alan_izinli(host, izinliler):
    host = (host or '').lower().rstrip('.')
    return any(host == a or host.endswith('.' + a) for a in izinliler)


def ip_guvenli(ip):
    adres = ipaddress.ip_address(ip)
    if adres.version == 6 and adres.ipv4_mapped:
        adres = adres.ipv4_mapped
    return adres.is_global and not (adres.is_private or adres.is_loopback or adres.is_link_local or adres.is_multicast
                                    or adres.is_reserved or adres.is_unspecified)


def cozumle(host, port):
    try:
        return {b[4][0] for b in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)}
    except socket.gaierror as e:
        raise GuvenlikHatasi(f'Alan adı çözülemedi: {host} ({e})') from e


def url_dogrula(url, izinliler, cozumleyici=cozumle):
    """URL yalnız http(s), izinli alan adında ve genel (internet) IP adresine çözülüyorsa geçer."""
    parca = urlsplit(url or '')
    if parca.scheme not in ('http', 'https'):
        raise GuvenlikHatasi(f'Desteklenmeyen şema: {parca.scheme or "-"}')
    if parca.username or parca.password:
        raise GuvenlikHatasi('URL içinde kullanıcı bilgisi olamaz')
    host = parca.hostname
    if not host:
        raise GuvenlikHatasi('URL alan adı içermiyor')
    if not izinliler:
        raise GuvenlikHatasi('Kaynağın izinli alan adı listesi boş')
    if not alan_izinli(host, izinliler):
        raise GuvenlikHatasi(f'Alan adı izinli listede değil: {host}')
    try:
        ipaddress.ip_address(host)
        raise GuvenlikHatasi('IP adresiyle tarama yapılmaz, alan adı kullanın')
    except ValueError:
        pass
    port = parca.port or (443 if parca.scheme == 'https' else 80)
    for ip in cozumleyici(host, port):
        if not ip_guvenli(ip):
            raise GuvenlikHatasi(f'{host} özel/iç ağ adresine çözülüyor ({ip}); SSRF koruması')
    return parca
