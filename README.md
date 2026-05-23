# Echo nginx rebuild — `nginx:1.25-bookworm` drop-in

A drop-in replacement for `docker.io/library/nginx:1.25-bookworm`, rebuilt
from upstream source on a current `debian:bookworm-slim` base, with two
explicit CVE remediations:

1. **Version bump**: `libssl3` floor raised from `3.0.0` to `3.0.15-1~deb12u1`
   in the .deb's `Depends`, closing CVE-2024-5535 (Critical) and ~9 other
   OpenSSL CVEs.
2. **Backport**: nginx's CVE-2026-42946 fix (`ngx_http_scgi_module`,
   `ngx_http_uwsgi_module`, `ngx_http_proxy_module`) backported from
   upstream nginx 1.30.1 onto the 1.25.5 source we ship.

Plus a VEX document covering both — re-run any scanner with `--vex
vex/echo-nginx.openvex.json` to drop both CVEs from the report.

---

## TL;DR

```
make build      # → out/nginx_1.25.5-1+echo1_arm64.deb
make image      # → echo/nginx:1.25-bookworm
make test       # → boots baseline + ours, runs 13 compat scenarios
make scan       # → out/{grype,trivy}-ours.txt and a CVE delta vs baseline
make vex        # → grype/trivy with --vex, showing the two CVEs drop
```

| | Baseline `nginx:1.25-bookworm` | Our `echo/nginx:1.25-bookworm` |
|---|---|---|
| `nginx -v` | `nginx/1.25.5` | `nginx/1.25.5` |
| `id nginx` | `uid=101, gid=101` | `uid=101, gid=101` |
| `libssl3` | `3.0.11-1~deb12u2` (May 2024) | `3.0.20-1~deb12u1` (Apr 2026) |
| Configure flags | (baseline) | identical (minus build-host `ffile-prefix-map`) |
| Installed packages | 149 | 90 |
| Image size | **193 MB** | **115 MB** (−40%) |
| Compat suite (13 scenarios) | n/a | **13/13 pass** byte-identical |
| Unique CVEs (grype) | **294** | **62** (with VEX) |

---

## Repo layout

```
.
├── baseline-trivy.txt            scan of upstream nginx:1.25-bookworm (input)
├── baseline-grype.txt
├── TRIAGE.md                     Triage step deliverable: which CVEs, why
├── Makefile                      one-command targets
├── Containerfile                 runtime image (installs our .deb)
├── build/
│   ├── Dockerfile                build environment (debian:bookworm-slim →
│   │                             fetch tarball, verify SHA, patch, configure,
│   │                             make, dpkg-deb --build)
│   ├── patches/
│   │   └── CVE-2026-42946.patch  unified diff vs pristine 1.25.5
│   ├── pkg/
│   │   ├── control               .deb metadata (Depends with the libssl3 floor)
│   │   ├── conffiles
│   │   ├── postinst              creates nginx user @ uid 101
│   │   ├── nginx.conf            ← captured from baseline
│   │   ├── default.conf          ← captured from baseline
│   │   └── html/*.html           ← captured from baseline
│   └── rootfs/
│       ├── docker-entrypoint.sh        ← captured from baseline
│       └── docker-entrypoint.d/*.sh    ← captured from baseline
├── test/
│   ├── conftest.py               pytest fixtures (boot baseline+ours)
│   ├── test_compat.py            13 parameterized scenarios
│   ├── custom.conf               bind-mounted into both for custom-config tests
│   └── requirements.txt
├── vex/
│   └── echo-nginx.openvex.json   OpenVEX v0.2.0
└── out/                          built artifacts (.deb, rescan reports)
```

---

## Build

Prereqs: Docker (with buildx), `python3 ≥ 3.10`, `trivy`, `grype`.

```sh
# 1) Build the .deb from upstream nginx 1.25.5 source, on a clean
#    debian:bookworm-slim base, with no pre-baked binaries.
make build
# → out/nginx_1.25.5-1+echo1_<arch>.deb

# 2) Build the runtime image (installs the .deb into a separate
#    debian:bookworm-slim).
make image
# → echo/nginx:1.25-bookworm

# 3) Run the compatibility suite. Boots baseline + ours, runs 13
#    HTTP scenarios, asserts status+headers+body match.
make test

# 4) Rescan with trivy + grype and print the CVE delta vs baseline.
make scan

# 5) Run grype/trivy WITH the VEX document and show CVE-2026-42946
#    and CVE-2023-44487 disappear.
make vex
```

The .deb is built inside Docker so the result is reproducible regardless
of host OS. Upstream source is pinned by SHA256 in `build/Dockerfile`:
`2fe2294f8af4144e7e842eaea884182a84ee7970e11046ba98194400902bbec0`.

