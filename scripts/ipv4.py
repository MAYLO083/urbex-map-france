"""
Force les connexions réseau en IPv4.

Certaines machines GitHub Actions n'ont pas de route IPv6 : quand un serveur
(ex. download.geofabrik.de) annonce aussi une adresse IPv6, Python peut essayer
celle-ci et échouer avec « [Errno 101] Network is unreachable ».
Il suffit d'importer ce module avant de télécharger.
"""

import socket

_getaddrinfo = socket.getaddrinfo


def _ipv4_first(host, *args, **kwargs):
    res = _getaddrinfo(host, *args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res


socket.getaddrinfo = _ipv4_first
