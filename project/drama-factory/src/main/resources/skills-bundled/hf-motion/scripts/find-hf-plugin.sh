#!/usr/bin/env bash
# Print the root directory of the official HyperFrames plugin
# (heygen-com/hyperframes marketplace), i.e. the directory that holds
# skills/hyperframes/scripts/plugin-cli.mjs. Exit 1 with a message when absent.
#
#   PLUGIN=$(bash find-hf-plugin.sh) || exit 1
#   node "$PLUGIN/skills/hyperframes/scripts/plugin-cli.mjs" lint .
#
# Resolution order (first proven hit wins):
#   1. $HF_PLUGIN_ROOT, when set. An explicit override that does not hold the
#      launcher is an error, never a silent fall-through.
#   2. $CLAUDE_CONFIG_DIR/plugins/cache/hyperframes/hyperframes/<ver>, newest.
#   3. $HOME/.claude*/plugins/cache/hyperframes/hyperframes/<ver>, newest.
set -u
LAUNCHER=skills/hyperframes/scripts/plugin-cli.mjs

if [ -n "${HF_PLUGIN_ROOT:-}" ]; then
    if [ -f "$HF_PLUGIN_ROOT/$LAUNCHER" ]; then
        printf '%s\n' "$HF_PLUGIN_ROOT"
        exit 0
    fi
    printf '[hf-motion] HF_PLUGIN_ROOT=%s holds no %s\n' "$HF_PLUGIN_ROOT" "$LAUNCHER" >&2
    exit 1
fi

newest() { # newest <cache-dir>... -> newest version dir holding the launcher
    for d in "$@"; do
        [ -f "$d/$LAUNCHER" ] && printf '%s\t%s\n' "${d##*/}" "$d"
    done | sort -V -k1,1 | tail -n 1 | cut -f2-
}

hit=""
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    hit=$(newest "$CLAUDE_CONFIG_DIR"/plugins/cache/hyperframes/hyperframes/*)
fi
[ -n "$hit" ] || hit=$(newest "$HOME"/.claude*/plugins/cache/hyperframes/hyperframes/*)

if [ -z "$hit" ]; then
    printf '%s\n' \
        '[hf-motion] official HyperFrames plugin not found.' \
        'Install it first:  /plugin marketplace add heygen-com/hyperframes  then  /plugin install hyperframes@hyperframes' \
        'or export HF_PLUGIN_ROOT=<dir holding skills/hyperframes/scripts/plugin-cli.mjs>.' >&2
    exit 1
fi
printf '%s\n' "$hit"
