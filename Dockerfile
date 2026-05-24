# syntax=docker/dockerfile:1.7
FROM alpine:3.20

ARG OPENCODE_VERSION
ARG TARGETARCH
ARG S6_OVERLAY_VERSION=3.2.0.2

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
# - shadow:        provides usermod/groupmod (alpine's busybox versions lack the -o flag)
# - bash:          opencode and various agent tool calls assume bash exists
# - gcompat:       glibc compatibility shim. Bun (opencode's runtime) extracts a
#                  helper .so at runtime that references glibc-only symbols like
#                  gnu_get_libc_version; without gcompat, dlopen fails and FFI-
#                  dependent features (session titles, summarisation) silently die.
# - python3 + py3-matplotlib/py3-pillow: chart and image artifact generation
#   (no py3-pip — apk packages cover what we need; runtime pip install on
#    musl needs gcc/musl-dev and is rarely worth it)
# - imagemagick, graphviz: image conversion + diagram rendering
# - git + openssh-client + ca-certificates: repo operations over SSH/HTTPS
# - jq + ripgrep + fd: data wrangling tools the agent reaches for constantly
RUN --mount=type=cache,target=/var/cache/apk,sharing=locked,id=apk-${TARGETARCH} \
    --mount=type=cache,target=/etc/apk/cache,sharing=locked,id=apkcache-${TARGETARCH} \
    apk add \
        ca-certificates curl tar xz \
        bash shadow tzdata gcompat \
        git openssh-client \
        jq ripgrep fd \
        imagemagick graphviz \
        python3 py3-matplotlib py3-pillow

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

# Install opencode from upstream GitHub release.
# Canonical upstream is anomalyco/opencode (sst/opencode redirects there).
# Pulls the -musl variant because the base image is alpine.
RUN set -eux; \
    if [ -z "${OPENCODE_VERSION}" ]; then echo "OPENCODE_VERSION build-arg is required" >&2; exit 1; fi; \
    case "${TARGETARCH}" in \
        amd64)  OC_ARCH=x64 ;; \
        arm64)  OC_ARCH=arm64 ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${OC_ARCH}-musl.tar.gz" \
        | tar -xz -C /usr/local/bin; \
    chmod +x /usr/local/bin/opencode; \
    /usr/local/bin/opencode --version

# Copy s6 service definitions and init scripts.
COPY root/ /

# Create the runtime user. UID/GID get reconciled to PUID/PGID at container
# start by /etc/cont-init.d/10-fix-perms; defaults match linuxserver.io convention.
RUN addgroup -g 1000 opencode \
    && adduser -D -u 1000 -G opencode -h /config -s /bin/bash opencode \
    && mkdir -p /config /workspace /ssh \
    && chown -R opencode:opencode /config /workspace \
    && chmod +x /etc/cont-init.d/* /etc/s6-overlay/s6-rc.d/svc-opencode/run

# OCI labels for the registry.
LABEL org.opencontainers.image.title="docker-opencode" \
      org.opencontainers.image.description="Self-hostable opencode (AI coding agent) for ARM64/AMD64, designed to sit behind a SWAG reverse proxy" \
      org.opencontainers.image.source="https://github.com/maksimstojkovic/docker-opencode" \
      org.opencontainers.image.licenses="MIT"

EXPOSE 4096
VOLUME ["/config", "/workspace", "/ssh"]

# Probe opencode's API health endpoint. wget is part of busybox so no extra
# install is needed. --start-period gives s6 + opencode time to come up on
# slower hardware (Pi 4 cold start ~10-15s).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget -q --spider --tries=1 http://127.0.0.1:4096/global/health || exit 1

ENTRYPOINT ["/init"]
