from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable

from flask import Request

from smartlink.models import AppSettings


def get_lan_addresses() -> list[str]:
    addresses = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for item in socket.gethostbyname_ex(hostname)[2]:
            if item:
                addresses.add(item)
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return sorted(addresses)


def get_client_ip(request: Request) -> str:
    if request.access_route:
        return request.access_route[0]
    return request.remote_addr or "127.0.0.1"


def ip_allowed(client_ip: str, settings: AppSettings) -> bool:
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    if client_ip in settings.allowed_ips:
        return True
    if not settings.allowed_networks and not settings.allowed_ips:
        return True
    for network in settings.allowed_networks:
        try:
            if ip_obj in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


def parse_lines(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        items = value.splitlines()
    else:
        items = list(value)
    return [item.strip() for item in items if item and item.strip()]
