"""Use explicit OA metadata; the PDF loader may resolve declared citation PDF metadata."""
import ipaddress
import os
import socket
from urllib.parse import urlsplit, quote
import httpx
import ssl
import truststore


def public_https(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only public HTTPS resources are allowed")
    # Provider URLs are external input. Reject private and loopback destinations
    # so article retrieval cannot be used to request local services.
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Non-public address")
    return url


def http_client():
    # Use system certificate trust while keeping redirects manual: the loaders
    # must validate each destination, not just the first URL.
    return httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                        timeout=10, follow_redirects=False, trust_env=False)


def resolve_fulltext(paper):
    if paper.open_access_url:
        # Some OA providers advertise HTTP even when their HTTPS endpoint works.
        # Try HTTPS only; public_https still rejects credentials/private hosts.
        url = paper.open_access_url
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        return public_https(url)
    # Unpaywall requires an email; absence is an ordinary abstract fallback.
    email = os.environ.get("UNPAYWALL_EMAIL")
    if paper.doi and email:
        with http_client() as client:
            response = client.get("https://api.unpaywall.org/v2/" + quote(paper.doi, safe=""), params={"email": email})
            response.raise_for_status()
            data = response.json()
            location = data.get("best_oa_location") or {}
            url = location.get("url_for_pdf") or location.get("url_for_landing_page")
            if data.get("is_oa") and url:
                return public_https(url)
    return None
