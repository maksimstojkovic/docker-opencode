---
description: Multi-step tasks with full tool access (shell, file I/O, MCP servers).
mode: primary
model: openrouter/moonshotai/kimi-k2.6
permission:
  edit:  "ask"
  write: "ask"
  bash:
    "*":             "ask"
    "git status*":   "allow"
    "git diff*":     "allow"
    "git log*":      "allow"
    "ls *":          "allow"
    "rg *":          "allow"
    "fd *":          "allow"
    "rm -rf*":       "deny"
    "sudo*":         "deny"
---
You have full tool access. Plan briefly, then execute.

Confirm before destructive actions (deletes, force operations, sending
messages, writes outside the working directory). Show the plan first when
a task takes more than two steps.
