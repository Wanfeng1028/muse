#!/usr/bin/env bash
# Self-check for scaffold.mjs + the intro-kinetic, pixel-dissolve, circle-pop, screen-dive, text-sandwich and letter-flythrough recipes. Offline: a fake
# hyperframes plugin supplies the copied assets, and --no-music skips numpy.
#
#   bash skills/hf-motion/scripts/scaffold.selfcheck.sh
#
# Scaffolds the default and an alternate config into temp dirs and asserts the
# alternate CONFIG, its static timing attributes and its literal UTF-8 text all
# took effect, then exercises the refusal paths.
set -u
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
S="$HERE/scaffold.mjs"
FAIL=0
chk() { # chk <label> <got> <want>
    if [ "$2" = "$3" ]; then echo "ok    $1"; else echo "FAIL  $1: got '$2' want '$3'"; FAIL=1; fi
}
TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"
mkdir -p "$P/skills/hyperframes/scripts" "$P/skills/demo/assets/vendor" "$P/skills/media-use/audio/assets/sfx"
: > "$P/skills/hyperframes/scripts/plugin-cli.mjs"
echo '/* gsap fixture */' > "$P/skills/demo/assets/vendor/gsap.min.js"
: > "$P/skills/media-use/audio/assets/sfx/impact-bass-1.mp3"
: > "$P/skills/media-use/audio/assets/sfx/whoosh-short.mp3"
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

# 1. default: timing identical to the original 15 s / 120 BPM cut
node "$S" intro-kinetic "$TMP/def" --no-music >/dev/null
chk "default exit" "$?" 0
chk "default name" "$(cfg "$TMP/def" c.name)" "윤병우"
chk "default total" "$(attr "$TMP/def" stage data-duration)" "15"
chk "default s6 start" "$(attr "$TMP/def" s6 data-start)" "11"
chk "default whoosh-4" "$(attr "$TMP/def" sfx-whoosh-4 data-start)" "8.7"
chk "gsap copied from plugin" "$(cat "$TMP/def/assets/vendor/gsap.min.js")" "/* gsap fixture */"
chk "font bundled" "$([ -s "$TMP/def/assets/fonts/NanumSquare_acEB.ttf" ] && echo y)" "y"
chk "recipe.mjs not copied" "$([ -e "$TMP/def/recipe.mjs" ] && echo y || echo n)" "n"
chk "package.json pins plugin version" "$(node -p 'require(process.argv[1]).scripts.render' "$TMP/def/package.json")" "npx --yes hyperframes@9.9.9 render"

# 2. alternate: different text, counts, palette and tempo
node "$S" intro-kinetic "$TMP/alt" --no-music 'name=홍길동' 'team=가나다팀' 'subsTarget=123000' \
    'tools=Notion Kit|Daily Log' 'flash=습관|기록|성장' 'finale=평범한 직장인이 알려주는|[돈과 시간]을 버는|[작은 습관] 하나' \
    'red=#c0392b' 'bpm=116' >/dev/null
chk "alt exit" "$?" 0
chk "alt name" "$(cfg "$TMP/alt" c.name)" "홍길동"
chk "alt team" "$(cfg "$TMP/alt" c.team)" "가나다팀"
chk "alt title follows name" "$(cfg "$TMP/alt" c.title)" "홍길동 자기소개"
chk "alt subsTarget is a number" "$(cfg "$TMP/alt" 'typeof c.subsTarget + c.subsTarget')" "number123000"
chk "alt tools list" "$(cfg "$TMP/alt" 'c.tools.join("/")')" "Notion Kit/Daily Log"
chk "alt flash count" "$(cfg "$TMP/alt" c.flash.length)" "3"
chk "alt finale comma kept inside item" "$(cfg "$TMP/alt" 'c.finale[1]')" "[돈과 시간]을 버는"
chk "alt palette" "$(cfg "$TMP/alt" c.red)" "#c0392b"
chk "alt untouched key keeps default" "$(cfg "$TMP/alt" c.employer)" "삼성 시니어 엔지니어"
chk "alt total = 29 beats @116" "$(attr "$TMP/alt" stage data-duration)" "15"
chk "alt s5 = 3 beats" "$(attr "$TMP/alt" s5 data-duration)" "1.551724"
chk "alt finale impact follows s6" "$(attr "$TMP/alt" sfx-impact-finale data-start)" "$(attr "$TMP/alt" s6 data-start)"
chk "alt music = total" "$(attr "$TMP/alt" music data-duration)" "15"
chk "Korean is literal UTF-8, no \\u escapes" "$(grep -c '\\u[0-9a-fA-F]\{4\}' "$TMP/alt/index.html")" \
    "$(grep -c '\\u[0-9a-fA-F]\{4\}' "$HERE/../templates/intro-kinetic/index.html")"
