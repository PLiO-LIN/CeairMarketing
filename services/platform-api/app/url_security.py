"""Validation helpers for user supplied outbound URLs.

Only public HTTP(S) endpoints are accepted.  DNS is resolved before the request
and every returned address is checked to prevent access to loopback, private,
link-local and other non-routable networks.

``safe_fetch`` closes the two bypasses a plain pre-request check leaves open:

* ``urllib`` follows redirects by default, so a public host can bounce the
  request to an internal address.  Every hop is re-validated here.
* The record can change between validation and the connection (DNS rebinding).
  The addresses accepted during validation are pinned for that connection.
"""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

ALLOWED_SCHEMES = {"http", "https"}
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 3
DEFAULT_MAX_BYTES = 1_000_000


@dataclass(frozen=True)
class Fetched:
    """Body and response metadata for a successful ``safe_fetch``."""

    body: bytes
    content_type: str
    charset: str
    url: str


class UnsafeUrlError(ValueError):
    """Raised when an outbound URL is not safe for server-side fetching."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    # ::ffff:127.0.0.1 stays an IPv6Address in Python, and its own flags do not
    # report the loopback address hidden inside it.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _check_syntax(value: str):
    parsed = urlparse(value)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise UnsafeUrlError("来源地址必须使用 http 或 https，且必须包含主机名")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("来源地址不允许携带用户名或密码")
    return parsed


def _resolve(host: str, port: int) -> set[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("来源主机无法解析") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeUrlError("来源主机无法解析")
    if any(not _is_public(address) for address in addresses):
        raise UnsafeUrlError("来源地址解析到受限网络，已拒绝访问")
    return addresses


def validate_public_url(value: str, *, allow_empty: bool = False) -> str:
    value = (value or "").strip()
    if not value and allow_empty:
        return ""
    parsed = _check_syntax(value)
    host = parsed.hostname.rstrip(".")
    _resolve(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    return value


@contextlib.contextmanager
def _pinned_resolution(host: str, addresses: set[str]):
    """Restrict this connection to the addresses that already passed review."""
    original = socket.getaddrinfo

    def pinned(name, *args, **kwargs):
        infos = original(name, *args, **kwargs)
        if str(name).rstrip(".") != host:
            return infos
        kept = [info for info in infos if info[4][0] in addresses]
        if not kept:
            raise UnsafeUrlError("来源地址在连接阶段改解析到未审查的主机")
        return kept

    socket.getaddrinfo = pinned
    try:
        yield
    finally:
        socket.getaddrinfo = original


class _StopAtRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_DEFAULT_OPENER = urllib.request.build_opener(_StopAtRedirect)


def safe_fetch(
    value: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    opener=None,
) -> Fetched:
    """Fetch a user supplied URL, validating every hop and pinning DNS.

    ``opener`` exists so the redirect policy can be exercised without network
    access in tests; production callers should leave it unset.
    """

    url = (value or "").strip()
    director = opener or _DEFAULT_OPENER
    for _hop in range(max_redirects + 1):
        parsed = _check_syntax(url)
        host = parsed.hostname.rstrip(".")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = _resolve(host, port)
        request = urllib.request.Request(url, headers=dict(headers or {}))
        try:
            with _pinned_resolution(host, addresses):
                response = director.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in REDIRECT_CODES:
                raise
            location = (exc.headers.get("Location") or "").strip()
            if not location:
                raise UnsafeUrlError("重定向响应缺少目标地址") from exc
            url = urljoin(request.full_url, location)
            continue
        except urllib.error.URLError as exc:
            reason = exc.args[0] if exc.args else exc
            if isinstance(reason, UnsafeUrlError):
                raise reason from exc
            raise UnsafeUrlError(f"来源地址无法访问：{reason}") from exc
        with response:
            payload = response.read(max_bytes + 1)
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
        if len(payload) > max_bytes:
            raise UnsafeUrlError("来源响应超过允许的大小上限")
        return Fetched(body=payload, content_type=content_type, charset=charset, url=final_url)
    raise UnsafeUrlError("重定向次数超过上限")
