import argparse
import json
import math
from pathlib import Path
import re
import sys
from uuid import UUID


TOKEN_FIELDS = {
    "inputTokens": "inputTokens",
    "outputTokens": "outputTokens",
    "cacheReadTokens": "cacheReadTokens",
    "cacheWriteTokens": "cacheCreationTokens",
    "thinkingTokens": "thinkingTokens",
}
CHILD_ID = re.compile(r"\b(?:session_id|task_id):\s*([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\b")


def children(settings, transcript):
    found = set(settings.get("childInclusiveTokenUsageBySessionId", {}))
    tasks = set()
    if transcript.is_file():
        with transcript.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                content = event.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Task":
                        tasks.add(block.get("id"))
                    if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in tasks:
                        text = block.get("content", "")
                        if isinstance(text, list):
                            text = "\n".join(part.get("text", "") for part in text if isinstance(part, dict))
                        if isinstance(text, str):
                            found.update(CHILD_ID.findall(text))
    return {str(UUID(child)) for child in found}


def main():
    parser = argparse.ArgumentParser(description="Aggregate a Droid session and its discovered subagents. Costs use approximate API list prices.")
    parser.add_argument("--session", help="Parent session UUID. Defaults to the newest settings file for the current directory.")
    parser.add_argument("--sessions-dir", type=Path, default=Path.home() / ".factory" / "sessions")
    parser.add_argument("--prices", type=Path, default=Path(__file__).with_name("prices.json"))
    parser.add_argument("--plan-credits", type=float, default=200_000_000)
    parser.add_argument("--out", type=Path, default=Path("usage.json"))
    args = parser.parse_args()
    if args.plan_credits <= 0 or not math.isfinite(args.plan_credits):
        parser.error("plan-credits must be positive and finite.")
    if not args.sessions_dir.is_dir():
        parser.error(f"Sessions directory not found: {args.sessions_dir}")
    paths = {}
    for path in args.sessions_dir.rglob("*.settings.json"):
        identifier = path.name.removesuffix(".settings.json")
        try:
            identifier = str(UUID(identifier))
        except ValueError:
            continue
        if identifier not in paths or path.stat().st_mtime_ns > paths[identifier].stat().st_mtime_ns:
            paths[identifier] = path
    if args.session:
        parent = str(UUID(args.session))
    else:
        slug = "-" + str(Path.cwd().resolve()).replace(":", "").replace("\\", "-").replace("/", "-")
        candidates = [path for path in paths.values() if path.parent == args.sessions_dir / slug]
        if not candidates:
            raise RuntimeError(f"No settings files for current-directory slug {slug}. Use --session.")
        parent = max(candidates, key=lambda path: path.stat().st_mtime_ns).name.removesuffix(".settings.json")
    if parent not in paths:
        raise RuntimeError(f"Session settings not found: {parent}")
    prices = json.loads(args.prices.read_text(encoding="utf-8"))
    for model, price in prices.items():
        if model.startswith("_"):
            continue
        if not isinstance(price, dict) or any(
            not isinstance(price.get(key), (int, float)) or not math.isfinite(price[key]) or price[key] < 0
            for key in ("input", "output", "cacheWrite", "cacheRead")
        ):
            raise RuntimeError(f"Invalid per-million prices for {model}.")
    queue = [parent]
    visited = set()
    sessions = []
    while queue:
        identifier = queue.pop(0)
        if identifier in visited:
            continue
        visited.add(identifier)
        path = paths.get(identifier)
        if not path:
            raise RuntimeError(f"Missing settings for discovered child {identifier}; cannot report complete totals.")
        settings = json.loads(path.read_text(encoding="utf-8"))
        usage = settings.get("tokenUsage")
        model = settings.get("model", "unknown")
        queue.extend(sorted(children(settings, path.with_name(f"{identifier}.jsonl")) - visited))
        if not isinstance(usage, dict):
            raise RuntimeError(f"Missing tokenUsage for {identifier}; cannot report complete totals.")
        counts = {}
        for output, source in TOKEN_FIELDS.items():
            value = usage.get(source, 0)
            if not isinstance(value, int) or value < 0:
                raise RuntimeError(f"Invalid {source} in session {identifier}.")
            counts[output] = value
        credits = usage.get("factoryCredits", 0)
        if not isinstance(credits, (int, float)) or not math.isfinite(credits) or credits < 0:
            raise RuntimeError(f"Invalid factoryCredits in session {identifier}.")
        price = prices.get(model)
        cost = 0
        if price is None:
            print(f"warning: unknown model {model} in {identifier}; skipping its API cost", file=sys.stderr)
        else:
            cost = (counts["inputTokens"] * price["input"] +
                    (counts["outputTokens"] + counts["thinkingTokens"]) * price["output"] +
                    counts["cacheWriteTokens"] * price["cacheWrite"] +
                    counts["cacheReadTokens"] * price["cacheRead"]) / 1_000_000
        sessions.append({"id": identifier, "model": model, **counts, "factoryCredits": credits, "cost": cost})
    totals = {field: sum(session[field] for session in sessions) for field in TOKEN_FIELDS}
    credits = sum(session["factoryCredits"] for session in sessions)
    output = {
        "subagents": len(sessions) - 1, **totals, "totalTokens": sum(totals.values()),
        "apiCostUsd": round(sum(session["cost"] for session in sessions), 6),
        "maxPlanPercent": round(credits / args.plan_credits * 100, 6),
        "approx": True, "factoryCredits": credits,
    }
    print(f"{'session':36}  {'model':20} {'input':>10} {'output':>10} {'cache read':>12} "
          f"{'cache write':>12} {'thinking':>10} {'credits':>12} {'API USD':>10}")
    for session in sessions:
        print(f"{session['id']:36}  {session['model']:20} {session['inputTokens']:10,d} "
              f"{session['outputTokens']:10,d} {session['cacheReadTokens']:12,d} "
              f"{session['cacheWriteTokens']:12,d} {session['thinkingTokens']:10,d} "
              f"{session['factoryCredits']:12,.0f} {session['cost']:10.4f}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    print(args.out.resolve())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
