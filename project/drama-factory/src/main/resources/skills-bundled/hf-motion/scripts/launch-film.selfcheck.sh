#!/usr/bin/env bash
# Self-check for scaffold.mjs + the launch-film recipe. Offline: a fake
# hyperframes plugin supplies GSAP; --no-music skips the numpy/ffmpeg bed.
#
#   bash skills/hf-motion/scripts/launch-film.selfcheck.sh
#
# Scaffolds the default and an alternate config (nine user photos passed as a
# list, one path with a space) into temp dirs and asserts the alternate
# CONFIG, its static timing attributes, the copied photos and the literal
# UTF-8 text all took effect, then exercises the refusal paths.
set -u
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
S="$HERE/scaffold.mjs"
TPL="$HERE/../templates/launch-film"
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
run() { node "$S" launch-film "$@" --no-music >/dev/null 2>&1; }

# 1. default: 54 beats at 120 BPM = 27 s, the shipped placeholder photos
node "$S" launch-film "$TMP/def" --no-music >/dev/null
chk "default exit" "$?" 0
chk "default wordmark" "$(cfg "$TMP/def" c.wordmark)" "Create"
chk "default photos" "$(cfg "$TMP/def" c.photos.length)" "9"
chk "default total" "$(attr "$TMP/def" stage data-duration)" "27"
chk "default film" "$(attr "$TMP/def" film data-duration)" "27"
chk "default music window" "$(attr "$TMP/def" music data-start)/$(attr "$TMP/def" music data-duration)" "0/27"
chk "canvas 1440x1440 @30" "$(attr "$TMP/def" stage data-width)x$(attr "$TMP/def" stage data-height)@$(attr "$TMP/def" stage data-fps)" "1440x1440@30"
chk "placeholder photos shipped" "$(cmp -s "$TMP/def/assets/photos/photo-09.jpg" "$TPL/assets/photos/photo-09.jpg" && echo y)" "y"
chk "fonts + licences bundled" "$(for f in archivo/archivo-latin-wdth-normal.woff2 archivo/OFL.txt geist/Geist-Variable.woff2 geist/OFL.txt; do [ -s "$TMP/def/assets/fonts/$f" ] || echo "missing $f"; done)" ""
chk "gsap copied from plugin" "$(cat "$TMP/def/assets/vendor/gsap.min.js")" "/* gsap fixture */"
chk "--no-music writes no bed" "$(find "$TMP/def" -name 'music.*' | wc -l | tr -d ' ')" "0"
chk "recipe.mjs not copied" "$([ -e "$TMP/def/recipe.mjs" ] && echo y || echo n)" "n"
chk "package.json pins plugin version" "$(node -p 'require(process.argv[1]).scripts.render' "$TMP/def/package.json")" "npx --yes hyperframes@9.9.9 render"

# 2. alternate: other words, nine user photos (one path with a space), palette, bpm
mkdir -p "$TMP/in"
L=""
for i in 1 2 3 4 5 6 7 8 9; do n="$TMP/in/shot $i.jpg"; [ "$i" -gt 1 ] && n="$TMP/in/s$i.png"; : > "$n"; L="$L|$n"; done
L="${L#|}"
node "$S" launch-film "$TMP/alt" --no-music 'wordmark=Make' 'openLabel=Gallery' 'glassWord=Clear' "photos=$L" \
    'lockTime=10:08' 'lockDate=Vendredi 3 mai' 'trackTitle=Café Noir' 'trackArtist=Zoë' 'landingHeadline=Prints that last.' \
    'productName=Wall print' 'frameColors=charcoal|red' 'sizes=A3|A2|A1|A0' 'orderLabel=Buy now' \
    'steps=Paid|Making|Shipped|Arrived' 'paper=#fff8e7' 'charcoal=#14213d' 'red=#d62828' 'bpm=110' >/dev/null
chk "alt exit" "$?" 0
chk "alt wordmark" "$(cfg "$TMP/alt" c.wordmark)" "Make"
chk "alt photos in CONFIG" "$(cfg "$TMP/alt" 'c.photos[0]+"|"+c.photos[8]')" "assets/shot 1.jpg|assets/s9.png"
chk "alt photos copied" "$(find "$TMP/alt/assets" -maxdepth 1 -type f -regextype posix-extended -regex '.*/(shot 1\.jpg|s[2-9]\.png)' | wc -l | tr -d ' ')" "9"
chk "alt lists" "$(cfg "$TMP/alt" '[c.frameColors.join(","),c.sizes.join(","),c.steps.join(",")].join(" ")')" "charcoal,red A3,A2,A1,A0 Paid,Making,Shipped,Arrived"
chk "alt palette" "$(cfg "$TMP/alt" '[c.paper,c.charcoal,c.red].join(" ")')" "#fff8e7 #14213d #d62828"
chk "alt bpm is a number" "$(cfg "$TMP/alt" 'typeof c.bpm + c.bpm')" "number110"
chk "alt total (54 beats @110)" "$(attr "$TMP/alt" stage data-duration)" "29.454545"
chk "alt film" "$(attr "$TMP/alt" film data-duration)" "29.454545"
chk "alt music" "$(attr "$TMP/alt" music data-duration)" "29.454545"
chk "text is literal UTF-8, no \\u escapes" "$(grep -c '\\u[0-9a-fA-F]\{4\}' "$TMP/alt/index.html")" \
    "$(grep -c '\\u[0-9a-fA-F]\{4\}' "$TPL/index.html")"