grep -q '"name": "홍길동"' "$TMP/alt/index.html"; chk "literal 홍길동 in CONFIG" "$?" 0

# 3. --update re-applies on top of the project's own CONFIG
node "$S" intro-kinetic "$TMP/alt" --update --no-music 'flash=하나|둘' >/dev/null
chk "update exit" "$?" 0
chk "update kept earlier override" "$(cfg "$TMP/alt" c.name)" "홍길동"
chk "update resynced s5" "$(attr "$TMP/alt" s5 data-duration)" "1.034483"

# 4. refusals
node "$S" intro-kinetic "$TMP/def" --no-music >/dev/null 2>&1; chk "non-empty dir refused" "$?" 2
node "$S" intro-kinetic "$TMP/x1" --no-music 'nmae=x' >/dev/null 2>&1; chk "unknown key refused" "$?" 2
node "$S" intro-kinetic "$TMP/x2" --no-music 'tools=a|b|c|d' >/dev/null 2>&1; chk "4 tools refused" "$?" 2
node "$S" intro-kinetic "$TMP/x3" --no-music 'bpm=fast' >/dev/null 2>&1; chk "non-numeric bpm refused" "$?" 2
node "$S" intro-kinetic "$TMP/x4" --no-music 'red=red' >/dev/null 2>&1; chk "non-hex colour refused" "$?" 2
node "$S" intro-kinetic "$TMP/x5" --no-music 'red=#fca311' 'paper=#fafafa' >/dev/null 2>&1; chk "low-contrast red refused" "$?" 2
chk "refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'x*' | wc -l | tr -d ' ')" "0"
node "$S" intro-kinetic "$TMP/ok6" --no-music 'name=홍길동' 'title=내 소개' >/dev/null 2>&1; chk "explicit title kept" "$(cfg "$TMP/ok6" c.title)" "내 소개"
node "$S" no-such-recipe "$TMP/x5" >/dev/null 2>&1; chk "unknown recipe refused (no planned recipe left)" "$?" 2
chk "--list = implemented only" "$(node "$S" --list | tr '\n' ' ')" "circle-pop intro-kinetic launch-film letter-flythrough pixel-dissolve screen-dive text-sandwich ui-morph "
HF_PLUGIN_ROOT="$TMP/none" node "$S" intro-kinetic "$TMP/y" --no-music >/dev/null 2>&1
chk "missing plugin stops (exit 3)" "$?" 3
chk "missing plugin wrote nothing" "$([ -e "$TMP/y" ] && echo y || echo n)" "n"

# 5. pixel-dissolve: no music bed, fixed 6 s, timing from transitionAt/Dur
PD="$HERE/../templates/pixel-dissolve"
out=$(node "$S" pixel-dissolve "$TMP/pd")
chk "pd default exit" "$?" 0
chk "pd no-music line" "$(printf '%s\n' "$out" | sed -n 's/.*(\(.*\))$/\1/p' | head -1)" "6s, no music"
chk "pd verify-render args" "$(printf '%s\n' "$out" | sed -n 's/^verify-render args: //p')" "--duration 6 --width 1080 --height 830"
chk "pd no music generated" "$([ -e "$TMP/pd/assets/music.wav" ] && echo y || echo n)" "n"
chk "pd textA" "$(cfg "$TMP/pd" c.textA)" "어제의 나"
chk "pd defaults" "$(cfg "$TMP/pd" '[c.textB,c.transitionAt,c.transitionDur,c.pixelSize,c.bgA,c.bgB,c.paper,c.charcoal,c.red].join("/")')" \
    "오늘의 나/3/1/40/charcoal/paper/#f2eee6/#1e1e1e/#e5322d"
