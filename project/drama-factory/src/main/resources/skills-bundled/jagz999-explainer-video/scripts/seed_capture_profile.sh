#!/bin/bash
# Seed a CLEAN Chrome profile (.capdir) with ONLY the auth from the user's real profile,
# so puppeteer can launch fast (a heavy real profile → "Target.setDiscoverTargets timed out")
# while staying logged in. Run with the user's Chrome QUIT (so the cookie DB isn't locked).
#
# Usage:  ./seed_capture_profile.sh "<SourceProfileName>" [workdir]
#   e.g.  ./seed_capture_profile.sh "Profile 6"
# Find the profile name at chrome://version  (Profile Path) or in ~/Library/.../Chrome/.
set -u
SRC_NAME="${1:?need source profile name, e.g. 'Default' or 'Profile 6'}"
WORK="${2:-$PWD}"
CHROME_DIR="$HOME/Library/Application Support/Google/Chrome"   # macOS
SRC="$CHROME_DIR/$SRC_NAME"
CAP="$WORK/.capdir"

if pgrep -x "Google Chrome" >/dev/null; then echo "Quit Google Chrome first."; exit 1; fi
[ -d "$SRC" ] || { echo "source profile not found: $SRC"; exit 1; }

rm -rf "$CAP"; mkdir -p "$CAP/Default/Network"
cp "$CHROME_DIR/Local State" "$CAP/Local State"               # holds the cookie-encryption key
# cookies live at Profile/Cookies (older) and/or Profile/Network/Cookies (newer) — copy both
[ -f "$SRC/Cookies" ]         && cp "$SRC/Cookies"         "$CAP/Default/Cookies"
[ -f "$SRC/Network/Cookies" ] && cp "$SRC/Network/Cookies" "$CAP/Default/Network/Cookies"
[ -f "$SRC/Cookies" ] && [ ! -f "$CAP/Default/Network/Cookies" ] && cp "$SRC/Cookies" "$CAP/Default/Network/Cookies"
cp -R "$SRC/Local Storage"   "$CAP/Default/Local Storage"   2>/dev/null
cp -R "$SRC/IndexedDB"       "$CAP/Default/IndexedDB"       2>/dev/null
cp -R "$SRC/Session Storage" "$CAP/Default/Session Storage" 2>/dev/null
cp    "$SRC/Preferences"     "$CAP/Default/Preferences"     2>/dev/null
find "$CAP" -name LOCK -delete 2>/dev/null
echo "seeded $CAP from '$SRC_NAME'  ($(du -sh "$CAP" | cut -f1))"
echo "NOTE: session cookies may not survive; capture.js waits for a manual login if so."
