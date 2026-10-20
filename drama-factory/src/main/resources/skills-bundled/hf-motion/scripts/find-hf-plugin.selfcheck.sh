#!/usr/bin/env bash
# Self-check for find-hf-plugin.sh. No network, no real plugin:
#
#   bash skills/hf-motion/scripts/find-hf-plugin.selfcheck.sh
set -u
T="$(cd -- "$(dirname -- "$0")" && pwd)/find-hf-plugin.sh"
FAIL=0
chk() { # chk <label> <got> <want>
    if [ "$2" = "$3" ]; then echo "ok    $1"; else echo "FAIL  $1: got '$2' want '$3'"; FAIL=1; fi
}
TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT
plugin() { # plugin <dir> -> fake plugin root holding the launcher
    mkdir -p "$1/skills/hyperframes/scripts" && : > "$1/skills/hyperframes/scripts/plugin-cli.mjs"
}
C=plugins/cache/hyperframes/hyperframes
plugin "$TMP/home/.claude-a/$C/0.8.9"
plugin "$TMP/home/.claude-b/$C/0.8.114"
mkdir -p "$TMP/home/.claude-b/$C/0.9.0"            # newer dir without a launcher: ignored
plugin "$TMP/cfg/$C/0.7.1"
plugin "$TMP/explicit"
run() { env -u HF_PLUGIN_ROOT -u CLAUDE_CONFIG_DIR HOME="$TMP/home" "$@" bash "$T" 2>/dev/null; }

chk "newest version across ~/.claude* (version sort, not lexical)" "$(run)" "$TMP/home/.claude-b/$C/0.8.114"
chk "CLAUDE_CONFIG_DIR wins over ~/.claude*" "$(run CLAUDE_CONFIG_DIR="$TMP/cfg")" "$TMP/cfg/$C/0.7.1"
chk "empty CLAUDE_CONFIG_DIR cache falls through" "$(run CLAUDE_CONFIG_DIR="$TMP/nope")" "$TMP/home/.claude-b/$C/0.8.114"
chk "HF_PLUGIN_ROOT wins" "$(run HF_PLUGIN_ROOT="$TMP/explicit")" "$TMP/explicit"
run HF_PLUGIN_ROOT="$TMP/home" >/dev/null; chk "wrong HF_PLUGIN_ROOT is an error, not a fall-through" "$?" 1
env -u HF_PLUGIN_ROOT -u CLAUDE_CONFIG_DIR HOME="$TMP/empty" bash "$T" >/dev/null 2>"$TMP/err"
chk "no plugin anywhere exits 1" "$?" 1
grep -q 'heygen-com/hyperframes' "$TMP/err"; chk "absent-plugin message names the marketplace" "$?" 0
exit "$FAIL"
