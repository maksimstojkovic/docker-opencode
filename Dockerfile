# syntax=docker/dockerfile:1.7
FROM debian:trixie-slim

ARG OPENCODE_VERSION
ARG TARGETARCH
ARG S6_OVERLAY_VERSION=3.2.0.2
ARG DEBIAN_FRONTEND=noninteractive

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    HOME=/config \
    XDG_CONFIG_HOME=/config/.config \
    XDG_DATA_HOME=/config/.local/share \
    XDG_STATE_HOME=/config/.local/state \
    XDG_CACHE_HOME=/config/.cache \
    PUID=1000 \
    PGID=1000 \
    TZ=Etc/UTC

# Core runtime + artifact tooling.
# - bash:          opencode and various agent tool calls assume bash exists
#                  (debian-slim ships /bin/sh as dash; bash is not installed by default)
# - python3 + python3-matplotlib/python3-pil: chart and image artifact generation.
#   apt packages cover what we need; pip wheels work cleanly on glibc if extras
#   are needed later.
# - imagemagick, graphviz: image conversion + diagram rendering. ImageMagick's
#   default policy.xml blocks PDF/PS/EPS for Ghostscript-CVE reasons; relaxed
#   below so the agent can convert those formats.
# - git + openssh-client + ca-certificates: repo operations over SSH/HTTPS
# - jq + ripgrep + fd-find: data wrangling tools the agent reaches for constantly.
#   Debian renames the fd binary to fdfind; symlinked to /usr/bin/fd below.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked,id=apt-${TARGETARCH} \
    --mount=type=cache,target=/var/lib/apt,sharing=locked,id=aptlists-${TARGETARCH} \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl tar xz-utils \
        bash tzdata \
        git openssh-client \
        jq ripgrep fd-find \
        imagemagick graphviz \
        python3 python3-matplotlib python3-pil \
    && ln -sf /usr/bin/fdfind /usr/bin/fd \
    && sed -i 's|<policy domain="coder" rights="none" pattern="\(PDF\|PS\|PS2\|PS3\|EPS\|XPS\)" />|<policy domain="coder" rights="read\|write" pattern="\1" />|g' /etc/ImageMagick-6/policy.xml || true

# s6-overlay (linuxserver.io's init system of choice) — proper PID 1,
# parallel service supervision, and the PUID/PGID hook pattern.
RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64)  S6_ARCH=x86_64 ;; \
        arm64)  S6_ARCH=aarch64 ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" \
        | tar -Jxpf - -C /; \
    curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" \
        | tar -Jxpf - -C /

# Copy s6 service definitions and init scripts. Placed before the opencode
# download so version bumps (most frequent change) don't invalidate this layer.
COPY root/ /

# Install opencode from upstream GitHub release.
# Canonical upstream is anomalyco/opencode (sst/opencode redirects there).
# Upstream ships the glibc binary with no suffix; the -musl variant is the
# alpine one. We pull the unsuffixed tarball.
RUN set -eux; \
    if [ -z "${OPENCODE_VERSION}" ]; then echo "OPENCODE_VERSION build-arg is required" >&2; exit 1; fi; \
    case "${TARGETARCH}" in \
        amd64)  OC_ARCH=x64 ;; \
        arm64)  OC_ARCH=arm64 ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${OC_ARCH}.tar.gz" \
        | tar -xz -C /usr/local/bin; \
    chmod +x /usr/local/bin/opencode; \
    /usr/local/bin/opencode --version

# Create the runtime user. UID/GID get reconciled to PUID/PGID at container
# start by /etc/cont-init.d/10-fix-perms; defaults match linuxserver.io convention.
# Login shell is the opencode-shell wrapper (clears the PTY before exec'ing
# bash) — see /usr/local/bin/opencode-shell for the why.
# -M skips home-dir creation because /config is a VOLUME; install -d sets
# ownership without populating skeleton files that would shadow user data
# on bind-mount.
RUN groupadd -g 1000 opencode \
    && useradd -u 1000 -g opencode -d /config -s /usr/local/bin/opencode-shell -M opencode \
    && install -d -o opencode -g opencode -m 755 /config /workspace \
    && mkdir -p /ssh \
    # Mark scripts executable by directory pattern so adding new cont-init
    # hooks, s6 services, opencode-* wrappers, or MCP servers doesn't
    # require Dockerfile changes — just drop the file under root/ and rebuild.
    && chmod +x \
        /etc/cont-init.d/* \
        /etc/s6-overlay/s6-rc.d/*/run \
        /usr/local/bin/opencode-* \
        /usr/local/lib/opencode-mcp/*

# OCI labels for the registry.
LABEL org.opencontainers.image.title="docker-opencode" \
      org.opencontainers.image.description="Self-hostable opencode (AI coding agent) for ARM64/AMD64, designed to sit behind a SWAG reverse proxy" \
      org.opencontainers.image.source="https://github.com/maksimstojkovic/docker-opencode" \
      org.opencontainers.image.licenses="MIT"

EXPOSE 4096
VOLUME ["/config", "/workspace", "/ssh"]

# Probe opencode's API health endpoint. curl is installed above.
# --start-period gives s6 + opencode time to come up on slower hardware
# (Pi 4 cold start ~10-15s). --max-time keeps the probe within the
# healthcheck timeout.
#
# URL-embedded credentials let the probe authenticate when OPENCODE_SERVER_PASSWORD
# is set. /global/health is NOT exempt from opencode's basic-auth middleware, so a
# password-protected instance returns 401 to an unauthenticated probe and the
# container would be marked unhealthy. When the password is unset, opencode skips
# auth entirely and the empty creds are ignored.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS --max-time 8 -o /dev/null \
        "http://${OPENCODE_SERVER_USERNAME:-opencode}:${OPENCODE_SERVER_PASSWORD:-}@127.0.0.1:4096/global/health" \
        || exit 1

ENTRYPOINT ["/init"]
