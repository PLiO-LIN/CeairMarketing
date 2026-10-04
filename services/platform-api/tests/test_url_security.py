from __future__ import annotations

import socket
import urllib.error

import pytest

from app import url_security as us


def message(headers: dict[str, str]):
    from email.message import Message

    msg = Message()
    for key, value in headers.items():
        msg[key] = value
    return msg


class FakeResponse:
    def __init__(self, body: bytes, url: str, content_type="text/html", charset="utf-8"):
        self._body = body
        self.url = url
        self.headers = message({"Content-Type": f"{content_type}; charset={charset}" if charset else content_type})

    def read(self, size=-1):
        return self._body if size is None or size < 0 else self._body[:size]

    def geturl(self):
        return self.url

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Replays scripted responses so the redirect policy can be exercised offline.

    ``open`` performs a connect-time resolution exactly as ``urllib`` would, so a
    record that flips to a private address after validation is caught by the
    pinned resolver instead of being silently ignored.
    """

    def __init__(self, script):
        self.script = script
        self.calls: list[str] = []

    def open(self, request, timeout=None):
        from urllib.parse import urlparse

        self.calls.append(request.full_url)
        parsed = urlparse(request.full_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        item = self.script[request.full_url]
        if isinstance(item, Exception):
            raise item
        return item


def redirect(location, url="http://public.example/"):
    return urllib.error.HTTPError(url, 302, "Found", message({"Location": location}), None)


@pytest.fixture
def dns(monkeypatch):
    """Script hostname -> addresses, with an optional per-host call counter."""

    table: dict[str, list] = {}
    state = {"counters": {}}

    def fake_getaddrinfo(host, port, *args, **kwargs):
        entries = table.get(str(host))
        if entries is None:
            raise socket.gaierror(f"no scripted DNS for {host}")
        if callable(entries):
            entries = entries(state["counters"])
        state["counters"][str(host)] = state["counters"].get(str(host), 0) + 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, port or 80)) for ip in entries]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    return table


PUBLIC = "93.184.216.34"  # example.com: genuinely routable, unlike TEST-NET ranges


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "172.16.4.4", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1", "fc00::1", "::ffff:127.0.0.1"],
)
def test_is_public_rejects_restricted_addresses(address):
    assert us._is_public(address) is False


@pytest.mark.parametrize("address", [PUBLIC, "93.184.216.34", "2606:2800:220:1:248:1878:2510:3368"])
def test_is_public_allows_routable_addresses(address):
    assert us._is_public(address) is True


@pytest.mark.parametrize("value", ["ftp://public.example/feed", "file:///etc/passwd", "http://user:pass@public.example/", "not a url"])
def test_validate_public_url_rejects_bad_syntax(value):
    with pytest.raises(us.UnsafeUrlError):
        us.validate_public_url(value)


def test_validate_public_url_accepts_dns_resolved_public_host(dns):
    dns["public.example"] = [PUBLIC]
    assert us.validate_public_url("http://public.example/feed") == "http://public.example/feed"


def test_validate_public_url_blocks_host_resolving_to_metadata_ip(dns):
    dns["metadata.example"] = ["169.254.169.254"]
    with pytest.raises(us.UnsafeUrlError):
        us.validate_public_url("http://metadata.example/latest/meta-data/")


def test_safe_fetch_returns_body_and_charset(dns):
    dns["public.example"] = [PUBLIC]
    opener = FakeOpener({"http://public.example/feed": FakeResponse(b"<title>ok</title>", "http://public.example/feed", charset="utf-8")})
    result = us.safe_fetch("http://public.example/feed", opener=opener)
    assert result.body == b"<title>ok</title>"
    assert result.charset == "utf-8"
    assert opener.calls == ["http://public.example/feed"]


def test_safe_fetch_revalidates_redirect_target(dns):
    """A public host that bounces to an internal address must not be followed."""
    dns["public.example"] = [PUBLIC]
    opener = FakeOpener({
        "http://public.example/feed": redirect("http://127.0.0.1/admin"),
    })
    with pytest.raises(us.UnsafeUrlError):
        us.safe_fetch("http://public.example/feed", opener=opener)


def test_safe_fetch_blocks_redirect_to_private_host(dns):
    dns["public.example"] = [PUBLIC]
    dns["internal.example"] = ["10.0.0.5"]
    opener = FakeOpener({
        "http://public.example/feed": redirect("http://internal.example/steal"),
        "http://internal.example/steal": FakeResponse(b"secret", "http://internal.example/steal"),
    })
    with pytest.raises(us.UnsafeUrlError):
        us.safe_fetch("http://public.example/feed", opener=opener)
    assert opener.calls == ["http://public.example/feed"]


def test_safe_fetch_follows_redirect_to_public_host(dns):
    dns["public.example"] = [PUBLIC]
    dns["other.example"] = ["1.1.1.1"]
    opener = FakeOpener({
        "http://public.example/feed": redirect("http://other.example/feed"),
        "http://other.example/feed": FakeResponse(b"payload", "http://other.example/feed"),
    })
    assert us.safe_fetch("http://public.example/feed", opener=opener).body == b"payload"


def test_safe_fetch_caps_redirect_hops(dns):
    dns["public.example"] = [PUBLIC]
    loop = {f"http://public.example/hop{i}": redirect(f"http://public.example/hop{i + 1}", url=f"http://public.example/hop{i}") for i in range(10)}
    loop["http://public.example/"] = redirect("http://public.example/hop0")
    opener = FakeOpener(loop)
    with pytest.raises(us.UnsafeUrlError):
        us.safe_fetch("http://public.example/", opener=opener, max_redirects=2)
    assert len(opener.calls) == 3


def test_safe_fetch_enforces_response_size(dns):
    dns["public.example"] = [PUBLIC]
    opener = FakeOpener({"http://public.example/big": FakeResponse(b"x" * 4096, "http://public.example/big")})
    with pytest.raises(us.UnsafeUrlError):
        us.safe_fetch("http://public.example/big", opener=opener, max_bytes=1024)


def test_safe_fetch_pins_dns_against_rebinding(dns):
    """The record may flip to a private address after validation; the pinned set must stop it."""
    def rebinding(counters):
        # First lookup (validation) answers public, the connect-time lookup answers loopback.
        return [PUBLIC] if counters.get("rebind.example", 0) == 0 else ["127.0.0.1"]

    dns["rebind.example"] = rebinding
    opener = FakeOpener({"http://rebind.example/feed": FakeResponse(b"ok", "http://rebind.example/feed")})
    with pytest.raises(us.UnsafeUrlError):
        us.safe_fetch("http://rebind.example/feed", opener=opener)


def test_safe_fetch_wraps_unreachable_hosts(dns):
    # No scripted record for this host, so the fixture raises gaierror exactly as
    # a real resolver failure would.
    with pytest.raises(us.UnsafeUrlError):
        us.safe_fetch("http://down.example/feed", opener=FakeOpener({}))