---

## Per-CVE remediation table

| CVE | Severity | Where | Method | Evidence |
|---|---|---|---|---|
| **CVE-2024-5535** | Critical | `openssl` / `libssl3` (TLS SSL\_select\_next\_proto) | **Version bump** | `Depends: libssl3 (>= 3.0.15-1~deb12u1)` in [`build/pkg/control`](build/pkg/control); runtime installs `3.0.20-1~deb12u1`. `dpkg --compare-versions "3.0.11-1~deb12u2" ">=" "3.0.15-1~deb12u1"` returns false → an older libssl3 cannot satisfy our deps. |
| **CVE-2026-42946** | Medium | `nginx` `ngx_http_scgi_module` / `ngx_http_uwsgi_module` / `ngx_http_proxy_module` | **Backport** | [`build/patches/CVE-2026-42946.patch`](build/patches/CVE-2026-42946.patch) — combined backport of upstream commits [`baef7fda`](https://github.com/nginx/nginx/commit/baef7fdac28e4e1fe26509b50b8d15603393e28e) + [`39d7d0ba`](https://github.com/nginx/nginx/commit/39d7d0ba0799fcff6baee52b6525f45739593cfd) from nginx 1.30.1 onto 1.25.5. Scanner still flags it (version string unchanged); [`vex/echo-nginx.openvex.json`](vex/echo-nginx.openvex.json) makes it drop. |
| CVE-2023-44487 | High (KEV) | nginx HTTP/2 (Rapid Reset) | **VEX `not_affected`** (bonus) | Fix landed upstream in nginx 1.25.3 (Oct 2023); we ship 1.25.5 source. VEX justification: `vulnerable_code_not_present`. Scanner gap, not a real vuln. |

The brief asks for "at least 2 CVEs eliminated, where at least one is fixed by bumping the
version of a dependency, at least one is fixed by backporting." That's covered by
**CVE-2024-5535** (bump) + **CVE-2026-42946** (backport). The third row is a bonus that
demonstrates a different VEX use (`not_affected` vs `fixed`).

### Cascade: how the rebuild actually closed 230 CVEs

We picked 2 CVEs. The scan delta shows 230 unique-CVE removals. The math:

| Mechanism | CVEs closed | Counts toward brief? |
|---|---:|---|
| Component removal (149 → 90 packages: no `curl`, `libavif`, `libheif`, `libtiff`, `libxml2`, fonts, etc.) | 210 | **No** ("Removing components is fine for extras, but it doesn't count toward the requirement.") |
| Version bumps of all 90 packages we *do* install — both the explicit `libssl3` floor and the implicit current-base bump | 20 | **Yes** — this is the version-bump technique |
| VEX `fixed` (CVE-2026-42946) and `not_affected` (CVE-2023-44487) | 2 | The backport sits behind the VEX `fixed` statement; without VEX, scanners can't detect the patch |
| **Total scanner-visible eliminations** | **232** | |

So the 2 explicit picks satisfy the brief's *technique* requirement; the cascade is the
side-benefit of rebuilding from a current, lean base instead of repackaging the May-2024
image.

---

## Residual risk

After the rebuild + VEX, **62 unique CVEs** remain. Breakdown:

| Severity | Count | Comment |
|---|---:|---|
| Critical | 3 | 2 in `libgnutls30` with fix in `3.7.9-2+deb12u7` (very recently disclosed, not yet in `bookworm-security` mirror at scan time — next rebuild picks them up). 1 in `libc-bin` (`CVE-2026-5450`) with no fix yet upstream. |
| High | 8 | 4 more `libgnutls30` (same upcoming `+deb12u7` fix). 2 `libc-bin` (`CVE-2026-5435`, `CVE-2026-5928`) — no fix. `libtasn1-6 CVE-2025-13151` — won't-fix, upstream fix in 4.21.0 not packaged. `libtinfo6 CVE-2025-69720` — won't-fix. |
| Medium | 12 | Mostly `libc-bin`, `libpam`, `libsystemd0` won't-fix items. |
| Low / Negligible / Unknown | 39 | Long tail; mostly historical CVEs Debian deems too minor to backport. |

**Concrete next steps:**

1. **Rebuild on a tick** — `libgnutls30 3.7.9-2+deb12u7` lands in `bookworm-security` and a no-code-change rebuild closes 6 of the 11 Critical+High residuals on its own.
2. **Backport the `libtasn1-6` fix** — same pattern as CVE-2026-42946. Fix is at upstream tag `v4.21.0`; would be ~20 lines, defensible to patch ourselves. Debian's "won't fix" here is "no DSA; can ship in next point release."
3. **Drop more transitive deps** — `libgnutls30` and `libtasn1-6` are not linked by nginx. They're pulled in by `gnupg`/apt machinery during install. Removing the install-time tooling from the final layer (multi-stage with the `.deb` extracted, not `apt installed`) would drop ~10 more residuals at the cost of more Dockerfile complexity. Currently out of scope.
4. **CVE-2024-7347 (nginx mp4 module)** — not in either scanner's report (scanner-DB gap for nginx.org packages), but the source we ship is in the affected range (1.5.13–1.27.0). Worth a second backport patch on the next pass. Documented as known-but-unreported.

The 39 Low/Negligible/Unknown residuals are accepted: they're long-tail Debian-stable trade-offs (chrono CVEs in `libc-bin`, terminal-escape in older nginx error logs, etc.). VEX `not_affected` statements could trim them further, but each statement is engineering effort and the signal-to-noise on these is low.

---

## What surprised me / would do differently

**Surprises:**

- **Scanner coverage gaps.** Trivy doesn't track the `nginx` *package* at all
  when it comes from nginx.org's apt repo — only the system deps. Grype does,
  but its DB for that package is sparse. CVE-2024-7347 (a real, named nginx
  CVE that affects our binary) is in neither report. Don't trust scanner
  output as the *whole* picture; cross-reference Debian Security Tracker,
  nginx.org/security_advisories, etc.
- **"won't fix" is the signal for backport candidates.** Initially I was
  filtering it out as "Debian won't help." The reframe — *Debian punted, but
  upstream has a fix; that's exactly the backport opportunity* — is what
  led to CVE-2026-42946.
- **The image-size win was free.** I didn't set out to shrink the image, but
  the lean `.deb`-Depends approach dropped 59 packages and 78 MB anyway, which
  also drove most of the CVE delta.

**Would do differently with more time:**

- **Multi-arch.** Built arm64 only because the host is Apple Silicon. Adding
  `--platform=linux/amd64,linux/arm64` to the buildx invocation is trivial
  config; verifying the .deb works on both is more involved.
- **Dynamic modules.** Skipped `ngx_http_geoip_module`, `ngx_http_image_filter_module`,
  `ngx_stream_js_module`, `ngx_http_xslt_filter_module`. They live in
  `/usr/lib/nginx/modules/*.so` in the baseline and are not loaded by the
  default config, so the compat suite doesn't notice — but a strictly
  drop-in image should include them. Each comes from a separate nginx.org
  package; rebuilding them is the same recipe applied four more times.
- **Compat test depth.** 13 scenarios is enough for a sanity sweep but
  covers GET-heavy paths. I'd add: SSL termination with a self-signed cert,
  upstream proxying (`proxy_pass` to a sidecar), gzip negotiation, request
  pipelining, and stress / connection-limit behavior.
- **Sign the .deb and the image.** No signing in this submission. In a
  real Echo build pipeline I'd `dpkg-sig --sign builder` the .deb and
  `cosign sign` the image, and attach the VEX as a cosign attestation
  rather than a free-standing JSON file.
- **CI.** No CI configured. `make all && make test && make scan` would
  fit GitHub Actions cleanly; would gate merge on the compat suite +
  any new High/Critical that's not VEX'd.

---

## AI tool usage

I used Claude Code (Opus 4.7) throughout. Where it helped and where it didn't:

Helped:
- Going through the 465-line trivy report and the 294-CVE grype report by hand would have taken me a long time. I had it bucket the CVEs by remediation technique and surface the won't-fix ones, which is what pointed me at CVE-2026-42946.
- The mechanical patch work: pulling the two upstream commits, checking they applied cleanly to 1.25.5, combining them into one unified diff, and writing a sensible Debian-style header. I'd have done it manually otherwise; this was just faster.
- OpenVEX. I hadn't written one before. The model knew the v0.2.0 schema and the justification vocabulary, which saved me a trip through the spec.
- Pytest scaffolding for the compat suite. Fixtures and parametrized cases came together quickly.

Didn't help:
- Its first backport candidate was CVE-2024-7347. The CVE is real and our binary is actually vulnerable, but it isn't in either of my scan reports — the model proposed it from training data rather than from the input. I caught it by grepping the reports. After that I made a point of asking "show me where in the report you saw that" whenever a specific CVE came up.
- The HTTP/3 / `--with-http_v3_module` question got brushed off. It happened to work because nginx 1.25's QUIC compat layer handles vanilla OpenSSL 3.0+, but that was luck. I should have verified it before keeping the flag.

Overall: useful for the mechanical stuff, less useful for the judgment calls. Any specific claim — a CVE ID, a version number, a configure flag — I checked against the actual files myself.
