#!/usr/bin/env bash
# Download the open-source fonts styles/base.json references (all SIL OFL 1.1). Fonts are not
# committed to this repo (fonts/ is gitignored) — run this once after cloning. render/fonts.py
# also finds these files if you install them under ~/Library/Fonts instead.
#
#   ./scripts/get_fonts.sh
#
# Pulls: Source Han Sans SC (Regular/Medium/Bold/Heavy — the `sans` role; Heavy is needed by
# library/card-number-impact's big-digit rendering), Source Han Serif SC (Bold/Heavy — `serif`),
# LXGW WenKai (Regular — `kai`). See fonts/SOURCES.md for exact versions/licenses, and for the
# 3 optional roles (display/mono/latin) this script does not fetch.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
DEST="fonts"
mkdir -p "$DEST"

dl() { # dl <url> <dest-file> <sha256>
  local url="$1" dest="$2" want="$3" got
  if [ -f "$dest" ]; then
    got=$(shasum -a 256 "$dest" | cut -d' ' -f1)
    if [ "$got" = "$want" ]; then echo "ok (cached): $dest"; return 0; fi
    echo "checksum stale, re-downloading: $dest"
  fi
  echo "-> $dest"
  curl -fL --progress-bar -o "$dest.part" "$url"
  got=$(shasum -a 256 "$dest.part" | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then
    echo "CHECKSUM MISMATCH for $dest" >&2
    echo "  expected $want" >&2
    echo "  got      $got" >&2
    echo "  (upstream may have moved; check fonts/SOURCES.md for the current URL/tag)" >&2
    rm -f "$dest.part"
    exit 1
  fi
  mv "$dest.part" "$dest"
  echo "ok: $dest"
}

echo "== Source Han Sans SC 2.005R · 思源黑体 (SIL OFL 1.1) =="
BASE_SANS="https://raw.githubusercontent.com/adobe-fonts/source-han-sans/2.005R"
dl "$BASE_SANS/OTF/SimplifiedChinese/SourceHanSansSC-Regular.otf" "$DEST/SourceHanSansSC-Regular.otf" \
   "f1d8611151880c6c336aabeac4640ef434fa13cbfbf1ffe82d0a71b2a5637256"
dl "$BASE_SANS/OTF/SimplifiedChinese/SourceHanSansSC-Medium.otf" "$DEST/SourceHanSansSC-Medium.otf" \
   "1df61d31687d04fd2f928a3bb6ca6cd61f0e988cc267cf317f32406edbb49f70"
dl "$BASE_SANS/OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf" "$DEST/SourceHanSansSC-Bold.otf" \
   "df2b90f5bcc6d01dfc964cec5f6d535d6b6aebd26ed7fd79a9c1b3f2112fcb6b"
dl "$BASE_SANS/OTF/SimplifiedChinese/SourceHanSansSC-Heavy.otf" "$DEST/SourceHanSansSC-Heavy.otf" \
   "6374b11bc4c2cd4bd7be1a1d64cf5047906c8a6a025c64e023c6792e50ba985e"
dl "$BASE_SANS/LICENSE.txt" "$DEST/LICENSE-SourceHanSans.txt" \
   "fcac737e761ec63dbfbdce11030a1780161920d80315edba9c8beff1c2bac5a2"

echo "== Source Han Serif SC 2.003R · 思源宋体 (SIL OFL 1.1) =="
BASE_SERIF="https://raw.githubusercontent.com/adobe-fonts/source-han-serif/2.003R"
dl "$BASE_SERIF/OTF/SimplifiedChinese/SourceHanSerifSC-Bold.otf" "$DEST/SourceHanSerifSC-Bold.otf" \
   "706b8c0de2deff6cbc0c87e2cdedfd33a78b7ffd76cebb4549012f197ba611fe"
dl "$BASE_SERIF/OTF/SimplifiedChinese/SourceHanSerifSC-Heavy.otf" "$DEST/SourceHanSerifSC-Heavy.otf" \
   "d033af54f96530476faed924ab5d5e9e6ef0833495670fd57bab9a7758398048"
dl "$BASE_SERIF/LICENSE.txt" "$DEST/LICENSE-SourceHanSerif.txt" \
   "9ff5bb567e1b92c801fc1069e5fbf992ff8efccacb9db94e5959a5b3ba9bb903"

echo "== LXGW WenKai v1.522 · 霞鹬文楷 (SIL OFL 1.1) =="
BASE_LXGW="https://github.com/lxgw/LxgwWenKai/releases/download/v1.522"
dl "$BASE_LXGW/LXGWWenKai-Regular.ttf" "$DEST/LXGWWenKai-Regular.ttf" \
   "39ad71264b588165b469e35e6afb162a378dacd1f95348160240ba9038ac3009"
dl "https://raw.githubusercontent.com/lxgw/LxgwWenKai/v1.522/OFL.txt" "$DEST/LICENSE-LXGWWenKai.txt" \
   "c38b1994a5e48ac30ac7d1da7d0409fd8fd8127dfe28a13d6e787d5b1ef34a5e"

echo
echo "Done: $(du -sh "$DEST" 2>/dev/null | cut -f1) in $DEST/"
echo "Optional roles this script skips (display/mono/latin) and manual-download fallback: see fonts/SOURCES.md"