chk "pd total" "$(attr "$TMP/pd" stage data-duration)" "6"
chk "pd canvas" "$(attr "$TMP/pd" stage data-width)x$(attr "$TMP/pd" stage data-height)" "1080x830"
chk "pd sA ends with the dissolve" "$(attr "$TMP/pd" sA data-duration)" "4"
chk "pd sB from transitionAt" "$(attr "$TMP/pd" sB data-start)/$(attr "$TMP/pd" sB data-duration)" "3/3"
chk "pd fx = transitionDur" "$(attr "$TMP/pd" fx data-duration)" "1"
chk "pd gsap copied, font bundled" "$(cat "$TMP/pd/assets/vendor/gsap.min.js")$([ -s "$TMP/pd/assets/fonts/NanumSquare_acEB.ttf" ] && echo y)" "/* gsap fixture */y"
node "$S" pixel-dissolve "$TMP/pd2" 'textA=작년의 평범한 직장인 김철수' transitionAt=2.5 transitionDur=1.5 pixelSize=24 bgA=red >/dev/null
chk "pd alt exit" "$?" 0
chk "pd alt timing" "$(attr "$TMP/pd2" sA data-duration)/$(attr "$TMP/pd2" sB data-start)/$(attr "$TMP/pd2" sB data-duration)/$(attr "$TMP/pd2" fx data-duration)" "4/2.5/3.5/1.5"
chk "pd alt literal Korean" "$(cfg "$TMP/pd2" c.textA)" "작년의 평범한 직장인 김철수"
node "$S" pixel-dissolve "$TMP/z1" transitionAt=4.5 transitionDur=1.5 >/dev/null 2>&1; chk "pd no hold refused" "$?" 2
node "$S" pixel-dissolve "$TMP/z2" pixelSize=7 >/dev/null 2>&1; chk "pd pixelSize floor refused" "$?" 2
node "$S" pixel-dissolve "$TMP/z3" bgB=blue >/dev/null 2>&1; chk "pd unknown bg refused" "$?" 2
chk "pd refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'z*' | wc -l | tr -d ' ')" "0"
# determinism: seeded order, no Math.random, template copy == recipe.mjs reference
chk "pd no Math.random" "$(grep -c 'Math\.random' "$PD/index.html" "$PD/recipe.mjs" | cut -d: -f2 | tr '\n' ' ')" "0 0 "
chk "pd cell order seeded + template matches recipe.mjs" "$(node --input-type=module -e '
  import { readFileSync } from "node:fs";
  const { cellOrder, grid } = await import(process.argv[1] + "/recipe.mjs");
  const h = readFileSync(process.argv[1] + "/index.html", "utf8");
  const tplOrder = eval("(" + h.slice(h.indexOf("const cellOrder = ") + 18, h.indexOf("const P = C.pixelSize")).trim().replace(/;$/, "") + ")");
  const { cols, rows } = grid({ pixelSize: 40 }), n = cols * rows;
  const a = cellOrder(n), b = cellOrder(n), t = tplOrder(n, 719);
  const perm = [...a].sort((x, y) => x - y).every((v, i) => v === i);
  const shuffled = a.some((v, i) => v !== i);
  console.log([n, perm, shuffled, a.join() === b.join(), a.join() === t.join()].join("/"));
' "$PD")" "567/true/true/true/true"

# 6. circle-pop: no music bed, fixed 6 s, the circle becomes scene B
CP="$HERE/../templates/circle-pop"
out=$(node "$S" circle-pop "$TMP/cp")
chk "cp default exit" "$?" 0
chk "cp verify-render args" "$(printf '%s\n' "$out" | sed -n 's/^verify-render args: //p')" "--duration 6 --width 1080 --height 830"
chk "cp no music generated" "$([ -e "$TMP/cp/assets/music.wav" ] && echo y || echo n)" "n"
chk "cp defaults" "$(cfg "$TMP/cp" '[c.textA,c.textB,c.transitionAt,c.popOrigin,c.popColor,c.overshoot,c.paper,c.charcoal,c.red].join("/")')" \
    "아이디어/완성된 영상/3/center/red/1.15/#f2eee6/#1e1e1e/#e5322d"
