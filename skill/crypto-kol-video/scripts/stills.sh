#!/bin/bash
# Quick visual QA: render one still per scene (end of each scene's last line) + frame 0, and tile them into a contact sheet.
# usage: stills.sh <proj>
set -e
P=$(cd "$1" && pwd); cd "$P/video"
BX=(); [ -n "$BROWSER" ] && BX=(--browser-executable="$BROWSER")
npx remotion bundle src/index.ts --out-dir="$P/build/bundle" --log=error
mkdir -p "$P/build/stills"; rm -f "$P/build/stills/"*.png
FR=$(python3 -c "
import json;t=json.load(open('src/timeline.json'))
print(' '.join(['0']+[str(s['subs'][-1]['v']+14) for s in t['scenes']]+[str(t['followAt']+50)]))")
for fr in $FR; do npx remotion still "$P/build/bundle" Main "$P/build/stills/f$fr.png" --frame=$fr "${BX[@]}" --log=error; done
python3 - "$P/build/stills" <<'PY'
import sys,glob,os
from PIL import Image
d=sys.argv[1]; fs=sorted(glob.glob(d+'/f*.png'),key=lambda s:int(os.path.basename(s)[1:-4]))
ims=[Image.open(x).crop((0,0,1080,1420)).resize((360,473)) for x in fs]; cols=5; rows=(len(ims)+cols-1)//cols
W=Image.new('RGB',(360*cols,473*rows));[W.paste(im,((i%cols)*360,(i//cols)*473)) for i,im in enumerate(ims)]
W.save(d+'/sheet.png'); print(d+'/sheet.png')
PY
