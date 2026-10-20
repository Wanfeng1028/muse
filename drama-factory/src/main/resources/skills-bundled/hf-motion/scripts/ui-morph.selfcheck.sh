#!/usr/bin/env bash
# Self-check for scaffold.mjs + the ui-morph recipe. Offline: a fake hyperframes
# plugin supplies GSAP (the recipe uses no plugin SFX), and --no-music skips numpy.
#
#   bash skills/hf-motion/scripts/ui-morph.selfcheck.sh
#
# Scaffolds the default and an alternate config into temp dirs and asserts the
# alternate CONFIG, its static timing attributes and its literal UTF-8 text all
# took effect, then exercises the refusal paths.
set -u
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
S="$HERE/scaffold.mjs"
R=ui-morph
FAIL=0
chk() { # chk <label> <got> <want>
    if [ "$2" = "$3" ]; then echo "ok    $1"; else echo "FAIL  $1: got '$2' want '$3'"; FAIL=1; fi
}
TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"
mkdir -p "$P/skills/hyperframes/scripts" "$P/skills/demo/assets/vendor"
: > "$P/skills/hyperframes/scripts/plugin-cli.mjs"
echo '/* gsap fixture */' > "$P/skills/demo/assets/vendor/gsap.min.js"
echo '{"name":"hyperframes","version":"9.9.9"}' > "$P/plugin.json"
export HF_PLUGIN_ROOT="$P"

cfg() { # cfg <project> <js-expr over CONFIG c> -> value
    node -e 'const h=require("fs").readFileSync(process.argv[1],"utf8");
      const c=JSON.parse(h.slice(h.indexOf("/* CONFIG:BEGIN */")+18,h.indexOf("/* CONFIG:END */")));
      console.log(eval(process.argv[2]))' "$1/index.html" "$2"
}
attr() { # attr <project> <id> <attr> -> value of that attribute on the element with that id
    node -e 'const h=require("fs").readFileSync(process.argv[1],"utf8");
      const t=h.match(new RegExp("<[a-zA-Z]+\\b[^>]*\\bid=\""+process.argv[2]+"\"[^>]*>"))[0];
      console.log(t.match(new RegExp(process.argv[3]+"=\"([^\"]*)\""))[1])' "$1/index.html" "$2" "$3"
}
win() { echo "$(attr "$1" "$2" data-start)+$(attr "$1" "$2" data-duration)"; }

# 1. default: the original 14 s / 120 BPM loop, 1440x1440
node "$S" "$R" "$TMP/def" --no-music >/dev/null
chk "default exit" "$?" 0
chk "default buttonLabel" "$(cfg "$TMP/def" c.buttonLabel)" "Get started"
chk "default tabs" "$(cfg "$TMP/def" 'c.tabs.join("|")')" "Daily|Weekly|Monthly"
chk "default bpm" "$(cfg "$TMP/def" c.bpm)" "120"
chk "default canvas" "$(attr "$TMP/def" stage data-width)x$(attr "$TMP/def" stage data-height)" "1440x1440"
chk "default stage window (28 beats)" "$(win "$TMP/def" stage)" "0+14"
chk "default scene window" "$(win "$TMP/def" scene)" "0+14"
chk "default music window (static)" "$(win "$TMP/def" music)" "0+14"
chk "music src" "$(attr "$TMP/def" music src)" "assets/music.m4a"
chk "one audio element" "$(grep -c '<audio id=' "$TMP/def/index.html")" "1"
chk "gsap copied from plugin" "$(cat "$TMP/def/assets/vendor/gsap.min.js")" "/* gsap fixture */"
chk "Geist font + OFL bundled" "$([ -s "$TMP/def/assets/fonts/geist/Geist-Variable.woff2" ] && grep -q 'SIL Open Font License, Version 1.1' "$TMP/def/assets/fonts/geist/OFL.txt" && echo y)" "y"
chk "NanumSquare not copied" "$([ -e "$TMP/def/assets/fonts/NanumSquare_acEB.ttf" ] && echo y || echo n)" "n"
chk "music script copied" "$([ -f "$TMP/def/scripts/make_music.py" ] && echo y)" "y"
chk "--no-music wrote no bed" "$([ -e "$TMP/def/assets/music.wav" ] && echo y || echo n)" "n"
chk "recipe.mjs not copied" "$([ -e "$TMP/def/recipe.mjs" ] && echo y || echo n)" "n"
chk "no will-change in template" "$(grep -c 'will-change:' "$TMP/def/index.html")" "0"
chk "package.json pins plugin version" "$(node -p 'require(process.argv[1]).scripts.render' "$TMP/def/package.json")" "npx --yes hyperframes@9.9.9 render"
chk "musicArgs: bpm, duration, taps" "$(node --input-type=module -e "
    const r = await import('$HERE/../templates/$R/recipe.mjs');
    const a = r.musicArgs({ bpm: 120 }); console.log(a.slice(1, 7).join(' '));")" \
    "--bpm 120 --duration 14 --taps 0,3,6,8,9,11,13,15,17,18,21,22,23,26"

