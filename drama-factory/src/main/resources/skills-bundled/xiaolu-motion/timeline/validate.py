"""Validate a storyboard (schema + anchors + component params + media) and print the report.

  python3 -m timeline.validate storyboard.json      (exit 1 on any error)
"""
import json
import sys

from .resolve import resolve


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    res, rep = resolve(sys.argv[1])
    out = rep.dump()
    if res:
        out["summary"] = {"frames": res["frames"], "shots": [(s["id"], s["component"], s["t0"], s["t1"], s["layer"], s["depth"]) for s in res["shots"]],
                          "transitions": [(t["id"], t["type"], t["t0"], t["at"], t["t1"]) for t in res["transitions"]], "sfx": len(res["sfx"])}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
