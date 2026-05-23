#!/usr/bin/env bash
# Check the latest upstream opencode release against .opencode-version and
# emit machine-readable outputs for GitHub Actions to act on.
#
# Inputs:
#   UPSTREAM_REPO   (default: anomalyco/opencode) — GitHub owner/repo to query
#   GITHUB_OUTPUT   (set automatically in GH Actions) — file to append outputs
#
# Outputs (when run under GH Actions):
#   latest_version  — newest upstream release version, leading "v" stripped
#   current_version — value of .opencode-version at script start
#   update_needed   — "true" iff latest_version differs from current_version

set -euo pipefail

UPSTREAM_REPO="${UPSTREAM_REPO:-anomalyco/opencode}"
VERSION_FILE=".opencode-version"

if [ ! -f "${VERSION_FILE}" ]; then
    echo "ERROR: ${VERSION_FILE} not found in repo root" >&2
    exit 1
fi

current_version="$(tr -d '[:space:]' < "${VERSION_FILE}")"

# Use the GitHub API; if a token is provided we'll use it to dodge anonymous
# rate limits (60 req/hr). Workflow-provided GITHUB_TOKEN is fine.
auth_header=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
    auth_header=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

api_url="https://api.github.com/repos/${UPSTREAM_REPO}/releases/latest"

response="$(curl -fsSL "${auth_header[@]}" "${api_url}")"
latest_tag="$(printf '%s' "${response}" | jq -r '.tag_name')"

if [ -z "${latest_tag}" ] || [ "${latest_tag}" = "null" ]; then
    echo "ERROR: could not parse tag_name from ${api_url}" >&2
    printf '%s\n' "${response}" | head -50 >&2
    exit 1
fi

# Strip leading "v" from "v1.15.10" → "1.15.10".
latest_version="${latest_tag#v}"

update_needed="false"
if [ "${latest_version}" != "${current_version}" ]; then
    update_needed="true"
fi

# Verify the expected release assets actually exist for both arches we ship.
# This guards against partial releases where the bot has cut the tag but
# binaries haven't uploaded yet — building against those would 404.
if [ "${update_needed}" = "true" ]; then
    missing=0
    for arch in arm64 x64; do
        asset_url="https://github.com/${UPSTREAM_REPO}/releases/download/v${latest_version}/opencode-linux-${arch}-musl.tar.gz"
        if ! curl -fsI -o /dev/null "${asset_url}"; then
            echo "WARN: expected asset not yet available: ${asset_url}" >&2
            missing=$((missing + 1))
        fi
    done
    if [ "${missing}" -gt 0 ]; then
        echo "WARN: ${missing} asset(s) missing — skipping bump this run" >&2
        update_needed="false"
    fi
fi

echo "current_version=${current_version}"
echo "latest_version=${latest_version}"
echo "update_needed=${update_needed}"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        echo "current_version=${current_version}"
        echo "latest_version=${latest_version}"
        echo "update_needed=${update_needed}"
    } >> "${GITHUB_OUTPUT}"
fi
