#!/usr/bin/env bash
# First-run check: lists every tool the skill needs that this machine lacks,
# with the install command for this system. Installs nothing itself: the agent
# shows the list, asks the person, and only then runs the commands.
# Exit 0 when everything is present, 2 when something is missing.
# Output lines the agent reads: "OK <tool>", "MISSING <tool>: <why>",
# "INSTALL <command>", "NOTE <text>".

missing=()
have() { command -v "$1" >/dev/null 2>&1; }

# node 18 or newer: Playwright refuses older versions
if have node && have npm && have npx; then
  major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
  if [ "${major:-0}" -ge 18 ]; then echo "OK node $(node -v)"; else missing+=(node); echo "MISSING node: version $(node -v) is too old, 18 or newer is needed"; fi
else
  missing+=(node); echo "MISSING node: runs the renderer (Playwright)"
fi
if have ffmpeg && have ffprobe; then echo "OK ffmpeg"; else missing+=(ffmpeg); echo "MISSING ffmpeg: assembles the video and reads the inspiration and footage"; fi
if have python3; then
  echo "OK python3 $(python3 -V 2>&1 | cut -d' ' -f2)"
  if python3 -c "import numpy" 2>/dev/null; then echo "OK numpy"; else missing+=(numpy); echo "MISSING numpy: python package for the soundtrack and the tempo analysis"; fi
else
  missing+=(python3 numpy); echo "MISSING python3: builds the fonts and the soundtrack"
  echo "MISSING numpy: python package for the soundtrack and the tempo analysis"
fi

[ ${#missing[@]} -eq 0 ] && { echo "all tools present"; exit 0; }

needs() { for m in "${missing[@]}"; do [ "$m" = "$1" ] && return 0; done; return 1; }
case "$(uname -s)" in
  Darwin)
    if ! have brew; then
      echo "NOTE Homebrew, the macOS package manager, is not installed. The person runs its official installer in their own Terminal (it asks for their Mac password), then reopens the terminal:"
      echo 'INSTALL /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    fi
    pkgs=(); needs node && pkgs+=(node); needs ffmpeg && pkgs+=(ffmpeg); needs python3 && pkgs+=(python)
    [ ${#pkgs[@]} -gt 0 ] && echo "INSTALL brew install ${pkgs[*]}"
    needs numpy && echo "INSTALL python3 -m pip install --user numpy"
    ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null; then echo "NOTE running in WSL: the Linux commands below apply"; fi
    # only what is actually missing, in each manager's package names
    pk() { local out=(); needs node && [ -n "$1" ] && out+=($1); needs ffmpeg && out+=($2); needs python3 && out+=($3); needs numpy && out+=($4); echo "${out[*]}"; }
    if have apt-get; then
      p=$(pk "" ffmpeg python3 python3-numpy); [ -n "$p" ] && echo "INSTALL sudo apt-get update && sudo apt-get install -y $p"
      needs node && echo "NOTE apt's node is often older than 18: install node 18+ from https://nodejs.org or with nvm (https://github.com/nvm-sh/nvm)"
    elif have dnf; then
      p=$(pk "nodejs npm" "" python3 python3-numpy); [ -n "$p" ] && echo "INSTALL sudo dnf install -y $p"
      needs ffmpeg && echo "NOTE Fedora ships ffmpeg through RPM Fusion: enable it (https://rpmfusion.org/Configuration), then: sudo dnf install -y ffmpeg"
    elif have pacman; then
      p=$(pk "nodejs npm" ffmpeg python python-numpy); [ -n "$p" ] && echo "INSTALL sudo pacman -S --needed $p"
    else
      echo "NOTE unknown package manager: install node 18+, ffmpeg, python3 and numpy with the system's own tools"
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*)
    echo "NOTE on Windows the skill's scripts run best in WSL (wsl --install, then reopen and rerun this check there)"
    echo "INSTALL winget install OpenJS.NodeJS.LTS Gyan.FFmpeg Python.Python.3.12"
    echo "INSTALL py -m pip install numpy"
    ;;
  *)
    echo "NOTE unknown system: install node 18+, ffmpeg, python3 and numpy"
    ;;
esac
exit 2
