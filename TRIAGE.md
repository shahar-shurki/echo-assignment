# Triage

Source reports: `baseline-trivy.txt` (465 findings), `baseline-grype.txt` (~390). Ranked by grype's risk score (severity × EPSS), then cross-checked against Debian Security Tracker for any "won't fix" entries that might be backport candidates.

Two scoping facts shaped the picks:

- **Trivy doesn't track the `nginx` package itself** when it comes from nginx.org's apt repo — only grype does. So the union of the two reports is the working set.
- **`ldd $(which nginx)` shows nginx links only**: libssl, libcrypto, libpcre2, libz, libc, libcrypt. Everything else in the image (libtiff, libxml2, libldap, libexpat, libheif, libavif, …) is transitive from other tools and not used by nginx at runtime. The library that matters most for remediation is libssl3.

## Picks

| # | CVE | Severity | Technique | Why |
|---|---|---|---|---|
| 1 | **CVE-2024-5535** | Critical | **Version bump**: libssl3 floor `>= 3.0.15-1~deb12u1` | Highest-impact single change. Closes a Critical and ~9 other High/Medium OpenSSL CVEs in one go (the openssl 3.0.11 → 3.0.20 jump that comes with rebuilding from a current `debian:bookworm-slim`). libssl3 is the most-linked dep of nginx. |
| 2 | **CVE-2026-42946** | Medium | **Backport** from nginx 1.30.1 (commits `baef7fda` + `39d7d0ba`) | In nginx itself, in the report, Debian status: postponed/won't-fix. Patches scgi/uwsgi/proxy status-line parsing — modules that have been stable across 1.25 → 1.30, so the diff applies cleanly to 1.25.5. Doubles as the VEX-disappearance demo: scanners still flag 1.25.5 post-patch (version unchanged), VEX `fixed` drops it. |

## Why these specifically

- **CVE-2024-5535 over the other 9 openssl CVEs**: they all close together with a single version bump, but CVE-2024-5535 is Critical so it's the natural headline. Listing it as the pick implies the others.
- **CVE-2026-42946 over CVE-2023-44487 as backport target**: HTTP/2 Rapid Reset's fix landed upstream in nginx 1.25.3; we ship 1.25.5 source so there's *nothing to backport*. CVE-2023-44487 gets a VEX `not_affected` instead — useful but different.
- **Why not a system-library backport (libtiff, libldap, libxml2, …)**: nginx doesn't link any of them. Patching a library nginx never loads doesn't demonstrate the workflow honestly.