chk "cp total + canvas" "$(attr "$TMP/cp" stage data-duration) $(attr "$TMP/cp" stage data-width)x$(attr "$TMP/cp" stage data-height)" "6 1080x830"
chk "cp sA ends when the circle covers (T+0.9)" "$(attr "$TMP/cp" sA data-duration)" "3.9"
chk "cp sB from transitionAt" "$(attr "$TMP/cp" sB data-start)/$(attr "$TMP/cp" sB data-duration)" "3/3"
chk "cp gsap copied, font bundled" "$(cat "$TMP/cp/assets/vendor/gsap.min.js")$([ -s "$TMP/cp/assets/fonts/NanumSquare_acEB.ttf" ] && echo y)" "/* gsap fixture */y"
node "$S" circle-pop "$TMP/cp2" 'textA=기획서' 'textB=런칭 완료' transitionAt=2.2 popOrigin=0.15,0.8 popColor=charcoal overshoot=1.4 >/dev/null
chk "cp alt exit" "$?" 0
chk "cp alt timing" "$(attr "$TMP/cp2" sA data-duration)/$(attr "$TMP/cp2" sB data-start)/$(attr "$TMP/cp2" sB data-duration)" "3.1/2.2/3.8"
chk "cp alt values" "$(cfg "$TMP/cp2" '[c.textB,c.popOrigin,c.popColor,c.overshoot].join("/")')" "런칭 완료/0.15,0.8/charcoal/1.4"
node "$S" circle-pop "$TMP/w1" transitionAt=4.2 >/dev/null 2>&1; chk "cp no hold refused" "$?" 2
node "$S" circle-pop "$TMP/w2" overshoot=1.8 >/dev/null 2>&1; chk "cp overshoot ceiling refused" "$?" 2
node "$S" circle-pop "$TMP/w3" overshoot=0.9 >/dev/null 2>&1; chk "cp overshoot floor refused" "$?" 2
node "$S" circle-pop "$TMP/w4" popOrigin=1.2,0.5 >/dev/null 2>&1; chk "cp origin outside frame refused" "$?" 2
node "$S" circle-pop "$TMP/w5" popOrigin=left >/dev/null 2>&1; chk "cp origin word refused" "$?" 2
node "$S" circle-pop "$TMP/w6" popColor=blue >/dev/null 2>&1; chk "cp off-palette colour refused" "$?" 2
chk "cp refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'w*' | wc -l | tr -d ' ')" "0"
# seek safety: the template's radius() is clamped at both boundaries, peaks at
# R0*overshoot inside the pop, never runs backwards in the fill, and its
# POP/FILL match recipe.mjs
chk "cp radius clamped + template matches recipe.mjs" "$(node --input-type=module -e '
  import { readFileSync } from "node:fs";
  const R = await import(process.argv[1] + "/recipe.mjs");
  const h = readFileSync(process.argv[1] + "/index.html", "utf8");
  const [, POP, FILL] = h.match(/const POP = ([\d.]+), FILL = ([\d.]+);/).map(Number);
  const radius = eval("(" + h.slice(h.indexOf("const radius = ") + 15, h.indexOf("const draw = ")).trim().replace(/;$/, "") + ")");
  const R0 = 200, RC = 1000, OS = 1.15, ts = Array.from({ length: 901 }, (_, i) => i / 1000);
  const rs = ts.map((t) => radius(t, R0, RC, OS));
  const peak = Math.max(...rs.filter((_, i) => ts[i] <= POP));
  const fillUp = rs.every((r, i) => ts[i] <= POP || r >= rs[i - 1] - 1e-9);
  console.log([POP === R.POP && FILL === R.FILL, radius(-1, R0, RC, OS), radius(0, R0, RC, OS), radius(POP, R0, RC, OS),
    radius(POP + FILL, R0, RC, OS), radius(POP + FILL + 0.3, R0, RC, OS), Math.abs(peak - R0 * OS) < 1, fillUp].join("/"));
' "$CP")" "true/0/0/200/1000/1000/true/true"

