# Using opencode — a practical reference

This is a community reference guide for getting real value out of an opencode
deployment, framed around using it as a self-hosted replacement for browser
chat (ChatGPT, Claude.ai, Gemini) rather than as a pure coding agent.

It covers the configuration surface (`opencode.json`), agents, slash commands,
MCP servers, LSP integration, plugins, permissions, and headless usage —
with concrete examples for each.

> **Source of truth.** opencode evolves quickly. When this guide and
> [opencode.ai/docs](https://opencode.ai/docs) disagree, the official docs
> win — please open an issue or PR against this file. The examples here are
> tested against opencode 1.15.x.

---

## Table of contents

- [Mental model](#mental-model)
- [Configuration: `opencode.json`](#configuration-opencodejson)
- [Providers and models](#providers-and-models)
- [Agents](#agents)
- [Slash commands](#slash-commands)
- [MCP servers](#mcp-servers)
- [LSP servers](#lsp-servers)
- [Plugins](#plugins)
- [Permissions](#permissions)
- [Instructions (rules) files](#instructions-rules-files)
- [Interfaces: TUI, web, CLI](#interfaces-tui-web-cli)
- [Sessions, sharing, compaction](#sessions-sharing-compaction)
- [Patterns that pay off](#patterns-that-pay-off)
- [Troubleshooting](#troubleshooting)
- [Further reading](#further-reading)

---

## Mental model

opencode is three things at once:

1. **A chat client** with TUI, web, and CLI front-ends, talking to any LLM
   provider you wire up (OpenRouter, Anthropic, OpenAI, Google, local Ollama,
   etc.).
2. **An agent harness** — the LLM can call tools (shell, file I/O, web fetch,
   custom MCP tools) to actually *do* things, not just describe them.
3. **A configurable workspace** — every behaviour above is customisable via
   markdown files, JSON config, and JavaScript/TypeScript plugins.

Two execution patterns matter:

- **Chat mode** — you drive, the model answers. Use this for replacement of
  ChatGPT-style use, drafting, research, Q&A.
- **Delegation mode** — you set a goal, the agent loops through tools until
  it's done. Use this for "go read these PDFs and summarise", "triage my
  inbox", "rebuild the auth flow".

**Customisation layers**, from quickest to most powerful:

| Layer            | What it changes                            | File type             |
| ---------------- | ------------------------------------------ | --------------------- |
| Config           | Defaults: model, provider, share, paths    | `opencode.json`       |
| Instructions     | System-prompt rules applied to all chats   | markdown              |
| Agents           | Persona + tool set + model + permissions   | markdown w/ frontmatter |
| Slash commands   | Reusable parameterised prompts             | markdown w/ frontmatter |
| MCP servers      | New tools the model can call               | JSON config           |
| LSP servers      | Code intelligence for repos                | JSON config           |
| Plugins          | Event hooks + custom tools in JS/TS        | JavaScript/TypeScript |

**Two file scopes:**

- **Global** — `~/.config/opencode/` (per-user, shared across all projects)
- **Project** — `.opencode/` (in repo root, scoped to one project)

In the Docker image, "global" is `/config/.config/opencode/` inside the
container, which is the bind-mount you exposed as
`data/opencode/config/.config/opencode/` on the host.

---

## Configuration: `opencode.json`

The primary config file. Lives at `~/.config/opencode/opencode.json` (global)
or `.opencode/opencode.json` (project). Project config overrides global.

### Annotated full example

```jsonc
{
  // Lets editors fetch type hints and validation.
  "$schema": "https://opencode.ai/config.json",

  // Default model used for chat unless an agent or /model overrides it.
  // Format: <provider-id>/<model-id>.
  "model": "openrouter/moonshotai/kimi-k2.6",

  // Cheap model used for housekeeping (session titles, summarisation,
  // suggestions). Should be fast and cheap — quality matters less here.
  "small_model": "openrouter/meta-llama/llama-3.1-8b-instruct",

  // Which agent loads by default (must be a *primary* agent, see Agents).
  "default_agent": "build",

  // Provider-level settings. Most providers need only an API key; you
  // can also set timeouts, custom headers, region/profile (Bedrock), etc.
  "provider": {
    "openrouter": {
      "options": {
        // {env:VAR} pulls from the runtime environment.
        "apiKey": "{env:OPENROUTER_API_KEY}",
        "headers": {
          "HTTP-Referer": "https://opencode.example.com",
          "X-Title": "opencode-self-host"
        }
      }
    },
    "anthropic": {
      "options": { "apiKey": "{env:ANTHROPIC_API_KEY}" }
    }
  },

  // Allow/blocklists for providers. blocked wins over allowed.
  "enabled_providers":  ["openrouter", "anthropic"],
  "disabled_providers": [],

  // Default permissions applied to all agents that don't override them.
  // Values: "allow" | "ask" | "deny", or a glob map for bash.
  "permission": {
    "edit":  "ask",
    "write": "ask",
    "bash": {
      "*":              "ask",
      "git status *":   "allow",
      "git diff *":     "allow",
      "ls *":           "allow",
      "rm -rf *":       "deny"
    },
    "webfetch":   "allow",
    "websearch":  "allow"
  },

  // Files loaded as system instructions for every session. Globs supported.
  "instructions": [
    "AGENTS.md",
    ".opencode/rules/*.md"
  ],

  // MCP servers — see "MCP servers" section.
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "enabled": true
    }
  },

  // LSP servers — see "LSP servers" section.
  "lsp": {
    "typescript": {
      "command": ["typescript-language-server", "--stdio"],
      "extensions": [".ts", ".tsx", ".js", ".jsx"]
    }
  },

  // Code formatters — opencode will run these after edits when configured.
  "formatter": {
    "prettier": {
      "command": ["npx", "prettier", "--write", "$FILE"],
      "extensions": [".ts", ".tsx", ".js", ".jsx", ".json", ".md"]
    }
  },

  // Plugins — npm package names, or paths to local files.
  "plugin": [
    "opencode-helicone-session"
  ],

  // Web/server settings.
  "server": {
    "port":      4096,
    "hostname":  "0.0.0.0",
    "mdns":      false,
    "cors":      false
  },

  // Which shell to spawn for bash tools. Match the container shell.
  "shell": "/bin/bash",

  // UI.
  "theme":     "tokyonight",
  "keybinds":  { "switch_agent": "tab" },

  // Image attachment handling.
  "attachment": {
    "image": {
      "auto_resize":      true,
      "max_width":        2048,
      "max_height":       2048,
      "max_base64_bytes": 4194304
    }
  },

  // Sessions are never shared by default. "auto" auto-shares, "manual"
  // requires /share, "disabled" disables sharing entirely.
  "share":    "disabled",
  "autoshare": false,

  // Skip auto-update prompts ("notify" shows a banner without updating).
  "autoupdate": false,

  // File-watcher ignore patterns for the agent's file awareness.
  "watcher": {
    "ignore": ["node_modules/**", "dist/**", ".git/**"]
  },

  // Context-window management.
  "compaction": {
    "auto":     true,
    "reserved": 4096
  }
}
```

### Variable substitution

Two substitutions are honoured in string values:

- `{env:VAR}` — environment variable lookup (errors if unset)
- `{file:path}` — contents of `path`, relative to the config file

Use them to keep secrets out of the config and to share large prompts
across files.

---

## Providers and models

opencode talks to any provider supported by the underlying SDK. The most
common pattern for a self-host is **one aggregator** (OpenRouter) and
optional **direct** providers when you want a privileged path or a model
not on OpenRouter.

### OpenRouter — the easy default

```json
{
  "provider": {
    "openrouter": {
      "options": {
        "apiKey": "{env:OPENROUTER_API_KEY}"
      }
    }
  },
  "model": "openrouter/moonshotai/kimi-k2.6"
}
```

OpenRouter route a single key to ~300 models including Claude, GPT, Gemini,
open-source models (Kimi, GLM, DeepSeek, Qwen, Llama). Append `:online` to
any model id to add Brave web search.

### Direct Anthropic / OpenAI / Google

```json
{
  "provider": {
    "anthropic": { "options": { "apiKey": "{env:ANTHROPIC_API_KEY}" } },
    "openai":    { "options": { "apiKey": "{env:OPENAI_API_KEY}"    } },
    "google":    { "options": { "apiKey": "{env:GOOGLE_API_KEY}"    } }
  }
}
```

Reference these models without the `openrouter/` prefix, e.g.
`anthropic/claude-sonnet-4.6`.

### Local Ollama

```json
{
  "provider": {
    "ollama": {
      "options": { "baseURL": "http://ollama:11434/v1" }
    }
  },
  "model": "ollama/llama3.1:70b"
}
```

The same agent and command files work unchanged — only the `model`
identifier changes. Useful when migrating between cloud and local.

### Choosing a model

Rough guidance for a chat-replacement use case (mid-2026):

| Use case                                 | Reasonable pick                            |
| ---------------------------------------- | ------------------------------------------ |
| General chat, multimodal default          | `openrouter/moonshotai/kimi-k2.6`          |
| Pure reasoning (math, logic)              | `openrouter/z-ai/glm-5.1` (thinking mode)  |
| Massive context (>200K tokens)            | `openrouter/meta-llama/llama-4-scout` (10M) |
| Vision-heavy (screenshots, diagrams)      | `openrouter/moonshotai/kimi-k2.6` (native) |
| Cheapest housekeeping `small_model`       | `openrouter/meta-llama/llama-3.1-8b-instruct` |
| Web-grounded factual answers              | any model + `:online` suffix               |

Pricing differences *between* open models are noise (~$0.30–$1/M tokens).
Pricing differences *between* open and frontier closed models (Claude Opus,
GPT-5) are 10–50x. Optimise on capability, not on saving cents between
DeepSeek and GLM.

---

## Agents

Agents are **personas with their own model, tool set, permissions, and
system prompt**. Two flavours:

- **Primary agents** — you talk to them directly. Cycle with `Tab` in TUI.
  Built-ins: `Build` (full access), `Plan` (restricted, read-only by default).
- **Subagents** — invoked by a primary agent (automatic delegation) or by
  the user via `@agent-name`. Built-ins: `General`, `Explore`, `Scout`.

### File location

| Scope    | Path                                    |
| -------- | --------------------------------------- |
| Global   | `~/.config/opencode/agents/<name>.md`   |
| Project  | `.opencode/agents/<name>.md`            |

The filename becomes the agent identifier. `security-auditor.md` →
`@security-auditor`.

### Frontmatter reference

| Field         | Type     | Purpose                                                              |
| ------------- | -------- | -------------------------------------------------------------------- |
| `description` | string   | Required. Shown in agent picker and used for routing.                |
| `mode`        | enum     | `primary` \| `subagent` \| `all` (default).                          |
| `model`       | string   | Override the default model for this agent.                           |
| `temperature` | number   | 0.0–1.0. Lower = more deterministic.                                 |
| `top_p`       | number   | Alternative to temperature. Don't set both.                          |
| `permission`  | object   | Tool gating (see Permissions section).                               |
| `steps`       | integer  | Max agentic iterations before forced text response.                  |
| `disable`     | boolean  | Disable without deleting the file.                                   |
| `hidden`      | boolean  | Hide from `@` autocomplete (subagents only).                         |
| `color`       | string   | Hex or theme colour for UI display.                                  |

The **body of the markdown file** becomes the system prompt.

### Example: chat-only persona (no shell)

```yaml
---
description: General conversation and writing. Read-only — no shell or file edits.
mode: primary
model: openrouter/moonshotai/kimi-k2.6
permission:
  bash:  "deny"
  edit:  "deny"
  write: "deny"
  read:  "allow"
  webfetch: "allow"
---
Be direct. Skip preamble. Answer the question that was asked, not adjacent
ones. No "as a language model" or "I'm just an AI" caveats.
```

### Example: tool-heavy primary agent

```yaml
---
description: Multi-step tasks with full tool access (shell, file I/O, MCP servers).
mode: primary
model: openrouter/moonshotai/kimi-k2.6
permission:
  edit:  "ask"
  write: "ask"
  bash:
    "*":                   "ask"
    "git status *":        "allow"
    "git diff *":          "allow"
    "ls *":                "allow"
    "rg *":                "allow"
    "fd *":                "allow"
    "rm -rf *":            "deny"
    "sudo *":              "deny"
---
You have full tool access. Plan briefly, then execute. Confirm before
destructive actions (deletes, force operations, sending messages, writes
outside the working directory). Show the plan first when a task takes more
than two steps.
```

### Example: security auditor subagent

```yaml
---
description: Reviews code for security issues. Read-only; never edits files.
mode: subagent
model: openrouter/z-ai/glm-5.1
permission:
  edit:  "deny"
  write: "deny"
  bash:  "deny"
  read:  "allow"
  grep:  "allow"
  glob:  "allow"
---
You are a security auditor. Given a code path or file, identify potential
vulnerabilities (injection, authn/authz gaps, secret leakage, unsafe
deserialisation, race conditions, side-channel risks).

For each finding, report:
1. Severity (critical/high/medium/low)
2. File:line reference
3. The vulnerable pattern in 1–2 lines
4. Concrete remediation

Do not edit files. Never run shell commands. Only read.
```

Invoke as `@security-auditor look at src/auth/`.

### Example: PR reviewer (corporate)

```yaml
---
description: First-pass PR review against team standards. Read-only.
mode: subagent
model: corp/claude-sonnet
permission:
  edit:  "deny"
  write: "deny"
  bash:
    "*":              "deny"
    "git diff*":      "allow"
    "git log*":       "allow"
    "git show*":      "allow"
  "github_*":         "ask"
---
You are reviewing a pull request. Produce:

1. **Summary** — what this PR does in 2 sentences, derived from the diff
   (not the description — descriptions lie).
2. **Risk** — anything that touches auth, billing, migrations, or PII.
3. **Standards** — violations of @AGENTS.md (be specific: file:line).
4. **Suggest** — up to 3 concrete improvements. Skip nits.

If the PR is < 20 lines and trivial (typo, comment, dep bump), just say
"LGTM" with one sentence why. Don't pad.
```

Invoke as `@pr-reviewer PR #1234` once the GitHub MCP is wired up.

### Example: vision-specialised subagent

```yaml
---
description: Analyses images, screenshots, diagrams, and charts.
mode: subagent
model: openrouter/moonshotai/kimi-k2.6
hidden: false
---
When given an image, describe what is actually present in the image before
offering any interpretation. Distinguish between:
1. Observation — what you see literally
2. Inference — what you conclude from those observations
3. Speculation — anything beyond direct evidence

If the image contains text, transcribe it verbatim before paraphrasing.
```

### Switching agents

- **Primary agents:** `Tab` cycles between them (configurable via
  `keybinds.switch_agent`).
- **Subagents from chat:** `@<agent-name> <message>` invokes the subagent
  with the message and returns its output to the primary thread.
- **Subagents automatically:** primary agents will delegate to subagents
  when the task matches the subagent's description (the description is
  effectively the routing signal — write it well).

---

## Slash commands

Reusable, parameterised prompts triggered with `/<name>` in the TUI. The
fastest way to capture a recurring workflow ("summarise this", "research
that", "triage my inbox") without re-typing the prompt.

### File location

| Scope    | Path                                       |
| -------- | ------------------------------------------ |
| Global   | `~/.config/opencode/commands/<name>.md`    |
| Project  | `.opencode/commands/<name>.md`             |

`tldr.md` → invoke as `/tldr <arguments>`.

### Frontmatter reference

| Field         | Type     | Purpose                                                       |
| ------------- | -------- | ------------------------------------------------------------- |
| `description` | string   | Shown in TUI command list.                                    |
| `agent`       | string   | Run with a specific agent's permissions/system prompt.        |
| `model`       | string   | Override the default model for this command only.             |
| `subtask`     | boolean  | If true, runs in a subagent context (isolates from main thread). |

The markdown **body** is the prompt sent to the model, with substitutions.

### Substitutions

| Token        | Replaced with                                  |
| ------------ | ---------------------------------------------- |
| `$ARGUMENTS` | All arguments after `/<name>` as one string.   |
| `$1`, `$2`…  | Individual positional arguments.               |
| `` !`cmd` `` | Live shell output from `cmd` at invocation time. |
| `@<path>`    | File contents inlined at invocation time.      |

### Example: summarise-anything

`commands/tldr.md`:

```yaml
---
description: Summarise a file, URL, or pasted text in 5 bullets.
model: openrouter/moonshotai/kimi-k2.6
---
Summarise the following in at most 5 bullets, then a single "so what"
sentence. No preamble.

$ARGUMENTS
```

Invoke: `/tldr <paste the article>` or `/tldr @path/to/doc.md`.

### Example: research with web grounding

`commands/research.md`:

```yaml
---
description: Research a topic with live web search and citations.
model: openrouter/moonshotai/kimi-k2.6:online
---
Research the following topic. Use the `:online` web grounding rather than
training data.

Topic: $ARGUMENTS

Structure:
- TL;DR — 2 sentences.
- Key facts — bullet list, each with an inline `[source-domain]` citation.
- Contested — anything where reputable sources disagree.
- Further reading — 3 URLs.
```

### Example: explain-this-code

`commands/explain.md`:

```yaml
---
description: Explain code at a chosen level (beginner/intermediate/expert).
model: openrouter/moonshotai/kimi-k2.6
---
Explain the following code at $1 level. Cover:
- What it does (one sentence)
- How it works (paragraph)
- Anything subtle or non-obvious

Code:
@$2
```

Invoke: `/explain beginner src/auth/jwt.ts`.

### Example: shell output injection

`commands/standup.md`:

```yaml
---
description: Generate a standup summary from this week's commits.
model: openrouter/moonshotai/kimi-k2.6
---
Generate a 3-bullet standup summary from the following git log:

!`git log --since="7 days ago" --author="$(git config user.email)" --oneline`

Focus on themes and shippable outcomes, not commit count.
```

### Example: subtask isolation

`commands/grade.md`:

```yaml
---
description: Grade a code review without polluting the main thread.
subtask: true
model: openrouter/z-ai/glm-5.1
---
Read $1 and grade it (A–F) against the project's coding standards in
@AGENTS.md. Return the grade, 3 specific strengths, and 3 specific issues.
Nothing else.
```

`subtask: true` runs in a fresh subagent context, so the response
doesn't pollute the main conversation's context window.

### Example: draft a PR description from the current branch

`commands/pr.md`:

```yaml
---
description: Draft a PR title and description from the current branch's diff vs main.
model: corp/claude-sonnet
---
Write a PR title (≤70 chars) and description for the changes below.

Branch summary:
!`git log --oneline origin/main..HEAD`

Diff:
!`git diff origin/main...HEAD`

Linked tickets (from branch name, if any): $ARGUMENTS

Structure the description as:
## Summary
- 2–4 bullets describing what changed and why.
## Test plan
- Concrete checklist of what to verify.
## Risk
- One line. "Low" / "Medium — touches X" / "High — see ...".
```

Invoke: `/pr PROJ-1234` and paste the output into GitHub.

### Example: triage a Jira ticket

`commands/ticket.md`:

```yaml
---
description: Summarise a Jira/Linear ticket and propose next actions.
model: corp/claude-sonnet
---
Pull ticket $1 via the atlassian MCP. Then return:

- **What** — 1 sentence describing the request.
- **Acceptance** — bulleted list of completion criteria, inferred if absent.
- **Blockers** — anything that prevents work starting today.
- **Suggested approach** — 2–4 bullets, technical not prose.
- **Estimate** — S/M/L with one-line justification.
```

Invoke: `/ticket PROJ-4521`.

### Example: on-call incident triage

`commands/oncall.md`:

```yaml
---
description: Triage an alert — pull context from Grafana, recent deploys, error logs.
model: corp/claude-sonnet
subtask: true
---
Alert: $ARGUMENTS

Step 1: Find the most recent deploy to the affected service:
!`gh api repos/$ORG/$REPO/deployments --jq '.[0]'`

Step 2: Search the last 100 commits on main for related changes:
!`git log -100 --oneline --grep="$1"`

Step 3: Recommend immediate action. Choose ONE:
- **Rollback** — if a recent deploy correlates and is the likely cause
- **Investigate** — if no clear correlation; list 3 specific things to check
- **Escalate** — if outside expertise; name the right owner team
```

### Overriding built-ins

Custom commands take precedence over built-ins. You can override
`/init`, `/undo`, `/redo`, `/share`, `/help` if you want — but rarely
worth it.

---

## MCP servers

[Model Context Protocol](https://modelcontextprotocol.io) lets you expose
arbitrary external tools to the agent. This is how you give opencode
real-world hooks: Gmail, Calendar, Drive, a database, your home automation,
custom internal APIs.

### Config schema

In `opencode.json` under the `mcp` key:

```jsonc
{
  "mcp": {
    "<server-name>": {
      "type": "local" | "remote",
      // local-only:
      "command": ["bin", "arg1", "arg2"],
      "environment": { "VAR": "value" },
      // remote-only:
      "url": "https://my-mcp.example.com",
      "headers": { "Authorization": "Bearer {env:MY_TOKEN}" },
      // both:
      "enabled": true
    }
  }
}
```

### Tool namespacing

Tools registered by an MCP server are prefixed with the server name in
opencode. So a `read_email` tool on a server named `gmail` becomes
`gmail_read_email`. You can allow/deny by glob:

```json
"permission": {
  "gmail_*":     "ask",
  "calendar_*":  "allow",
  "homeassist_*": "ask"
}
```

### Example: filesystem MCP

Lets the agent read/write outside the workspace bind-mount (sparingly!):

```json
{
  "mcp": {
    "fs": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace", "/data"],
      "enabled": true
    }
  }
}
```

### Example: Brave Search MCP

```json
{
  "mcp": {
    "brave": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-brave-search"],
      "environment": { "BRAVE_API_KEY": "{env:BRAVE_API_KEY}" },
      "enabled": true
    }
  }
}
```

### Example: remote MCP with bearer auth

```json
{
  "mcp": {
    "linear": {
      "type": "remote",
      "url": "https://mcp.linear.app/sse",
      "headers": {
        "Authorization": "Bearer {env:LINEAR_TOKEN}"
      },
      "enabled": true
    }
  }
}
```

### Example: SQLite over MCP for personal data

Point opencode at a personal `.sqlite` you maintain (finances, journal,
habit tracking):

```json
{
  "mcp": {
    "personal": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-sqlite", "/workspace/personal.db"],
      "enabled": true
    }
  }
}
```

### Example: Home Assistant MCP

```json
{
  "mcp": {
    "homeassist": {
      "type": "remote",
      "url": "http://homeassistant.local:8123/mcp",
      "headers": { "Authorization": "Bearer {env:HASS_TOKEN}" },
      "enabled": true
    }
  }
}
```

Now the agent can answer "what's the temperature in the living room?" or
"turn off the office lights".

### Example: Atlassian (Jira + Confluence) for corporate work

```json
{
  "mcp": {
    "atlassian": {
      "type": "remote",
      "url": "https://mcp.atlassian.com/v1/sse",
      "headers": { "Authorization": "Bearer {env:ATLASSIAN_TOKEN}" },
      "enabled": true
    }
  }
}
```

Unlocks "summarise all open tickets assigned to me", "find every Confluence
page about the payments service", "draft a status update from this sprint's
done column".

### Example: GitHub / GitHub Enterprise MCP

```json
{
  "mcp": {
    "github": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
      "environment": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "{env:GITHUB_TOKEN}",
        "GITHUB_API_URL": "https://github.your-corp.com/api/v3"
      },
      "enabled": true
    }
  }
}
```

The same server works for `github.com` (drop `GITHUB_API_URL`) or GHE.
Lets the agent read PRs, review diffs, post comments, triage issues.

### Example: internal LLM gateway (LiteLLM / corporate proxy)

Many corps force model traffic through a central gateway that handles
auth, audit, and budget. Wire it as a custom OpenAI-compatible provider:

```json
{
  "provider": {
    "corp": {
      "npm":     "@ai-sdk/openai-compatible",
      "name":    "Corporate LLM Gateway",
      "options": {
        "baseURL": "https://llm-gateway.corp.example.com/v1",
        "apiKey":  "{env:CORP_GATEWAY_TOKEN}",
        "headers": {
          "X-Cost-Center": "{env:COST_CENTER}",
          "X-User":        "{env:USER}"
        }
      },
      "models": {
        "claude-sonnet": { "name": "Claude Sonnet (gateway)" },
        "gpt-4.1":       { "name": "GPT 4.1 (gateway)" }
      }
    }
  },
  "model": "corp/claude-sonnet"
}
```

Cost-centre and user headers travel on every call — finance can chargeback
correctly and security has an audit trail.

### Per-agent MCP enablement

In an agent file you can disable entire MCP namespaces:

```yaml
---
description: Chat-only — no tool access at all
permission:
  "gmail_*":      "deny"
  "calendar_*":   "deny"
  "homeassist_*": "deny"
---
```

### Authentication patterns

| Auth style                 | How to wire                                                    |
| -------------------------- | -------------------------------------------------------------- |
| Static API key             | `environment.KEY` (local) or `headers.Authorization` (remote)  |
| OAuth (user-driven)        | Use an MCP server that handles the OAuth dance once and caches |
| mTLS / client cert         | Front the MCP with a proxy that adds the cert (e.g. SWAG)      |
| IP allowlist               | Remote MCP, restrict by source IP at the MCP host              |

---

## LSP servers

opencode can attach to [Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
servers to give the agent real diagnostics, hovers, and symbol info —
the same information your IDE uses. This dramatically improves how well
an agent navigates an unfamiliar codebase.

### Why bother?

Without LSP, the agent works from raw text and grep. With LSP, it knows:

- Type errors and warnings (no more "looks right but doesn't compile")
- Where symbols are defined
- What types/signatures look like
- Available methods on an object

For chat-replacement use, LSP matters less. For any coding work in opencode,
turn it on for your main languages.

### Config

```jsonc
{
  "lsp": {
    "typescript": {
      "command":    ["typescript-language-server", "--stdio"],
      "extensions": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]
    },
    "python": {
      "command":    ["pyright-langserver", "--stdio"],
      "extensions": [".py"]
    },
    "rust": {
      "command":    ["rust-analyzer"],
      "extensions": [".rs"]
    },
    "go": {
      "command":    ["gopls"],
      "extensions": [".go"]
    }
  }
}
```

Each LSP requires its server binary on the container's `PATH`. For a
self-host Docker image you'd add the binary in the Dockerfile or mount it
in.

### Tips

- **Start narrow.** Only configure LSPs for languages you actually use in
  opencode sessions. Each adds startup latency and memory.
- **Use the agent's permission system** to deny `lsp` on chat-only agents
  so it doesn't try to attach for non-code conversations.
- **Workspace folders** — point opencode at the repo root, not subdirs.
  Many LSPs (TypeScript, gopls) walk up to find project boundaries.

### Common use cases

The scenarios where wiring up an LSP actually changes the outcome:

| Scenario                                | What LSP unlocks                                                |
| --------------------------------------- | --------------------------------------------------------------- |
| Refactoring across a TS/JS monorepo     | Accurate find-references and rename; agent stops missing call sites |
| Onboarding into an unfamiliar Rust/Go repo | Hover types, go-to-definition; agent navigates by symbol, not grep |
| "Why won't this compile?" debugging     | Live diagnostics — agent sees the same errors `tsc`/`pyright` does |
| Pre-commit verification                 | Agent confirms its own edits typecheck before declaring done    |
| Adding a method to a class              | Knows existing signatures and avoids name collisions            |

If your opencode is purely a chat replacement, skip this section entirely
and `"lsp": "deny"` in your chat agents.

---

## Plugins

JavaScript/TypeScript code that hooks into opencode's event loop. Use for:

- Auto-saving outputs to specific paths
- Injecting environment variables into shell calls
- Custom tools (defined with Zod schemas) without writing an MCP server
- Notifications (Telegram, Pushover, ntfy) on session events
- Routing model calls through a proxy (Helicone, LangSmith)

### Loading

Two ways:

1. **From npm** — declare in `opencode.json`:

   ```json
   { "plugin": ["opencode-helicone-session", "@my-org/internal-plugin"] }
   ```

   opencode auto-installs via Bun and caches in
   `~/.cache/opencode/node_modules/`.

2. **From a local file** — drop into `.opencode/plugins/` (project) or
   `~/.config/opencode/plugins/` (global). Loaded automatically.

Load order: global config → project config → global plugin dir →
project plugin dir.

### Plugin shape

```typescript
import type { Plugin } from "@opencode-ai/plugin"

export const MyPlugin: Plugin = async ({ project, client, directory, worktree, $ }) => {
  return {
    // Hook into events here.
    "session.idle": async (input) => {
      console.log(`Session ${input.sessionID} went idle`)
    },
    "tool.execute.before": async (input, output) => {
      if (input.tool === "bash" && /rm -rf \//.test(input.args.command)) {
        output.deny = true
        output.reason = "Blocked by safety plugin"
      }
    }
  }
}
```

The context object includes:
- `project` — current project metadata
- `client` — opencode HTTP client (call back into the server)
- `directory` — current working directory
- `worktree` — git worktree info if applicable
- `$` — Bun's shell helper for running commands

### Event catalogue (non-exhaustive)

| Category    | Events                                                                                |
| ----------- | ------------------------------------------------------------------------------------- |
| Session     | `session.created`, `session.updated`, `session.compacted`, `session.idle`             |
| Tool        | `tool.execute.before`, `tool.execute.after`                                            |
| File        | `file.edited`, `file.watcher.updated`                                                  |
| Command     | `command.executed`                                                                     |
| Message     | message and permission lifecycle hooks                                                 |
| TUI         | `tui.prompt.append`, `tui.command.execute`, `tui.toast.show`                          |
| Shell       | `shell.env` (mutate env before shell runs)                                            |

### Example: inject env into every shell call

```typescript
export const InjectEnv = async () => ({
  "shell.env": async (input, output) => {
    output.env.PROJECT_ROOT = input.cwd
    output.env.OPENCODE_SESSION = input.sessionID
  }
})
```

### Example: ntfy notification on session idle

```typescript
export const NtfyOnIdle = async ({ $ }) => ({
  "session.idle": async (input) => {
    await $`curl -d "Session ${input.sessionID} idle (${input.title})" https://ntfy.sh/your-private-topic`
  }
})
```

Combined with headless runs, this lets your phone ping when a long-running
task finishes.

### Example: custom tool with Zod schema

```typescript
import { z } from "zod"
import { tool } from "@opencode-ai/plugin"

export const WeatherPlugin = async () => ({
  tools: {
    get_weather: tool({
      description: "Get current weather for a city",
      input: z.object({ city: z.string() }),
      async execute({ city }) {
        const r = await fetch(`https://wttr.in/${encodeURIComponent(city)}?format=j1`)
        return await r.json()
      }
    })
  }
})
```

Now the model can call `get_weather({ city: "Sydney" })` like any other tool.

### Example: auto-archive every assistant reply to a daily journal

```typescript
import { appendFile, mkdir } from "node:fs/promises"
import { join } from "node:path"

export const JournalPlugin = async () => ({
  "session.updated": async (input) => {
    const last = input.messages?.at(-1)
    if (last?.role !== "assistant") return
    const day = new Date().toISOString().slice(0, 10)
    const dir = "/config/journal"
    await mkdir(dir, { recursive: true })
    await appendFile(
      join(dir, `${day}.md`),
      `\n\n## ${new Date().toISOString()} — ${input.title}\n\n${last.content}\n`
    )
  }
})
```

Drop into `~/.config/opencode/plugins/journal.ts` and every reply lands
in a dated markdown file — searchable, greppable, backupable.

### Example: route through Helicone for observability

```typescript
export const HeliconePlugin = async () => ({
  "shell.env": async (_input, output) => {
    output.env.OPENROUTER_BASE_URL = "https://oai.helicone.ai/v1"
    output.env.HELICONE_AUTH = `Bearer ${process.env.HELICONE_API_KEY}`
  }
})
```

Rewriting the provider base URL via env injection pipes all model calls
through Helicone's proxy so you get token, latency, and cost dashboards
per session — useful when you're tuning prompts or hunting waste.

### Example: audit log every tool call to syslog (corporate)

```typescript
import { appendFile } from "node:fs/promises"

const AUDIT = process.env.OPENCODE_AUDIT_LOG || "/var/log/opencode/audit.jsonl"

export const AuditPlugin = async () => ({
  "tool.execute.before": async (input) => {
    await appendFile(AUDIT, JSON.stringify({
      ts:        new Date().toISOString(),
      user:      process.env.USER,
      session:   input.sessionID,
      tool:      input.tool,
      args:      input.args,
      phase:     "before"
    }) + "\n")
  },
  "tool.execute.after": async (input, output) => {
    await appendFile(AUDIT, JSON.stringify({
      ts:        new Date().toISOString(),
      user:      process.env.USER,
      session:   input.sessionID,
      tool:      input.tool,
      ok:        !output.error,
      error:     output.error?.message,
      phase:     "after"
    }) + "\n")
  }
})
```

Ship the JSONL to your SIEM (Splunk, Datadog, ELK) via a sidecar.
Satisfies "who ran what tool, when" for SOC 2 / ISO 27001 evidence.

### Common use cases

| Goal                              | Hook(s)                              | Pattern                                          |
| --------------------------------- | ------------------------------------ | ------------------------------------------------ |
| Notify when long task finishes    | `session.idle`                       | `curl` to ntfy / Telegram / Pushover             |
| Block specific dangerous commands | `tool.execute.before`                | Pattern-match args, set `output.deny = true`     |
| Inject secrets into shell calls   | `shell.env`                          | Mutate `output.env` without exposing in config   |
| Audit log of every tool call      | `tool.execute.after`                 | Append to a JSONL file with timestamp + args     |
| Archive assistant output          | `session.updated`                    | Append latest assistant message to disk          |
| Add custom domain tools           | (tools export)                       | Zod schema + `execute` — no MCP server needed    |
| Observability proxy               | `shell.env`                          | Override provider base URL with proxy endpoint   |
| Auto-tag sessions                 | `session.created`                    | Call `client` to set title from cwd / git branch |

---

## Permissions

The single most underused feature. Permissions gate every tool call,
preventing the agent from doing things you didn't authorise.

### Values

| Value     | Meaning                                                       |
| --------- | ------------------------------------------------------------- |
| `"allow"` | Tool runs without prompt                                      |
| `"ask"`   | User is prompted to approve before each call                  |
| `"deny"`  | Tool is unavailable to this agent (returns an error)          |

### Keys

The keys you can set permissions on:

`read`, `edit`, `write`, `glob`, `grep`, `list`, `bash`, `task`,
`external_directory`, `todowrite`, `webfetch`, `websearch`, `lsp`, `skill`,
`question`, `doom_loop`, plus MCP tool names (with prefix glob support).

### Bash with glob patterns

The most useful pattern — `ask` everything by default, allow safe reads,
deny known-destructive operations:

```json
"bash": {
  "*":              "ask",
  "git status*":    "allow",
  "git diff*":      "allow",
  "git log*":       "allow",
  "ls *":           "allow",
  "cat *":          "allow",
  "rg *":           "allow",
  "fd *":           "allow",
  "rm -rf*":        "deny",
  "sudo*":          "deny",
  "kill *":         "deny",
  "docker rm*":     "deny",
  "docker stop*":   "deny"
}
```

Match order: more specific patterns win over `*`.

### Per-agent overrides

The most powerful pattern is **strict global defaults + permissive
agent-specific overrides**. Global config denies everything dangerous;
the `agent.md` for your trusted automation agent loosens it for known-safe
flows.

Global `opencode.json`:
```json
"permission": {
  "bash":  { "*": "ask", "rm -rf*": "deny" },
  "edit":  "ask",
  "write": "ask"
}
```

`agents/cron-runner.md`:
```yaml
---
description: Trusted scheduled task runner. Used by cron only.
permission:
  bash:
    "*":          "allow"
    "rm -rf*":    "deny"
    "sudo*":      "deny"
  edit:  "allow"
  write: "allow"
---
```

---

## Instructions (rules) files

Plain markdown files included as system instructions for every session.
Use for project conventions, coding standards, persistent context.

`opencode.json`:
```json
"instructions": ["AGENTS.md", ".opencode/rules/*.md"]
```

`AGENTS.md` is conventional (parallel to Anthropic's `CLAUDE.md` or
Cursor's `.cursorrules`):

```markdown
# Project rules

- Use TypeScript strict mode.
- Tests live next to the file under test, named `<name>.test.ts`.
- Never commit `.env` or `node_modules`.
- Prefer composition over inheritance.
```

The model sees these on every session. Keep them tight — every byte
costs context.

### Common use cases

For a chat-replacement self-host, instructions are mostly about *you*,
not a codebase. Split into multiple files under `.opencode/rules/` and
glob them in — easier to edit and disable individually.

**Personal context (`rules/about-me.md`)** — who you are so the model
stops asking:

```markdown
- Based in Sydney, Australia (AEST/AEDT). All times in 24h.
- Work in platform engineering; comfortable with Linux, Docker, networks.
- Prefer concrete examples over abstract explanations.
```

**Response style (`rules/style.md`)** — how you want it to talk:

```markdown
- Skip preamble. No "great question", no "I'd be happy to".
- Answer directly first, then expand only if asked.
- Use markdown tables for comparisons of 3+ items.
- Cite sources with inline `[domain]` markers when using web search.
- Avoid hedging ("might", "perhaps", "it depends") unless genuinely uncertain.
```

**Privacy guardrails (`rules/privacy.md`)** — what not to leak:

```markdown
- Do not send personal email, calendar, or filesystem contents to web search.
- Treat anything from the `personal_*` MCP namespace as confidential.
- Never include API keys, tokens, or `.env` contents in responses verbatim.
```

**Output conventions (`rules/output.md`)** — for headless / cron use:

```markdown
- When invoked headlessly (no TTY), output plain text only — no ANSI codes.
- Briefings should fit a phone notification (≤500 chars) unless asked to expand.
- Dates always ISO-8601 (`2026-05-24`), never US-format.
```

**Corporate context (`rules/corp.md`)** — for team/company self-hosts:

```markdown
- Audience is internal engineering at $COMPANY. Assume familiarity with our stack:
  Go services, Kafka, Postgres, k8s on EKS, Terraform.
- Data classification: anything touched via `atlassian_*`, `github_*`,
  `gmail_*`, or paths under `/workspace/internal/` is **Confidential**.
  Never include verbatim Confidential content in `websearch` or `webfetch` args.
- When drafting external-facing content (customer email, support reply,
  marketing copy), call it out explicitly and use the brand voice in
  @docs/brand-voice.md.
- Code suggestions must follow @docs/engineering-standards.md.
  Tests required for any non-trivial behaviour change.
- For incident or production work, default to read-only investigation.
  Any write/exec against prod requires explicit human "yes do it" — never
  infer permission from earlier turns in the session.
```

Wire them all in:

```json
"instructions": [".opencode/rules/*.md"]
```

---

## Interfaces: TUI, web, CLI

opencode runs in three modes from the same binary.

### TUI (terminal)

```bash
opencode
```

Best for keyboard-driven workflows. Key bindings:

- `Tab` — cycle primary agents
- `/` — open command palette
- `@` — invoke a subagent
- `Esc` — cancel current generation
- `Ctrl+C` twice — quit

Customise with the `keybinds` config block.

### Web

```bash
opencode web --hostname 0.0.0.0 --port 4096
```

This is what the Docker image runs. Best for phone access, shared
sessions, browser convenience. Front it with SWAG/Caddy/Traefik for TLS
and auth.

### CLI (headless)

```bash
opencode run "Summarise the README" --output text
opencode run "/morning" --agent agent
echo "What did I commit this week?" | opencode run --stdin
```

Headless mode is what unlocks integration patterns (cron, fswatch,
shell pipelines, Telegram bots). Output formats: `text`, `json`, `stream`.

### Server (API)

```bash
opencode serve --port 4096
```

Exposes a REST/SSE API for other apps to call. Same surface the web UI
uses. Combine with plugins for full programmability.

---

## Sessions, sharing, compaction

### Sessions

Every conversation is a session. Persisted to
`~/.local/share/opencode/sessions/` (or
`/config/.local/share/opencode/sessions/` in the Docker image).

In TUI/web:
- `/new` — fresh session
- `/sessions` — pick from history
- `/undo` / `/redo` — step backward / forward in a session

### Sharing

Sessions can be published to opencode's hosted share service (a public URL,
read-only). Three modes:

- `"disabled"` — sharing disabled entirely. **Use this for self-host with
  sensitive data.**
- `"manual"` — `/share` to publish
- `"auto"` — every session auto-shared (rarely what you want)

### Compaction

When the conversation outgrows the model's context, opencode summarises
older messages. Configure via:

```json
"compaction": {
  "auto":     true,
  "reserved": 4096
}
```

`reserved` is the buffer kept free for the model's response.

---

## Patterns that pay off

The integrations that justify the whole self-host.

### Pattern 1 — Scheduled briefing to your phone

Cron + headless + a Telegram/ntfy webhook:

```cron
0 7 * * * docker exec opencode opencode run "/morning" --agent agent --output text \
    | curl -d @- https://ntfy.sh/your-private-topic
```

`commands/morning.md` consolidates calendar, email, weather, news via MCP.

### Pattern 2 — Watch-folder summariser

`fswatch` or `inotifywait` on a directory; new files trigger a summary:

```bash
fswatch -0 /path/to/inbox | while read -d "" event; do
  docker exec opencode opencode run "/tldr @$event" --output text \
      > "/path/to/summaries/$(basename "$event").md"
done
```

Drop PDFs into a folder, get summaries elsewhere.

### Pattern 3 — Email triage on a cron

```cron
0 18 * * * docker exec opencode opencode run "/triage" --agent agent \
    --output text > /path/to/notes/inbox-$(date +\%F).md
```

`commands/triage.md` uses a Gmail MCP to classify unread email
(reply / archive / delete / needs-action) without sending anything.

### Pattern 4 — Cross-corpus search

A single primary agent with Gmail, Calendar, Drive, and filesystem MCPs
attached lets you ask:

> Find every mention of "subsidy" across my email, calendar invites, and
> ~/notes/ from the last 12 months. Group by source.

Nothing in browser AI can touch three data sources at once like this.

### Pattern 5 — Long-context document chewing

For inputs over 200K tokens, switch to a long-context model:

`commands/megacontext.md`:
```yaml
---
description: Read a massive file/folder and answer questions about it.
model: openrouter/meta-llama/llama-4-scout
---
Read the following input fully before answering. It may be very long.

$ARGUMENTS
```

### Pattern 6 — Multi-stage workflows with subtask isolation

A primary agent runs `subtask: true` commands to delegate research
phases without polluting its own context:

`commands/decide.md`:
```yaml
---
description: Research a decision, then recommend without the research clutter.
subtask: true
model: openrouter/z-ai/glm-5.1
---
Decision: $ARGUMENTS

Step 1: Identify the 3 most important factors.
Step 2: Research each via :online search.
Step 3: Return *only* the final recommendation with 3 bullet justification.

Do NOT include the research process in your output.
```

### Pattern 7 — Voice in (Telegram bot frontend)

A small bot listens on Telegram, pipes messages to
`opencode run --stdin`, and posts replies back. Gives you phone access
to your whole stack with no opencode web UI exposed externally.

### Pattern 8 — Home automation by intent

With a Home Assistant MCP attached, ad-hoc phrases work:

> "I'm leaving for work" → agent calls homeassist_run_script("leaving_routine")
> "What's the temperature upstairs?" → agent calls homeassist_get_state(...)

### Pattern 9 — Auto-review every PR (corporate)

GitHub Actions runs opencode headlessly on every PR open / push:

```yaml
# .github/workflows/opencode-review.yml
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: |
          docker run --rm \
            -e GITHUB_TOKEN \
            -e CORP_GATEWAY_TOKEN \
            -v $PWD:/workspace \
            opencode:latest \
            run "@pr-reviewer PR #${{ github.event.number }}" \
              --output text \
            | gh pr comment ${{ github.event.number }} --body-file -
```

Catches obvious issues before a human looks. Tuned via `agents/pr-reviewer.md`
and `rules/engineering-standards.md` — no code changes, just markdown.

### Pattern 10 — Knowledge-base Q&A over Confluence + Drive

Primary agent with `atlassian_*` + `drive_*` MCPs, plus a chat-only persona:

> "What's our policy on third-party model training?" →
> agent searches Confluence + Drive, returns the answer with source links
> (`[Confluence: Security/Vendor-Review-2025]`).

Replaces "ask in #help-it" for the 80% of FAQs that already have a written
answer somewhere nobody can find.

### Pattern 11 — Weekly status report from sprint activity

Cron + headless, posts to Slack via webhook:

```cron
0 16 * * 5 docker exec opencode opencode run "/sprint-report" \
    --agent agent --output text \
    | curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\": \"$(cat -)\"}" \
        $SLACK_WEBHOOK_URL
```

`commands/sprint-report.md` pulls done tickets from Jira, merged PRs from
GitHub, and summarises into "shipped / in-flight / blocked" for your team.

### Pattern 12 — On-call assistant in Slack

Slack MCP receives DMs to a bot user, pipes to a `oncall` agent with
Grafana + GitHub + runbook MCPs attached:

> "p99 on payments spiked 5 min ago" →
> agent pulls dashboard, recent deploys, related runbook section, suggests
> rollback vs investigate, links the deploy PR.

Replaces "who knows about payments?" pings during an incident.

### Pattern 13 — DLP guardrail on external sends

A plugin watches `tool.execute.before` for `webfetch`, `websearch`, and
external MCP namespaces. If the args contain content from a Confidential
source (matched against a regex or classifier), it sets `output.deny = true`
and `output.reason = "DLP: Confidential content in external call"`.

Lets you safely give the agent both internal and external tools without
worrying about cross-contamination.

---

## Troubleshooting

### Model errors out with 401 / 403

Check the env var name in `opencode.json` matches what your environment
exports. `{env:OPENROUTER_API_KEY}` is literal — typos here silently pass
a missing key to the provider.

### Agent doesn't appear in `Tab` cycle

Primary agents only appear if `mode: primary` or `mode: all`. Check the
frontmatter. Also confirm the file is in `agents/` (plural) not `agent/`.

### Slash command not recognised

Same — must be in `commands/` (plural). The filename without `.md`
becomes the command name; underscores, dashes, lowercase letters and
digits work; spaces don't.

### MCP server "tool unavailable"

Run `opencode run "list MCP tools"` to see what's actually registered.
If your server isn't there:
- Check the `command` actually exists on PATH in the container
- Run the command manually to confirm it speaks MCP
- Check `enabled: true` (the default, but worth confirming)
- Look at `/config/.local/state/opencode/log` for stderr from the MCP

### Permission prompts on actions you marked `"allow"`

Glob match order matters. More-specific patterns override `"*"`. Test:

```json
"bash": {
  "*":        "ask",
  "git *":    "allow"
}
```

`git status` matches `"git *"` → allow. `npm install` matches only `"*"`
→ ask.

### Compaction kicks in too aggressively

Lower `compaction.reserved` (default 4096) to give more room before
trimming, or switch to a longer-context model. Llama 4 Scout's 10M
context effectively never compacts.

### Sessions vanish after container rebuild

Sessions live under `XDG_DATA_HOME`, which the Docker image sets to
`/config/.local/share/`. Make sure `/config` is bind-mounted (the
`docker-compose.yml` here mounts it as `./data/opencode/config`). If it
isn't, your sessions are in an ephemeral container layer.

---

## Further reading

- [opencode.ai/docs](https://opencode.ai/docs) — authoritative docs
- [github.com/anomalyco/opencode](https://github.com/anomalyco/opencode) — source
- [Model Context Protocol](https://modelcontextprotocol.io) — MCP spec and SDKs
- [Language Server Protocol](https://microsoft.github.io/language-server-protocol/) — LSP spec
- [OpenRouter docs](https://openrouter.ai/docs) — provider routing, `:online`, headers
- [linuxserver.io SWAG](https://docs.linuxserver.io/general/swag/) — reverse proxy front-end
