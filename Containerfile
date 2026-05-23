# Final runtime image — installs the .deb produced by build/Dockerfile and sets
# up the same entrypoint/env/ports/signals as nginx:1.25-bookworm so this image
# is a drop-in replacement.
#
# Build:    make image
# (which invokes `docker build -f Containerfile --build-arg DEB_FILE=… .`)

FROM debian:bookworm-slim

ARG DEB_FILE
ARG NGINX_VERSION=1.25.5
ARG PKG_RELEASE=1~bookworm

# Bring in our .deb and install it. apt-get install resolves runtime deps
# (libssl3, libpcre2-8-0, zlib1g, adduser, …) against the current bookworm
# repos — which is where the libssl3 3.0.11 → 3.0.20 version bump comes from.
COPY out/${DEB_FILE} /tmp/nginx.deb
RUN apt-get update \
    && apt-get install -y --no-install-recommends /tmp/nginx.deb \
    && rm -f /tmp/nginx.deb \
    && rm -rf /var/lib/apt/lists/*

# Docker scaffolding (entrypoint + drop-in scripts) — verbatim from upstream
# nginx:1.25-bookworm so behavior under `docker run` is identical.
COPY build/rootfs/docker-entrypoint.sh /docker-entrypoint.sh
COPY build/rootfs/docker-entrypoint.d/ /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.sh /docker-entrypoint.d/*.sh

# Match upstream image metadata so `docker inspect` looks the same to consumers.
ENV NGINX_VERSION=${NGINX_VERSION} \
    PKG_RELEASE=${PKG_RELEASE} \
    NJS_VERSION=0.8.4 \
    NJS_RELEASE=3~bookworm
EXPOSE 80
STOPSIGNAL SIGQUIT

LABEL maintainer="Echo Build <echo@build.local>" \
      org.opencontainers.image.title="nginx" \
      org.opencontainers.image.description="Drop-in replacement for nginx:1.25-bookworm with CVE backports." \
      org.opencontainers.image.source="https://github.com/echo/nginx-rebuild" \
      org.opencontainers.image.base.name="docker.io/library/debian:bookworm-slim" \
      org.opencontainers.image.version="${NGINX_VERSION}"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