# 7. screen-dive: no music bed, fixed 6 s, device leaves when the dive lands
SD="$HERE/../templates/screen-dive"
out=$(node "$S" screen-dive "$TMP/sd")
chk "sd default exit" "$?" 0
chk "sd verify-render args" "$(printf '%s\n' "$out" | sed -n 's/^verify-render args: //p')" "--duration 6 --width 1080 --height 830"
chk "sd no music generated" "$([ -e "$TMP/sd/assets/music.wav" ] && echo y || echo n)" "n"
chk "sd defaults" "$(cfg "$TMP/sd" '[c.screenText,c.diveAt,c.diveDur,c.deviceStyle,c.paper,c.charcoal,c.red].join("/")')" \
    "모션 그래픽/2/2.5/laptop/#f2eee6/#1e1e1e/#e5322d"
chk "sd total + canvas" "$(attr "$TMP/sd" stage data-duration) $(attr "$TMP/sd" stage data-width)x$(attr "$TMP/sd" stage data-height)" "6 1080x830"
chk "sd device ends with the dive" "$(attr "$TMP/sd" device data-start)/$(attr "$TMP/sd" device data-duration)" "0/4.5"
chk "sd screen is one DOM for all 6 s" "$(attr "$TMP/sd" screen data-start)/$(attr "$TMP/sd" screen data-duration)" "0/6"
chk "sd gsap copied, font bundled" "$(cat "$TMP/sd/assets/vendor/gsap.min.js")$([ -s "$TMP/sd/assets/fonts/NanumSquare_acEB.ttf" ] && echo y)" "/* gsap fixture */y"
node "$S" screen-dive "$TMP/sd2" 'screenText=Hello 새로운 화면' diveAt=1.2 diveDur=3.5 'red=#c0392b' >/dev/null
chk "sd alt exit" "$?" 0
chk "sd alt device window" "$(attr "$TMP/sd2" device data-duration)" "4.7"
chk "sd alt literal Korean" "$(cfg "$TMP/sd2" c.screenText)" "Hello 새로운 화면"
node "$S" screen-dive "$TMP/v1" diveAt=3 diveDur=3 >/dev/null 2>&1; chk "sd no hold refused" "$?" 2
node "$S" screen-dive "$TMP/v2" diveAt=0.5 >/dev/null 2>&1; chk "sd dive before entrance refused" "$?" 2
node "$S" screen-dive "$TMP/v3" deviceStyle=phone >/dev/null 2>&1; chk "sd unknown device refused" "$?" 2
chk "sd refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'v*' | wc -l | tr -d ' ')" "0"
# no image asset: the laptop is drawn in CSS; the glass is exactly the canvas ratio at half size
chk "sd no image in template" "$(find "$SD" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.svg' -o -name '*.webp' \) | wc -l | tr -d ' ')" "0"
chk "sd glass = half canvas" "$(sed -n '/#glass {/,/}/p' "$SD/index.html" | grep -Eo '(width|height): [0-9]+px' | tr '\n' ' ')" "width: 540px height: 415px "

# 8. text-sandwich: the character image is the user's file, copied in, never bundled
TS="$HERE/../templates/text-sandwich"
mkdir -p "$TMP/img" && cd "$TMP/img" || exit 1
# throwaway 1x1 transparent PNG, generated here, never committed
printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==' | base64 -d > alex.png
printf 'GIF89a' > other.gif
out=$(node "$S" text-sandwich "$TMP/ts")
chk "ts default exit (alex.png in cwd)" "$?" 0
chk "ts verify-render args" "$(printf '%s\n' "$out" | sed -n 's/^verify-render args: //p')" "--duration 6 --width 1080 --height 830"
chk "ts no music generated" "$([ -e "$TMP/ts/assets/music.wav" ] && echo y || echo n)" "n"
chk "ts defaults" "$(cfg "$TMP/ts" '[c.word,c.characterImage,c.direction,c.passAt,c.passDur,c.paper,c.charcoal,c.red].join("/")')" \
    "MOTION/alex.png/ltr/1.5/2.5/#f2eee6/#1e1e1e/#e5322d"
