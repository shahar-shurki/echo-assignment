"""
Compatibility suite. For every scenario, fire the identical request at the
baseline image and our image; assert status, headers, and body match.

"Working correctly" =
  - same HTTP status code
  - same response body (byte-for-byte)
  - same response headers, EXCEPT:
      Date           - changes per second
      Last-Modified  - based on file mtime in the image layer; baseline was
                       built 2024-04, ours was built today
      ETag           - derived from mtime+size, same reason
      Connection     - sometimes ordered differently by the framework

Coverage:
  root                       static index.html served from /
  not-found                  404 for an unknown path
  HEAD                       HEAD request returns headers only
  50x-page                   static error page served via location = /50x.html
  POST-static                POST to a static location
  large-body-rejected        request body > client_max_body_size
  range-request              Range: bytes=0-50 -> 206 Partial Content
  if-modified-since-future   conditional GET with a future date -> 304
  options                    OPTIONS request
  custom-config-healthz      location added by mounted custom.conf
  custom-config-vars         the same location with $server_name / $uri substitution
  malformed-version          raw socket, request with bogus HTTP version

A non-zero pytest exit code = at least one scenario diverged.
"""

import socket
from urllib.parse import urlparse

import pytest
import requests


HEADERS_TO_IGNORE = {"date", "last-modified", "etag", "connection"}


def _norm_headers(h):
    return {k.lower(): v for k, v in dict(h).items() if k.lower() not in HEADERS_TO_IGNORE}


def _http_raw(base_url, payload: bytes) -> bytes:
    u = urlparse(base_url)
    with socket.create_connection((u.hostname, u.port), timeout=5) as s:
        s.sendall(payload)
        s.settimeout(3)
        chunks = []
        try:
            while True:
                c = s.recv(4096)
                if not c:
                    break
                chunks.append(c)
        except socket.timeout:
            pass
    return b"".join(chunks)


# Each scenario is a callable: base_url -> (status, headers_dict, body_bytes).
# For raw-socket scenarios, status is the status line string and headers={}.

def s_root(base):
    r = requests.get(f"{base}/", timeout=5)
    return r.status_code, r.headers, r.content

def s_not_found(base):
    r = requests.get(f"{base}/this-does-not-exist", timeout=5)
    return r.status_code, r.headers, r.content

def s_head(base):
    r = requests.head(f"{base}/", timeout=5)
    return r.status_code, r.headers, r.content

def s_50x_page(base):
    r = requests.get(f"{base}/50x.html", timeout=5)
    return r.status_code, r.headers, r.content

def s_post_static(base):
    r = requests.post(f"{base}/index.html", data=b"hello", timeout=5)
    return r.status_code, r.headers, r.content

def s_large_body_rejected(base):
    # Default client_max_body_size is 1m. A 2 MiB POST should be refused.
    r = requests.post(f"{base}/", data=b"x" * (2 * 1024 * 1024), timeout=10)
    return r.status_code, r.headers, r.content

def s_range_request(base):
    r = requests.get(f"{base}/index.html", headers={"Range": "bytes=0-50"}, timeout=5)
    return r.status_code, r.headers, r.content

def s_if_modified_since_future(base):
    r = requests.get(
        f"{base}/",
        headers={"If-Modified-Since": "Mon, 01 Jan 2099 00:00:00 GMT"},
        timeout=5,
    )
    return r.status_code, r.headers, r.content

def s_options(base):
    r = requests.options(f"{base}/", timeout=5)
    return r.status_code, r.headers, r.content

def s_malformed_version(base):
    raw = _http_raw(base, b"GET / HTTP/9.9\r\nHost: localhost\r\n\r\n")
    status_line = raw.split(b"\r\n", 1)[0].decode(errors="replace")
    return status_line, {}, raw


# Default-server scenarios (port 80).
DEFAULT_SCENARIOS = [
    ("root",                       s_root),
    ("not-found",                  s_not_found),
    ("HEAD",                       s_head),
    ("50x-page",                   s_50x_page),
    ("POST-static",                s_post_static),
    ("large-body-rejected",        s_large_body_rejected),
    ("range-request",              s_range_request),
    ("if-modified-since-future",   s_if_modified_since_future),
    ("options",                    s_options),
    ("malformed-version",          s_malformed_version),
]


@pytest.mark.parametrize(
    "name,scenario",
    DEFAULT_SCENARIOS,
    ids=[s[0] for s in DEFAULT_SCENARIOS],
)
def test_default_server(name, scenario, baseline_url, ours_url):
    bs, bh, bb = scenario(baseline_url)
    os_, oh, ob = scenario(ours_url)

    assert bs == os_, f"[{name}] status differs: baseline={bs!r} ours={os_!r}"
    assert _norm_headers(bh) == _norm_headers(oh), (
        f"[{name}] headers differ:\n  baseline={_norm_headers(bh)}\n  ours={_norm_headers(oh)}"
    )
    assert bb == ob, (
        f"[{name}] body differs (len: baseline={len(bb)} ours={len(ob)})\n"
        f"  baseline[:200]={bb[:200]!r}\n  ours[:200]={ob[:200]!r}"
    )


# Custom-config scenarios (port 8081 via mounted custom.conf).

def s_custom_healthz(base):
    r = requests.get(f"{base}/echo-healthz", timeout=5)
    return r.status_code, r.headers, r.content

def s_custom_vars(base):
    r = requests.get(
        f"{base}/echo-headers",
        headers={"User-Agent": "compat-suite/1.0"},
        timeout=5,
    )
    return r.status_code, r.headers, r.content

def s_custom_big_accepted(base):
    # location /echo-big raises client_max_body_size to 5m; 2 MiB should succeed.
    r = requests.post(f"{base}/echo-big", data=b"x" * (2 * 1024 * 1024), timeout=10)
    return r.status_code, r.headers, r.content


CUSTOM_SCENARIOS = [
    ("custom-healthz",      s_custom_healthz),
    ("custom-vars",         s_custom_vars),
    ("custom-big-accepted", s_custom_big_accepted),
]


@pytest.mark.parametrize(
    "name,scenario",
    CUSTOM_SCENARIOS,
    ids=[s[0] for s in CUSTOM_SCENARIOS],
)
def test_custom_config(name, scenario, baseline_custom_url, ours_custom_url):
    bs, bh, bb = scenario(baseline_custom_url)
    os_, oh, ob = scenario(ours_custom_url)

    assert bs == os_, f"[{name}] status differs: baseline={bs!r} ours={os_!r}"
    assert _norm_headers(bh) == _norm_headers(oh), (
        f"[{name}] headers differ:\n  baseline={_norm_headers(bh)}\n  ours={_norm_headers(oh)}"
    )
    assert bb == ob, (
        f"[{name}] body differs (len: baseline={len(bb)} ours={len(ob)})\n"
        f"  baseline[:200]={bb[:200]!r}\n  ours[:200]={ob[:200]!r}"
    )
