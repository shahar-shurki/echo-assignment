# One-command reproducible build for the Echo nginx rebuild.
# Usage:
#   make build      Build the nginx .deb from upstream source (writes out/*.deb)
#   make clean      Remove built artifacts

NGINX_VERSION   ?= 1.25.5
PKG_REVISION    ?= 1+echo1
ARCH            ?= $(shell uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')

DEB_FILE        := nginx_$(NGINX_VERSION)-$(PKG_REVISION)_$(ARCH).deb
OUT_DIR         := out
IMAGE           ?= echo/nginx:1.25-bookworm

.PHONY: all build image test scan vex clean

TEST_VENV := test/.venv
VEX_FILE  := vex/echo-nginx.openvex.json

all: image

build: $(OUT_DIR)/$(DEB_FILE)

$(OUT_DIR)/$(DEB_FILE): build/Dockerfile build/patches/*.patch build/pkg/* build/pkg/html/*
	@echo ">>> Building nginx $(NGINX_VERSION)-$(PKG_REVISION) for $(ARCH)"
	@mkdir -p $(OUT_DIR)
	docker buildx build \
	    --file build/Dockerfile \
	    --target export \
	    --build-arg NGINX_VERSION=$(NGINX_VERSION) \
	    --build-arg PKG_REVISION=$(PKG_REVISION) \
	    --output type=local,dest=$(OUT_DIR) \
	    build
	@echo ">>> Produced: $@"
	@ls -lh $(OUT_DIR)/*.deb

image: build Containerfile build/rootfs/docker-entrypoint.sh
	@echo ">>> Building $(IMAGE) from $(OUT_DIR)/$(DEB_FILE)"
	docker build \
	    --file Containerfile \
	    --build-arg DEB_FILE=$(DEB_FILE) \
	    --build-arg NGINX_VERSION=$(NGINX_VERSION) \
	    --tag $(IMAGE) \
	    .
	@echo ">>> Image:"
	@docker image inspect $(IMAGE) --format '  {{.RepoTags}}  {{.Size}} bytes  ({{.Architecture}})'

$(TEST_VENV)/bin/pytest: test/requirements.txt
	python3 -m venv $(TEST_VENV)
	$(TEST_VENV)/bin/pip install -q --disable-pip-version-check -r test/requirements.txt
	@touch $@

test: image $(TEST_VENV)/bin/pytest
	@echo ">>> Pulling baseline image (if not present) and running compat suite"
	@docker pull -q nginx:1.25-bookworm
	OURS_IMAGE=$(IMAGE) $(TEST_VENV)/bin/pytest -v test/

scan: image
	@mkdir -p out
	@echo ">>> grype  -> out/grype-ours.txt"
	grype $(IMAGE)  > out/grype-ours.txt
	@echo ">>> trivy  -> out/trivy-ours.txt"
	trivy image $(IMAGE) > out/trivy-ours.txt
	@echo ""
	@echo ">>> CVE deltas vs baseline (grype):"
	@awk 'NR>1 {print $$5}' baseline-grype.txt 2>/dev/null | sort -u > /tmp/cve.baseline 2>/dev/null || true
	@awk 'NR>1 {print $$5}' out/grype-ours.txt   | sort -u > /tmp/cve.ours 2>/dev/null || true
	@echo "  removed by rebuild (in baseline, NOT in ours):"
	@comm -23 /tmp/cve.baseline /tmp/cve.ours | sed 's/^/    /' | head -30
	@echo "  added by rebuild (in ours, NOT in baseline):"
	@comm -13 /tmp/cve.baseline /tmp/cve.ours | sed 's/^/    /' | head -10

vex: image $(VEX_FILE)
	@echo ">>> grype WITHOUT vex — CVE-2026-42946 should still appear:"
	@grype $(IMAGE) 2>/dev/null | grep -E "VULNERABILITY|CVE-2026-42946" || echo "    (not found in default summary)"
	@echo ""
	@echo ">>> grype WITH vex ($(VEX_FILE)) — CVE-2026-42946 should disappear:"
	@grype $(IMAGE) --vex $(VEX_FILE) 2>/dev/null | grep -E "VULNERABILITY|CVE-2026-42946" || echo "    (gone)"
	@echo ""
	@echo ">>> trivy WITHOUT vex — CVE-2026-42946 should still appear:"
	@trivy image --quiet --severity HIGH,CRITICAL,MEDIUM $(IMAGE) 2>/dev/null | grep -E "CVE-2026-42946" || echo "    (not found)"
	@echo ""
	@echo ">>> trivy WITH vex ($(VEX_FILE)) — CVE-2026-42946 should disappear:"
	@trivy image --quiet --severity HIGH,CRITICAL,MEDIUM --vex $(VEX_FILE) $(IMAGE) 2>/dev/null | grep -E "CVE-2026-42946" || echo "    (gone)"

clean:
	rm -rf $(OUT_DIR) $(TEST_VENV)
	-docker rm -f compat-baseline compat-ours 2>/dev/null || true
	-docker image rm $(IMAGE) 2>/dev/null || true
