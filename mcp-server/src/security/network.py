"""Bounded public HTTP access. Every redirect target is revalidated."""
import ipaddress
import socket
import urllib.parse
import urllib.request


def safe_public_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Only public HTTP(S) URLs without credentials are allowed")
    if p.port and p.port not in (80, 443):
        raise ValueError("Nonstandard ports are blocked")
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError("Host did not resolve")
        for info in addresses:
            if not ipaddress.ip_address(info[4][0]).is_global:
                raise ValueError("Private or non-global network address blocked")
    except socket.gaierror as exc:
        raise ValueError("Host did not resolve") from exc
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_public_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_open(req, timeout=12):
    safe_public_url(req.full_url)
    return urllib.request.build_opener(SafeRedirect()).open(req, timeout=timeout)


def request_bytes(url, *, data=None, headers=None, timeout=10, max_bytes=2_000_000, content_types=None):
    """Fetch bounded bytes through the same SSRF/redirect policy for all providers."""
    safe_public_url(url)
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with safe_open(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        content_type = response.headers.get_content_type()
        if content_types and content_type not in content_types:
            raise ValueError(f"Unexpected content type: {content_type}")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"Response exceeds {max_bytes} byte limit")
        return body, content_type, response.headers.get_content_charset() or "utf-8", response.geturl()