grep -q '"trackTitle": "Café Noir"' "$TMP/alt/index.html"; chk "literal Café Noir in CONFIG" "$?" 0

# 3. --update re-applies on top of the project's own CONFIG
node "$S" launch-film "$TMP/alt" --update --no-music 'bpm=100' >/dev/null
chk "update exit" "$?" 0
chk "update kept wordmark" "$(cfg "$TMP/alt" c.wordmark)" "Make"
chk "update kept photos" "$(cfg "$TMP/alt" c.photos[8])" "assets/s9.png"
chk "update resynced total" "$(attr "$TMP/alt" stage data-duration)" "32.4"
chk "update resynced music" "$(attr "$TMP/alt" music data-duration)" "32.4"

# 4. refusals (exit 2, nothing written)
EIGHT="${L%|*}"
run "$TMP/def"; chk "non-empty dir refused" "$?" 2
run "$TMP/x01" "photos=$EIGHT"; chk "8 photos refused" "$?" 2
run "$TMP/x02" "photos=$L|$TMP/in/s2.png|$TMP/in/s3.png|$TMP/in/s4.png|$TMP/in/s5.png"; chk "13 photos refused" "$?" 2
run "$TMP/x03" "photos=$EIGHT|$TMP/in/missing.jpg"; chk "missing photo refused" "$?" 2
mkdir -p "$TMP/in/b"; : > "$TMP/in/b/s9.png"
run "$TMP/x04" "photos=$L|$TMP/in/b/s9.png"; chk "duplicate photo names refused" "$?" 2
: > "$TMP/in/notes.txt"
run "$TMP/x05" "photos=$EIGHT|$TMP/in/notes.txt"; chk "non-image photo refused" "$?" 2
run "$TMP/x06" 'red=red'; chk "non-hex colour refused" "$?" 2
run "$TMP/x07" 'red=#f0d8d0'; chk "low-contrast red refused" "$?" 2
run "$TMP/x08" 'bpm=89'; chk "bpm 89 refused" "$?" 2
run "$TMP/x09" 'bpm=151'; chk "bpm 151 refused" "$?" 2
run "$TMP/x10" 'bpm=fast'; chk "non-numeric bpm refused" "$?" 2
run "$TMP/x11" 'wordmark=Go'; chk "2-letter wordmark refused" "$?" 2
run "$TMP/x12" 'wordmark=Wonderfuls'; chk "10-letter wordmark refused" "$?" 2
run "$TMP/x13" 'wordmark=Two words'; chk "two-word wordmark refused" "$?" 2
run "$TMP/x14" 'wordmark=만들다'; chk "non-Latin wordmark refused" "$?" 2
run "$TMP/x15" 'productName=액자'; chk "non-Latin text refused" "$?" 2
run "$TMP/x16" 'lockTime=noon'; chk "bad lockTime refused" "$?" 2
run "$TMP/x17" 'steps=One|Two|Three'; chk "3 steps refused" "$?" 2
run "$TMP/x18" 'frameColors=red|blue'; chk "non-palette frame colour refused" "$?" 2
run "$TMP/x19" 'frameColors=red|red'; chk "duplicate frame colour refused" "$?" 2
run "$TMP/x20" 'sizes=M'; chk "1 size refused" "$?" 2
run "$TMP/x21" 'glassWord=Ab'; chk "2-letter glassWord refused" "$?" 2
run "$TMP/x22" 'wrodmark=x'; chk "unknown key refused" "$?" 2
chk "refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'x*' | wc -l | tr -d ' ')" "0"
chk "--list includes launch-film" "$(node "$S" --list | grep -cx launch-film)" "1"
HF_PLUGIN_ROOT="$TMP/none" node "$S" launch-film "$TMP/y" --no-music >/dev/null 2>&1
chk "missing plugin stops (exit 3)" "$?" 3
chk "missing plugin wrote nothing" "$([ -e "$TMP/y" ] && echo y || echo n)" "n"
exit "$FAIL"
