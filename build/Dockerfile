# syntax=docker/dockerfile:1.6
#
# Builds an nginx .deb from upstream source.
# Output: /out/nginx_<version>_<arch>.deb in the export stage.
#
# Build:    docker buildx build -f build/Dockerfile --target export --output type=local,dest=./out build
# (the Makefile wraps this)

FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

ARG NGINX_VERSION=1.25.5
ARG PKG_REVISION=1+echo1
ARG NGINX_SHA256=2fe2294f8af4144e7e842eaea884182a84ee7970e11046ba98194400902bbec0

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        build-essential dpkg-dev \
        libpcre2-dev libssl-dev zlib1g-dev \
        patch \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSL -o nginx.tar.gz "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" \
    && echo "${NGINX_SHA256}  nginx.tar.gz" | sha256sum -c - \
    && tar xzf nginx.tar.gz && rm nginx.tar.gz

WORKDIR /build/nginx-${NGINX_VERSION}

# Apply backport patches.
COPY patches/ /tmp/patches/
RUN for p in /tmp/patches/*.patch; do \
        echo "==> applying $p"; \
        patch -p1 --no-backup-if-mismatch < "$p"; \
    done \
    && grep -n "r->header_name_start = u->buffer.pos" \
           src/http/modules/ngx_http_scgi_module.c \
           src/http/modules/ngx_http_uwsgi_module.c \
           src/http/modules/ngx_http_proxy_module.c \
    || (echo "patch verification failed" && exit 1)

# Configure with the exact flags from nginx:1.25-bookworm's nginx -V (minus the
# build-host ffile-prefix-map). Dynamic modules (geoip/image_filter/njs/xslt)
# are separate nginx.org packages, not in scope here.
RUN ./configure \
        --prefix=/etc/nginx \
        --sbin-path=/usr/sbin/nginx \
        --modules-path=/usr/lib/nginx/modules \
        --conf-path=/etc/nginx/nginx.conf \
        --error-log-path=/var/log/nginx/error.log \
        --http-log-path=/var/log/nginx/access.log \
        --pid-path=/var/run/nginx.pid \
        --lock-path=/var/run/nginx.lock \
        --http-client-body-temp-path=/var/cache/nginx/client_temp \
        --http-proxy-temp-path=/var/cache/nginx/proxy_temp \
        --http-fastcgi-temp-path=/var/cache/nginx/fastcgi_temp \
        --http-uwsgi-temp-path=/var/cache/nginx/uwsgi_temp \
        --http-scgi-temp-path=/var/cache/nginx/scgi_temp \
        --user=nginx --group=nginx \
        --with-compat \
        --with-file-aio \
        --with-threads \
        --with-http_addition_module \
        --with-http_auth_request_module \
        --with-http_dav_module \
        --with-http_flv_module \
        --with-http_gunzip_module \
        --with-http_gzip_static_module \
        --with-http_mp4_module \
        --with-http_random_index_module \
        --with-http_realip_module \
        --with-http_secure_link_module \
        --with-http_slice_module \
        --with-http_ssl_module \
        --with-http_stub_status_module \
        --with-http_sub_module \
        --with-http_v2_module \
        --with-http_v3_module \
        --with-mail \
        --with-mail_ssl_module \
        --with-stream \
        --with-stream_realip_module \
        --with-stream_ssl_module \
        --with-stream_ssl_preread_module \
        --with-cc-opt='-g -O2 -fstack-protector-strong -Wformat -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2 -fPIC' \
        --with-ld-opt='-Wl,-z,relro -Wl,-z,now -Wl,--as-needed -pie' \
    && make -j"$(nproc)"

# Assemble the .deb root.
RUN mkdir -p /pkg/DEBIAN \
             /pkg/etc/nginx/conf.d \
             /pkg/usr/sbin \
             /pkg/usr/share/nginx/html \
             /pkg/usr/share/doc/nginx \
             /pkg/usr/lib/nginx/modules \
             /pkg/var/log/nginx \
             /pkg/var/cache/nginx \
    && make DESTDIR=/pkg install \
    # nginx's `make install` puts html under /etc/nginx/html — move it to /usr/share/nginx/html to match upstream image.
    && mv /pkg/etc/nginx/html/* /pkg/usr/share/nginx/html/ \
    && rmdir /pkg/etc/nginx/html \
    # Default index.html / 50x.html come from the source, but the upstream image
    # ships slightly different ones. Use the source-provided versions.
    # nginx's install leaves a stray default `nginx.conf.default`; remove.
    && rm -f /pkg/etc/nginx/*.default \
    # Provide a minimal conf.d/default.conf matching upstream
    && true

COPY pkg/default.conf /pkg/etc/nginx/conf.d/default.conf

# Override nginx.conf to match the upstream image (writes to /var/run/nginx.pid,
# user nginx, includes conf.d/*.conf).
COPY pkg/nginx.conf /pkg/etc/nginx/nginx.conf

# Use the same default index.html / 50x.html as the upstream image.
COPY pkg/html/ /pkg/usr/share/nginx/html/

# Symlink access/error logs to stdout/stderr so docker logs picks them up.
RUN ln -sf /dev/stdout /pkg/var/log/nginx/access.log \
    && ln -sf /dev/stderr /pkg/var/log/nginx/error.log \
    # The /etc/nginx/modules symlink in the upstream image points to /usr/lib/nginx/modules.
    && ln -sf /usr/lib/nginx/modules /pkg/etc/nginx/modules

# DEBIAN/ metadata
COPY pkg/control /pkg/DEBIAN/control
COPY pkg/conffiles /pkg/DEBIAN/conffiles
COPY pkg/postinst /pkg/DEBIAN/postinst
RUN chmod 755 /pkg/DEBIAN/postinst \
    && ARCH=$(dpkg --print-architecture) \
    && VERSION="${NGINX_VERSION}-${PKG_REVISION}" \
    && sed -i "s|__ARCH__|${ARCH}|; s|__VERSION__|${VERSION}|" /pkg/DEBIAN/control \
    && mkdir -p /out \
    && dpkg-deb --root-owner-group --build /pkg "/out/nginx_${VERSION}_${ARCH}.deb" \
    && ls -lh /out/

# Tiny export stage so `docker buildx --output type=local` can extract the .deb cleanly.
FROM scratch AS export
COPY --from=builder /out/*.deb /
