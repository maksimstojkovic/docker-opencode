# docker-opencode

Multi-arch (linux/amd64 + linux/arm64) Docker image for self-hosting
[opencode](https://opencode.ai/) — an open-source AI coding agent — behind a
[SWAG](https://docs.linuxserver.io/general/swag/) reverse proxy. Designed for
a Raspberry Pi 4 as a phone/browser-accessible replacement for the
ChatGPT/Claude.ai web chat experience, with OpenRouter as the default LLM
provider.

- **Base:** `alpine:3.20` with s6-overlay (linuxserver.io pattern)
- **Runs:** `opencode web --hostname 0.0.0.0 --port 4096`
- **Auth:** none in-container — SWAG (htpasswd/Authelia) handles it at the edge
- **Bundled tooling:** Python+matplotlib+pillow, ImageMagick, Graphviz, git,
  openssh-client, jq, ripgrep, fd — so the agent can produce text, code,
  diagrams and charts as artifacts
- **Auto-updates:** daily GitHub Actions workflow detects new upstream
  opencode releases, bumps `.opencode-version`, and rebuilds the image

## Prerequisites

- An existing [SWAG](https://docs.linuxserver.io/general/swag/) container with
  a wildcard or SAN cert covering `opencode.<your-domain>`
- An [OpenRouter](https://openrouter.ai/) API key (or credentials for any
  other opencode-supported provider)
- Docker + docker-compose on the host
- The host docker network that SWAG joins (we'll attach to it as an `external`
  network so SWAG can resolve `opencode` by container name)

## Quick start

```bash
# 1. Clone next to your SWAG compose stack
git clone https://github.com/maksimstojkovic/docker-opencode.git
cd docker-opencode

# 2. Create the host data directories
mkdir -p data/opencode/{config,workspace,ssh}

# 3. Drop your OpenRouter key into a .env file (gitignored)
cp .env.example .env
$EDITOR .env

# 4. Edit docker-compose.yml — change `swag` (external network name) to
#    whatever network your SWAG container joins. Adjust TZ if needed.

# 5. Pull and start
docker compose pull
docker compose up -d
docker compose logs -f opencode
```

You should see s6 supervise opencode and the line:

```
opencode web listening on http://0.0.0.0:4096
```

## Wire up SWAG

1. Copy the proxy template into your SWAG container:

   ```bash
   cp swag/opencode.subdomain.conf.sample \
      /path/to/swag/config/nginx/proxy-confs/opencode.subdomain.conf
   ```

2. (Optional) Enable basic auth — see the commented block in the template.

3. Restart SWAG: `docker restart swag`.

4. Browse to `https://opencode.<your-domain>`.

## First-run auth (OpenRouter)

OpenRouter is the default model provider. The container reads the key from the
`OPENROUTER_API_KEY` environment variable (passed via `.env` in
`docker-compose.yml`), and a seed `opencode.json` is written on first start
(see [Customising the default model](#customising-the-default-model) below).

For other providers that don't use env-var auth (e.g., OAuth-only ones, or
direct Anthropic/OpenAI accounts), run the interactive login once:

```bash
docker exec -it opencode opencode auth login
```

Credentials persist in `data/opencode/config/.local/share/opencode/auth.json`
and survive container restarts/upgrades.

## Customising the default model

The seed `opencode.json` written on first start uses:

| Setting       | Default                                       | Override env var          |
| ------------- | --------------------------------------------- | ------------------------- |
| `model`       | `openrouter/moonshotai/kimi-k2.6`             | `OPENROUTER_MODEL`        |
| `small_model` | `openrouter/meta-llama/llama-3.1-8b-instruct` | `OPENROUTER_SMALL_MODEL`  |

`model` is used for chat. `small_model` runs cheap housekeeping (session
titles, context summarisation). Set the env overrides in `.env` *before* the
first start. Any id listed on [openrouter.ai/models](https://openrouter.ai/models)
works.

After the seed file exists, the env vars are ignored — edit
`data/opencode/config/.config/opencode/opencode.json` directly to change models.

## Custom agents and slash commands

opencode picks up Markdown-frontmatter files from your bind-mount:

| Type                              | Path under `data/opencode/config/`   |
| --------------------------------- | ------------------------------------ |
| Agents (persona + tool set)       | `.config/opencode/agent/*.md`        |
| Slash commands (reusable prompts) | `.config/opencode/command/*.md`      |

Starter templates live in [`examples/opencode/`](examples/opencode/). Copy
the ones you want into the bind-mount:

```bash
mkdir -p data/opencode/config/.config/opencode/agent \
         data/opencode/config/.config/opencode/command
cp examples/opencode/agents/*.md   data/opencode/config/.config/opencode/agent/
cp examples/opencode/commands/*.md data/opencode/config/.config/opencode/command/
```

In the opencode TUI, `/agents` switches personas and `/<name>` runs a command.

## Adding an SSH key for git over SSH

The container does **not** mount your host `~/.ssh`. Instead, drop a
purpose-specific key (one you've added as a GitHub deploy key, not your main
personal key) into `data/opencode/ssh/`:

```bash
ssh-keygen -t ed25519 -f data/opencode/ssh/id_ed25519 -N "" -C "docker-opencode"
ssh-keyscan github.com >> data/opencode/ssh/known_hosts
chmod 600 data/opencode/ssh/id_ed25519
```

Add the resulting `data/opencode/ssh/id_ed25519.pub` as a deploy key on the
GitHub repo(s) you want the agent to clone/push. The container's init script
symlinks `/ssh` into the runtime user's `~/.ssh` so `git clone git@github.com:...`
works out of the box.

## Updating

When a new opencode release ships, the daily `upstream-check` workflow
auto-bumps `.opencode-version` and the `build` workflow publishes a new
`:<version>` and re-tags `:latest`. On the host:

```bash
docker compose pull
docker compose up -d
```

To pin a specific version instead of `:latest`, edit `docker-compose.yml`:

```yaml
image: ghcr.io/maksimstojkovic/docker-opencode:1.15.10
```

## Building locally (dev / amd64 smoke test)

```bash
docker compose -f docker-compose.dev.yml up --build
# → http://localhost:4096
```

To produce both architectures from your dev box and push to GHCR manually:

```bash
docker buildx create --use --name opencode-builder
docker login ghcr.io -u <username>
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --build-arg OPENCODE_VERSION=1.15.10 \
    -t ghcr.io/maksimstojkovic/docker-opencode:1.15.10 \
    -t ghcr.io/maksimstojkovic/docker-opencode:latest \
    --push \
    .
```

In CI, the `.github/workflows/build.yml` workflow does the equivalent
automatically on pushes to `main` that touch the Dockerfile, `root/`,
`scripts/`, or `.opencode-version`. It can also be triggered manually with a
custom version via the Actions UI.

## Repository layout

```
.
├── Dockerfile                                # alpine + s6-overlay + opencode
├── docker-compose.yml                        # Pi / production sample (uses GHCR)
├── docker-compose.dev.yml                    # Local build + port-publish for testing
├── root/                                     # Copied into the image at /
│   └── etc/
│       ├── cont-init.d/                      # PUID/PGID fixup + config seeding
│       │   ├── 10-fix-perms
│       │   └── 20-opencode-config
│       └── s6-overlay/s6-rc.d/
│           ├── svc-opencode/                 # Long-running opencode web service
│           │   ├── type
│           │   ├── run
│           │   └── dependencies.d/base
│           └── user/contents.d/svc-opencode  # Registers the service
├── swag/
│   └── opencode.subdomain.conf.sample        # Drop into SWAG proxy-confs/
├── examples/
│   └── opencode/
│       ├── agents/                           # Starter agent (persona) templates
│       │   ├── chat.md
│       │   └── agent.md
│       └── commands/                         # Starter slash command templates
│           ├── tldr.md
│           └── research.md
├── scripts/
│   └── check-upstream.sh                     # Compares upstream vs .opencode-version
├── .github/workflows/
│   ├── build.yml                             # Multi-arch build + push to GHCR
│   └── upstream-check.yml                    # Daily cron + workflow_dispatch
├── .opencode-version                         # Tracks last successfully built upstream
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

## Tags

| Tag                  | What it points to                                 |
| -------------------- | ------------------------------------------------- |
| `:latest`            | Most recent successful build (any `main` commit)  |
| `:<major>.<minor>`   | Floats forward across patches (e.g. `:1.15` → currently `1.15.10`, would move to `1.15.11` on next bump) |
| `:<major>.<minor>.<patch>` | Pin to a specific opencode release (e.g. `:1.15.10`) |
| `:sha-<7-char>`      | Pin to a specific commit of this repo             |

## Credits

- [opencode](https://github.com/anomalyco/opencode) — the upstream agent
- [linuxserver.io](https://www.linuxserver.io/) — SWAG + the PUID/PGID/s6 pattern
- [just-containers/s6-overlay](https://github.com/just-containers/s6-overlay)