# 2. alternate: Latin-1 text, other lists, bpm 110, other palette
node "$S" "$R" "$TMP/alt" --no-music 'buttonLabel=Join the beta' 'trackTitle=Golden Hour Café' \
    'trackArtist=Lumière Trio' 'tabs=Hour|Day|Year' 'chartTitle=Weekly signups' 'chartData=40|32|55|48|70|64' \
    'paletteQuery=inv' 'paletteItems=Invite teammates|Billing|Invoices archive|Log out' 'toastText=Invite sent' \
    'paper=#f4f1ea' 'charcoal=#16213a' 'red=#d62828' 'bpm=110' >/dev/null
chk "alt exit" "$?" 0
chk "alt trackTitle" "$(cfg "$TMP/alt" c.trackTitle)" "Golden Hour Café"
chk "alt tabs" "$(cfg "$TMP/alt" 'c.tabs.join("|")')" "Hour|Day|Year"
chk "alt chartData items" "$(cfg "$TMP/alt" 'c.chartData.length')" "6"
chk "alt paletteItems" "$(cfg "$TMP/alt" 'c.paletteItems.length')" "4"
chk "alt bpm is a number" "$(cfg "$TMP/alt" 'typeof c.bpm + c.bpm')" "number110"
chk "alt palette" "$(cfg "$TMP/alt" '[c.paper,c.charcoal,c.red].join(" ")')" "#f4f1ea #16213a #d62828"
chk "alt stage = 28 beats at 110" "$(win "$TMP/alt" stage)" "0+15.272727"
chk "alt scene = stage" "$(win "$TMP/alt" scene)" "0+15.272727"
chk "alt music = stage" "$(win "$TMP/alt" music)" "0+15.272727"
chk "Latin-1 is literal UTF-8, no \\u escapes" "$(grep -c '\\u[0-9a-fA-F]\{4\}' "$TMP/alt/index.html")" \
    "$(grep -c '\\u[0-9a-fA-F]\{4\}' "$HERE/../templates/$R/index.html")"
grep -q '"trackArtist": "Lumière Trio"' "$TMP/alt/index.html"; chk "literal Lumière Trio in CONFIG" "$?" 0

# 3. --update re-applies on top of the project's own CONFIG
node "$S" "$R" "$TMP/alt" --update --no-music 'bpm=150' >/dev/null
chk "update exit" "$?" 0
chk "update kept earlier override" "$(cfg "$TMP/alt" c.toastText)" "Invite sent"
chk "update resynced stage" "$(win "$TMP/alt" stage)" "0+11.2"
chk "update resynced music" "$(win "$TMP/alt" music)" "0+11.2"

# 4. refusals
node "$S" "$R" "$TMP/def" --no-music >/dev/null 2>&1; chk "non-empty dir refused" "$?" 2
node "$S" "$R" "$TMP/x1" --no-music 'buttonLable=x' >/dev/null 2>&1; chk "unknown key refused" "$?" 2
node "$S" "$R" "$TMP/x2" --no-music 'bpm=89' >/dev/null 2>&1; chk "bpm 89 refused" "$?" 2
node "$S" "$R" "$TMP/x3" --no-music 'bpm=151' >/dev/null 2>&1; chk "bpm 151 refused" "$?" 2
node "$S" "$R" "$TMP/x4" --no-music 'bpm=fast' >/dev/null 2>&1; chk "non-numeric bpm refused" "$?" 2
node "$S" "$R" "$TMP/x5" --no-music 'red=red' >/dev/null 2>&1; chk "non-hex colour refused" "$?" 2
node "$S" "$R" "$TMP/x6" --no-music 'red=#f0d8d8' >/dev/null 2>&1; chk "low-contrast red refused" "$?" 2
node "$S" "$R" "$TMP/x7" --no-music 'charcoal=#d0d0d0' >/dev/null 2>&1; chk "low paper/charcoal contrast refused" "$?" 2
node "$S" "$R" "$TMP/x8" --no-music 'buttonLabel=시작하기' >/dev/null 2>&1; chk "Hangul (not in Geist) refused" "$?" 2
node "$S" "$R" "$TMP/x9" --no-music 'buttonLabel=Seventeen letters' >/dev/null 2>&1; chk "17-char button refused" "$?" 2
node "$S" "$R" "$TMP/xa" --no-music 'tabs=One|Two' >/dev/null 2>&1; chk "2 tabs refused" "$?" 2
node "$S" "$R" "$TMP/xb" --no-music 'chartData=1|2|3|4|5' >/dev/null 2>&1; chk "5 data points refused" "$?" 2
node "$S" "$R" "$TMP/xc" --no-music 'chartData=1|2|3|4|5|x' >/dev/null 2>&1; chk "non-numeric data refused" "$?" 2
node "$S" "$R" "$TMP/xd" --no-music 'paletteQuery=zzz' >/dev/null 2>&1; chk "query matching nothing refused" "$?" 2
node "$S" "$R" "$TMP/xe" --no-music 'paletteQuery=e' >/dev/null 2>&1; chk "query matching everything refused" "$?" 2
chk "refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'x*' | wc -l | tr -d ' ')" "0"
chk "--list includes $R" "$(node "$S" --list | grep -cx "$R")" "1"
HF_PLUGIN_ROOT="$TMP/none" node "$S" "$R" "$TMP/y" --no-music >/dev/null 2>&1
chk "missing plugin stops (exit 3)" "$?" 3
chk "missing plugin wrote nothing" "$([ -e "$TMP/y" ] && echo y || echo n)" "n"
exit "$FAIL"
