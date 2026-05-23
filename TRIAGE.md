# Triage

Source reports: `baseline-trivy.txt` (465 findings), `baseline-grype.txt` (~390 findings).
Risk ordering taken from grype (which is sorted by risk score = severity × EPSS).

## Scope notes

- Trivy does not track the `nginx` package at all (nginx.org's apt-repo origin is filtered out of its package DB). Only grype reports nginx-package CVEs. We treat the two reports as the union.
- `ldd $(which nginx)` shows nginx links only: libssl/libcrypto (openssl), libpcre2, libz, libc, libcrypt. Every other library in the image (libtiff, libxml2, libldap, libexpat, libheif, libavif, …) is transitive dep of other tools (curl, dpkg, apt), not used by nginx at runtime. Triage prioritizes accordingly.

## Findings on the nginx package itself

| CVE | Severity | Where | Upstream fix | Remediation |
|---|---|---|---|---|
| CVE-2023-44487 (HTTP/2 Rapid Reset) | High (KEV) | HTTP/2 framing | Fixed in nginx 1.25.3 | **Already fixed in 1.25.5.** Scanner false-positive. → VEX `not_affected` |
| **CVE-2026-42946** | **Medium** | `ngx_http_scgi_module`, `ngx_http_uwsgi_module` (excessive memory allocation / over-read) | **Fixed in nginx 1.30.1** (commits `baef7fdac28e4e1fe26509b50b8d15603393e28e`, `39d7d0ba0799fcff6baee52b6525f45739593cfd`) — Debian status: **postponed / won't fix** | **Backport** |
| CVE-2013-0337 | Low | Default config file perms | "Won't fix" | Out of scope; not a code patch |
| CVE-2009-4487 | Negligible | Terminal escape sequences in error log | No upstream fix planned | Out of scope |

## Findings on libraries nginx actually links

These are the runtime-relevant CVEs. All affect `libssl3` / `openssl` (`3.0.11-1~deb12u2` in the baseline image — released May 2024). Every one of them has a fix in a newer Debian package; none are won't-fix.

| CVE | Severity | Fixed in (Debian) | Remediation |
|---|---|---|---|
| **CVE-2024-5535** | **Critical** | `3.0.15-1~deb12u1` | **Version bump** |
| CVE-2024-6119 | High | `3.0.14-1~deb12u2` | Version bump (covered by above) |
| CVE-2024-4741 | High | `3.0.14-1~deb12u1` | Version bump (covered) |
| CVE-2025-15467 | High | `3.0.18-1~deb12u2` | Version bump (covered) |
| CVE-2025-69420 | High | `3.0.18-1~deb12u2` | Version bump (covered) |
| CVE-2024-2511 | Medium | `3.0.14-1~deb12u1` | Version bump (covered) |
| CVE-2024-9143 | Medium | `3.0.15-1~deb12u1` | Version bump (covered) |
| CVE-2023-5678 | Medium | `3.0.13-1~deb12u1` | Version bump (covered) |
| CVE-2023-6129 | Medium | `3.0.13-1~deb12u1` | Version bump (covered) |
| CVE-2023-6237 | Medium | `3.0.13-1~deb12u1` | Version bump (covered) |

Bumping libssl3 / openssl to the current bookworm-security version (`3.0.20-1~deb12u1` at time of writing) closes all ten in one go. No backports needed in this lane because Debian keeps openssl current.

## Findings on transitive-only libraries (nginx does not link)

Surveyed but deprioritized for engineering effort. Examples:
- `libtiff6` CVE-2023-52355 (High, won't-fix): Debian tracker says "Minor issue, **no code fix, just updated docs**" — not a code-patch backport candidate.
- `libxml2` critical CVEs (CVE-2024-56171, CVE-2025-49794, CVE-2025-49796) — all have Debian fixes in `2.9.14+dfsg-1.3~deb12u2` / `…u3`. Closed by the same `apt-get upgrade` that bumps openssl.
- `libexpat1` criticals (CVE-2024-45491, CVE-2024-45492) — same story, Debian-fixed.
- `libldap-2.5-0` CVE-2023-2953 (High, no-DSA) — has an upstream fix in OpenLDAP 2.5.16, but the library is unused by nginx → low priority.

The single `apt-get upgrade` on the build base implicitly closes ~30 critical/high CVEs across these libs. We get that for free as part of the openssl version-bump path.

## Picks

| # | CVE | Technique | Why |
|---|---|---|---|
| 1 | **CVE-2024-5535** (and ~9 other openssl CVEs in the same bump) | **Version bump**: libssl3/openssl `3.0.11-1~deb12u2` → current Debian security (`3.0.20-1~deb12u1`) | Highest-value single change. Closes a Critical + multiple Highs that nginx actually links. Evidence: `dpkg -l libssl3` before/after and a delta on the rescan. |
| 2 | **CVE-2026-42946** | **Backport** of upstream nginx commits `baef7fdac28…` and `39d7d0ba0799…` from nginx 1.30.1 onto our 1.25.5 build | In nginx itself, in the report, Debian explicitly **won't fix** so we must do it ourselves, has a clean named upstream fix. Patches scgi/uwsgi modules which have been stable across 1.25 → 1.30, so the diff should apply with at most trivial conflicts. **Used for the VEX disappearance demo** — scanner will still flag 1.25.5 post-patch (version string unchanged), VEX `fixed` justification drops it. |

### Why not the alternatives

- **CVE-2023-44487 as the backport target**: 1.25.5 already includes the fix (it landed in 1.25.3). There's literally nothing to backport. We'll still emit a VEX `not_affected` for it as a bonus — that's a *different* and equally instructive use of VEX (justification-by-existing-fix vs justification-by-backport-patch). Adds, doesn't replace.
- **A libtiff / libxml2 / libldap backport**: nginx doesn't link any of them. Patching a library nginx never loads is engineering theatre — not what the brief is testing.
- **CVE-2024-7347 (nginx mp4 module)**: legitimate vulnerability in our binary (`--with-http_mp4_module` is on, version is in affected range 1.5.13–1.27.0). Not in either scanner report, though — scanner DBs have a gap on nginx.org's apt repo. Noted under residual risk; not a primary pick because the brief is anchored to "CVEs in the reports."

## Residual risk preview (full version goes in README)

After the two picks land:

- The openssl bump implicitly closes ~30 other critical/high CVEs across libxml2, libexpat, libfreetype6, libssl, kerberos, etc. — all from the same `apt-get upgrade`. Free win.
- "Won't fix" CVEs in transitive libs (libtiff, libldap, libtasn1, libde265, libheif, libavif, …) remain. None reachable through nginx code paths in a default config. Mitigation: drop those packages from the final image entirely (image-shrink work, but counts as "removal" not a technique under the brief).
- CVE-2024-7347 (mp4 module) is real and unflagged by both scanners. Documented as known residual.
- `coreutils`, `tar`, `bash` "won't fix" CVEs are non-network-reachable through nginx; low priority.