chk "ts image copied byte-exact" "$(cmp -s alex.png "$TMP/ts/assets/character.png" && echo y || echo n)" "y"
chk "ts total + canvas" "$(attr "$TMP/ts" stage data-duration) $(attr "$TMP/ts" stage data-width)x$(attr "$TMP/ts" stage data-height)" "6 1080x830"
chk "ts character window = pass" "$(attr "$TMP/ts" character data-start)/$(attr "$TMP/ts" character data-duration)" "1.5/2.5"
chk "ts both slices run 6 s" "$(attr "$TMP/ts" back data-duration)/$(attr "$TMP/ts" front data-duration)" "6/6"
chk "ts gsap copied, font bundled" "$(cat "$TMP/ts/assets/vendor/gsap.min.js")$([ -s "$TMP/ts/assets/fonts/NanumSquare_acEB.ttf" ] && echo y)" "/* gsap fixture */y"
node "$S" text-sandwich "$TMP/ts2" 'word=샌드위치 TEXT' characterImage="$TMP/img/alex.png" direction=rtl passAt=1 passDur=3.5 'red=#c0392b' >/dev/null
chk "ts alt exit (absolute path)" "$?" 0
chk "ts alt window" "$(attr "$TMP/ts2" character data-start)/$(attr "$TMP/ts2" character data-duration)" "1/3.5"
chk "ts alt literal Korean" "$(cfg "$TMP/ts2" c.word)" "샌드위치 TEXT"
node "$S" text-sandwich "$TMP/ts2" --update characterImage=other.gif >/dev/null
chk "ts update re-copies a passed image" "$(head -c 6 "$TMP/ts2/assets/character.png")" "GIF89a"
node "$S" text-sandwich "$TMP/ts2" --update passAt=2 >/dev/null
chk "ts update keeps the copied image" "$(head -c 6 "$TMP/ts2/assets/character.png")/$(attr "$TMP/ts2" character data-start)" "GIF89a/2"
# missing / unreadable / wrong-kind asset: exit 2, a message naming the key, nothing written
err=$(node "$S" text-sandwich "$TMP/u1" characterImage=nope.png 2>&1 >/dev/null); rc=$?
chk "ts missing image refused" "$rc" 2
chk "ts missing image message" "$(printf '%s' "$err" | grep -c 'characterImage: cannot read')" "1"
(cd "$TMP" && node "$S" text-sandwich "$TMP/u2" >/dev/null 2>&1); chk "ts default without alex.png refused" "$?" 2
mkdir "$TMP/img/dir.png"; node "$S" text-sandwich "$TMP/u3" characterImage=dir.png >/dev/null 2>&1; chk "ts directory refused" "$?" 2
cp alex.png locked.png && chmod 000 locked.png
if [ -r locked.png ]; then echo "skip  ts unreadable image (running as root)"; else
    node "$S" text-sandwich "$TMP/u4" characterImage=locked.png >/dev/null 2>&1; chk "ts unreadable image refused" "$?" 2; fi
node "$S" text-sandwich "$TMP/u5" characterImage=x.svg >/dev/null 2>&1; chk "ts svg refused" "$?" 2
node "$S" text-sandwich "$TMP/u6" direction=up >/dev/null 2>&1; chk "ts unknown direction refused" "$?" 2
node "$S" text-sandwich "$TMP/u7" passAt=3 passDur=3 >/dev/null 2>&1; chk "ts no hold refused" "$?" 2
node "$S" text-sandwich "$TMP/u8" 'word=ABCDEFGHIJKLM' >/dev/null 2>&1; chk "ts long word refused" "$?" 2
chk "ts refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'u*' | wc -l | tr -d ' ')" "0"
chk "ts no image in template" "$(find "$TS" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.gif' -o -name '*.webp' \) | wc -l | tr -d ' ')" "0"
cd "$HERE" || exit 1

