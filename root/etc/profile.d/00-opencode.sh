# shellcheck shell=sh
# System-wide interactive-shell setup for opencode containers.
# Sourced by /etc/profile (login shells) and /etc/bash.bashrc (bash non-login).
# Keep POSIX-compatible — dash and bash both source this.

# Skip non-interactive invocations (scp/rsync/etc. choke on prompt setup).
case $- in *i*) ;; *) return 0 ;; esac

# Sane default umask so files dropped into bind-mounts stay group-readable.
umask 022

# Coloured ls when supported; fall back silently otherwise.
if ls --color=auto / >/dev/null 2>&1; then
    alias ls='ls --color=auto'
fi

alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'

# Prompt: bash supports \[ \] non-printing markers (needed so readline tracks
# line length correctly across colours). Dash doesn't, so feed it a plain
# version — colour sequences in dash PS1 would break line wrap.
if [ -n "${BASH_VERSION:-}" ]; then
    PS1='\[\e[1;32m\]\u\[\e[0m\]@\[\e[1;34m\]opencode\[\e[0m\]:\[\e[1;36m\]\w\[\e[0m\]\$ '
else
    PS1='\u@opencode:\w\$ '
fi
export PS1

# opencode's web terminal exec's /bin/bash directly (bypassing the user's
# login shell from /etc/passwd), so /usr/local/bin/opencode-shell never
# runs for web-spawned terminals. This rc file IS sourced (via the
# /etc/bash.bashrc -> profile.d chain for interactive non-login bash),
# so it's the only reliable place to handle clear + cwd.
case "${TERM:-dumb}" in
    dumb|screen*|tmux*) ;;
    *)
        if [ -t 1 ] && [ -z "${TMUX:-}" ] && [ -z "${STY:-}" ]; then
            # RIS (full reset) — masks the ghost text opencode leaks into
            # freshly opened "+" tabs. Heavier than `clear` but needed:
            # the bug also leaves termios in a weird state (\n without \r),
            # and RIS resets that too.
            printf '\033c'
        fi
        ;;
esac

# Land in /workspace when no meaningful cwd was passed. Respect any path
# under /workspace (per-project terminals) so opening a project in opencode
# still drops the terminal in that project dir.
if [ -t 1 ] && [ -d /workspace ]; then
    case "${PWD:-/}" in
        /workspace|/workspace/*) ;;
        *) cd /workspace 2>/dev/null || true ;;
    esac
fi
