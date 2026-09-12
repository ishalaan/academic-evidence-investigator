"""Use explicit OA metadata; never scrape landing pages or bypass restrictions."""
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
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Non-public address")
    return url


def http_client():
    return httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                        timeout=10, follow_redirects=False, trust_env=False)


def resolve_fulltext(paper):
    if paper.open_access_url:
        return public_https(paper.open_access_url)
    # Unpaywall requires an email; absence is an ordinary abstract fallback.
    email = os.environ.get("UNPAYWALL_EMAIL")
    if paper.doi and email:
        with http_client() as client:
            response = client.get("https://api.unpaywall.org/v2/" + quote(paper.doi, safe=""), params={"email": email})
            response.raise_for_status()
            data = response.json()
            location = data.get("best_oa_location") or {}
            url = location.get("url_for_pdf")
            if data.get("is_oa") and url:
                return public_https(url)
    return None