# 9. letter-flythrough: no music bed, fixed 6 s, glyph outlines generated from the bundled font
LF="$HERE/../templates/letter-flythrough"
g() { # g <project> <js-expr over GLYPHS g> -> value
    node -e 'const window={};eval(require("fs").readFileSync(process.argv[1],"utf8"));const g=window.GLYPHS;console.log(eval(process.argv[2]))' "$1/glyphs.js" "$2"
}
out=$(node "$S" letter-flythrough "$TMP/lf")
chk "lf default exit" "$?" 0
chk "lf verify-render args" "$(printf '%s\n' "$out" | sed -n 's/^verify-render args: //p')" "--duration 6 --width 1080 --height 830"
chk "lf no music generated" "$([ -e "$TMP/lf/assets/music.wav" ] && echo y || echo n)" "n"
chk "lf defaults" "$(cfg "$TMP/lf" '[c.letters,c.nextText,c.diveAt,c.diveDur,c.targetGlyphIndex,c.paper,c.charcoal,c.red].join("/")')" \
    "AI/프롬프트 한 줄/2/2/0/#f2eee6/#1e1e1e/#e5322d"
chk "lf total + canvas" "$(attr "$TMP/lf" stage data-duration) $(attr "$TMP/lf" stage data-width)x$(attr "$TMP/lf" stage data-height)" "6 1080x830"
chk "lf letters end with the dive" "$(attr "$TMP/lf" letters data-start)/$(attr "$TMP/lf" letters data-duration)" "0/4"
chk "lf next scene is one DOM for all 6 s" "$(attr "$TMP/lf" next data-start)/$(attr "$TMP/lf" next data-duration)" "0/6"
chk "lf gsap copied, font bundled" "$(cat "$TMP/lf/assets/vendor/gsap.min.js")$([ -s "$TMP/lf/assets/fonts/NanumSquare_acEB.ttf" ] && echo y)" "/* gsap fixture */y"
# drift guard: the template's committed glyphs.js is exactly what the scaffold generates for the default
chk "lf template glyphs.js = generated default" "$(cmp -s "$LF/glyphs.js" "$TMP/lf/glyphs.js" && echo same || echo differs)" "same"
chk "lf glyphs for AI, landing rect at canvas ratio" "$(g "$TMP/lf" '[g.letters,g.targetGlyphIndex,Math.abs(g.rect[2]/g.rect[3]-1080/830)<0.01,g.hole.startsWith("M"),g.ink.length>g.hole.length].join("/")')" "AI/0/true/true/true"
node "$S" letter-flythrough "$TMP/lf2" letters=OK 'nextText=Hello 다음 장면' diveAt=1.5 diveDur=3 'red=#c0392b' >/dev/null
chk "lf alt exit" "$?" 0
chk "lf alt letters window" "$(attr "$TMP/lf2" letters data-duration)" "4.5"
chk "lf alt glyphs follow CONFIG" "$(g "$TMP/lf2" 'g.letters+"/"+g.targetGlyphIndex')" "OK/0"
chk "lf alt literal Korean" "$(cfg "$TMP/lf2" c.nextText)" "Hello 다음 장면"
node "$S" letter-flythrough "$TMP/lf2" --update letters=오늘 >/dev/null
chk "lf update regenerates glyphs.js" "$(g "$TMP/lf2" g.letters)" "오늘"
msg=$(node "$S" letter-flythrough "$TMP/q1" targetGlyphIndex=1 2>&1 >/dev/null); rc=$?
chk "lf target without a counter refused" "$rc/$(printf '%s' "$msg" | grep -c "'I' (targetGlyphIndex 1) has no counter")" "2/1"
node "$S" letter-flythrough "$TMP/q2" letters=K >/dev/null 2>&1; chk "lf letter without a counter refused" "$?" 2
node "$S" letter-flythrough "$TMP/q3" targetGlyphIndex=2 >/dev/null 2>&1; chk "lf target index outside letters refused" "$?" 2
node "$S" letter-flythrough "$TMP/q4" letters=ABCDEFG >/dev/null 2>&1; chk "lf more than 6 letters refused" "$?" 2
node "$S" letter-flythrough "$TMP/q5" diveAt=3 diveDur=3 >/dev/null 2>&1; chk "lf no hold refused" "$?" 2
node "$S" letter-flythrough "$TMP/q6" diveAt=0.5 >/dev/null 2>&1; chk "lf dive before entrance refused" "$?" 2
chk "lf refused runs wrote nothing" "$(find "$TMP" -maxdepth 1 -name 'q*' | wc -l | tr -d ' ')" "0"
exit "$FAIL"
