#!/usr/bin/env python3
"""Trend radar for motion-studio: find videos that broke out against their creator's own normal.

A breakout is a video whose views beat the median of the same creator's recent videos. That ratio
(the outlier score) is the signal paid tools sell; this computes it from free sources.

  trends.py tiktok @user [@user ...] [--watchlist FILE] [--per-creator 30] [--stale-days 60] [--keywords a,b --min-fit 0.3]
                    [--keep @a,@b]   creators kept whatever the stale and niche filters say
  trends.py tiktok-tag scam [--videos 60] [--per-creator 20]      hashtag discovery (broken as of 2026-10: yt-dlp needs TikTok app info)
  trends.py youtube "query" [--days 14] [--max 25] [--per-creator 20]
  common: [--min-score 3] [--min-age-days 1] [--max-age-days 30] [--out DIR]

Watchlist lines: "@handle", or "@handle tiktokuser:<secUid>" (the secUid route still works when TikTok bot-checks
profile pages), "#" starts a comment.

Sources, all free:
  TikTok   yt-dlp (pip install yt-dlp); no account or cookie. Unofficial, so it breaks when TikTok
           changes its site; upgrade yt-dlp first when it does. Needs tiktok.com reachable.
  YouTube  YouTube Data API v3 with an API key (Google Cloud Console > Credentials > API key; free,
           10,000 units a day; one search costs 100). Set YT_API_KEY or save the key to
           ~/.motion-studio/youtube/api_key.

Each run writes trends-<date>-<source>.md (ranked table) and .json (every video seen) to --out.
Scores for videos younger than --min-age-days are left out: they have not had time to collect views.
Each video carries "paid": why it looks sponsored ("declared" when YouTube says it has paid placement, else the
first marker found in its caption or description: #ad, "sponsored by", "use code"...), or null. A sponsored
breakout may be paid reach, not organic demand; the report marks it.
The radar picks topics. It never downloads videos; the factory makes original episodes about them.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DAY = 86400


# ── scoring ────────────────────────────────────────────────
def score(videos, min_age_days=1.0, now=None):
    """Add 'baseline' (median views of the creator's other videos) and 'score' to each video.

    videos: dicts with creator, id, views, timestamp. The video itself is left out of its own
    baseline so one hit cannot hide itself. Creators with fewer than 3 other videos get no score."""
    now = now or time.time()
    by_creator = {}
    for v in videos:
        by_creator.setdefault(v["creator"], []).append(v)
    for vs in by_creator.values():
        for v in vs:
            others = [o["views"] for o in vs if o is not v and o.get("views") is not None]
            v["age_days"] = round((now - v["timestamp"]) / DAY, 1) if v.get("timestamp") else None
            v["baseline"] = statistics.median(others) if len(others) >= 3 else None
            young = v["age_days"] is not None and v["age_days"] < min_age_days
            v["score"] = (round(v["views"] / max(v["baseline"], 1), 1)
                          if v["baseline"] is not None and v.get("views") is not None and not young else None)
    return videos


def breakouts(videos, min_score, max_age_days=None):
    """Videos at min_score or more, ranked; with max_age_days, only those inside the window (the baseline still
    uses every video, so an old hit can't hide a creator's normal)."""
    hits = [v for v in videos if v.get("score") is not None and v["score"] >= min_score
            and (max_age_days is None or (v.get("age_days") is not None and v["age_days"] <= max_age_days))]
    return sorted(hits, key=lambda v: (-v["score"], -v["views"]))


# ── TikTok via yt-dlp ──────────────────────────────────────
def ydl():
    try:
        import yt_dlp
    except ImportError:
        raise SystemExit("needs yt-dlp: python3 -m pip install yt-dlp")
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True,
                             "skip_download": True, "extractor_retries": 3})


BOT_CHECK = ("captcha", "verify", "rehydration", "unable to extract", "bot", "access denied", "403")
FAILS = {"bot-check": 0, "other": 0}


def failure_kind(msg):
    """TikTok answers a scraping IP with its bot-check page; yt-dlp then can't find the page's data. Upgrading
    yt-dlp doesn't fix that, a different IP (a GitHub runner) or the secUid route might."""
    m = msg.lower()
    return "bot-check" if any(k in m for k in BOT_CHECK) else "other"


def tiktok_list(url, limit):
    """Flat entries from a TikTok user or tag page (or a tiktokuser:<secUid> id), newest first."""
    with ydl() as y:
        y.params["playlistend"] = limit
        try:
            info = y.extract_info(url, download=False)
        except Exception as e:  # yt-dlp raises its own error types; report and carry on with the rest
            msg = str(e).splitlines()[0][:200]
            kind = failure_kind(msg)
            FAILS[kind] += 1
            print(f"  ! [{kind}] {url}: {msg}", file=sys.stderr)
            return []
    out = []
    for e in (info or {}).get("entries") or []:
        creator = (e.get("uploader") or e.get("channel") or "").lstrip("@")
        if not creator or e.get("view_count") is None:
            continue
        out.append({"source": "tiktok", "creator": creator, "id": e.get("id"),
                    "url": e.get("url") or e.get("webpage_url"),
                    "title": (e.get("title") or e.get("description") or "").replace("\n", " ")[:160],
                    "text": e.get("description") or e.get("title") or "",     # the whole caption, hashtags included
                    "views": e["view_count"], "likes": e.get("like_count"),
                    "comments": e.get("comment_count"), "shares": e.get("repost_count"),
                    "timestamp": e.get("timestamp")})
    return out


SECUID = re.compile(r"MS4wLjABAAAA[\w-]{64}")   # yt-dlp reads tiktokuser:<id> as a secUid only in this exact shape


def handles(args):
    """[(name, urls)] from the command line and the watchlist. A line's tiktokuser:<secUid> is tried first and its
    @handle page second, so a secUid that fails costs nothing over a plain handle."""
    lines = list(args.users)
    if args.watchlist:
        lines += [l.split("#")[0].strip() for l in Path(args.watchlist).read_text().splitlines()]
    out = {}
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        sec = next((x for x in parts if x.startswith("tiktokuser:")), None)
        name = next((x.lstrip("@") for x in parts if not x.startswith("tiktokuser:")), None)
        if sec and not SECUID.fullmatch(sec.split(":", 1)[1]):
            print(f"  ! {sec[:40]}: not a secUid (MS4wLjABAAAA + 64 characters); yt-dlp would read it as a handle"
                  + (f", using @{name}" if name else ", skipped"), file=sys.stderr)
            sec = None
        urls = ([sec] if sec else []) + ([f"https://www.tiktok.com/@{name}"] if name else [])
        if urls:
            out[name or sec] = urls
    return list(out.items())


def fit_filter(videos, a):
    """Drop creators who are stale (newest video older than --stale-days) or off-niche (under --min-fit of their
    videos match --keywords in the caption or its hashtags), except those named in --keep.
    Returns (kept videos, [(creator, reason)])."""
    by = {}
    for v in videos:
        by.setdefault(v["creator"], []).append(v)
    words = [w.strip().lower() for w in (a.keywords or "").split(",") if w.strip()]
    keep = {k.strip().lstrip("@").lower() for k in (getattr(a, "keep", None) or "").split(",") if k.strip()}
    kept, dropped, now = [], [], time.time()
    for c, vs in by.items():
        if c.lower() in keep:
            kept += vs
            continue
        ts = [v["timestamp"] for v in vs if v.get("timestamp")]
        if a.stale_days and ts and (now - max(ts)) / DAY > a.stale_days:
            dropped.append((c, f"no post in {round((now - max(ts)) / DAY)} days"))
            continue
        if words:
            fit = sum(any(w in (v.get("text") or v.get("title") or "").lower() for w in words) for v in vs) / len(vs)
            if fit < a.min_fit:
                dropped.append((c, f"{fit:.0%} of videos on-niche"))
                continue
        kept += vs
    return kept, dropped


def cmd_tiktok(a):
    names = handles(a)
    if not names:
        raise SystemExit("name at least one @creator or pass --watchlist")
    videos = []
    for n, urls in names:
        for url in urls:
            got = tiktok_list(url, a.per_creator)
            if got:
                break
        print(f"  @{n}: {len(got)} videos", file=sys.stderr)
        videos += got
    if FAILS["bot-check"] and FAILS["bot-check"] >= len(names) / 2:
        print(f"  TikTok bot-checked {FAILS['bot-check']} of {len(names)} pages from this IP. Upgrading yt-dlp won't fix that: "
              "wait, run from another network (the GitHub runner workflow), or add tiktokuser:<secUid> to the watchlist.", file=sys.stderr)
    videos, dropped = fit_filter(videos, a)
    for c, why in dropped:
        print(f"  dropped @{c}: {why}", file=sys.stderr)
    return videos, "tiktok"


def cmd_tiktok_tag(a):
    tag = a.tag.lstrip("#")
    found = tiktok_list(f"https://www.tiktok.com/tag/{tag}", a.videos)
    print(f"  #{tag}: {len(found)} videos from {len({v['creator'] for v in found})} creators", file=sys.stderr)
    videos = {v["id"]: v for v in found}
    for n in sorted({v["creator"] for v in found}):
        for v in tiktok_list(f"https://www.tiktok.com/@{n}", a.per_creator):
            videos.setdefault(v["id"], v)
    keep = {v["id"] for v in found}   # rank only the tag's videos; the rest are baseline
    out = list(videos.values())
    for v in out:
        v["in_query"] = v["id"] in keep
    return out, f"tiktok-tag-{tag}"


# ── YouTube Data API ───────────────────────────────────────
def yt_key():
    key = os.environ.get("YT_API_KEY")
    f = Path.home() / ".motion-studio" / "youtube" / "api_key"
    if not key and f.exists():
        key = f.read_text().strip()
    if not key:
        raise SystemExit("needs a YouTube Data API key: set YT_API_KEY or save it to " + str(f))
    return key


QUOTA = {"search": 100}   # units per call; every other call here costs 1
used = [0]


def yt(path, **params):
    used[0] += QUOTA.get(path, 1)
    url = f"https://www.googleapis.com/youtube/v3/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-Goog-Api-Key": yt_key()})   # a header, so the key never sits in a URL or log
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"YouTube API {path} -> {e.code}: {e.read().decode()[:400]}")


PAID_PART = [True]     # videos.list part=paidProductPlacementDetails; dropped for the run if the API refuses it


def yt_videos(ids):
    out = []
    for i in range(0, len(ids), 50):
        batch = ",".join(ids[i:i + 50])
        try:
            items = yt("videos", part="snippet,statistics" + (",paidProductPlacementDetails" if PAID_PART[0] else ""), id=batch)["items"]
        except SystemExit as e:
            if not PAID_PART[0] or "-> 400" not in str(e):
                raise
            PAID_PART[0] = False
            print("  paidProductPlacementDetails refused by the API; paid flags come from descriptions only", file=sys.stderr)
            items = yt("videos", part="snippet,statistics", id=batch)["items"]
        for it in items:
            s, st = it["snippet"], it.get("statistics", {})
            declared = (it.get("paidProductPlacementDetails") or {}).get("hasPaidProductPlacement")
            out.append({"source": "youtube", "creator": s["channelTitle"], "channel_id": s["channelId"],
                        "id": it["id"], "url": f"https://www.youtube.com/watch?v={it['id']}",
                        "text": " ".join([s["title"], s.get("description", ""), " ".join("#" + t for t in s.get("tags", []))]),
                        "paid_declared": bool(declared),
                        "title": s["title"][:160], "views": int(st["viewCount"]) if "viewCount" in st else None,
                        "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                        "timestamp": datetime.fromisoformat(s["publishedAt"].replace("Z", "+00:00")).timestamp()})
    return out


def cmd_youtube(a):
    after = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hits = yt("search", part="id", q=a.query, type="video", order="viewCount",
              publishedAfter=after, maxResults=min(a.max, 50), relevanceLanguage="en")["items"]
    found = yt_videos([h["id"]["videoId"] for h in hits])
    videos = {v["id"]: v for v in found}
    for cid in sorted({v["channel_id"] for v in found}):
        uploads = "UU" + cid[2:]   # every channel's uploads playlist id
        items = yt("playlistItems", part="contentDetails", playlistId=uploads,
                   maxResults=min(a.per_creator, 50)).get("items", [])
        for v in yt_videos([i["contentDetails"]["videoId"] for i in items]):
            videos.setdefault(v["id"], v)
    keep = {v["id"] for v in found}
    out = list(videos.values())
    for v in out:
        v["in_query"] = v["id"] in keep
    print(f"  '{a.query}': {len(found)} results, {len(out) - len(found)} baseline videos "
          f"({used[0]} of 10,000 daily quota units)", file=sys.stderr)
    return out, "youtube-" + "-".join(a.query.lower().split())[:40]


# ── paid partnerships ──────────────────────────────────────
PAID = re.compile(r"(?i)(#ad\b|#ads\b|#sponsored\b|#partner\b|#partnership\b|#paidpartnership\b|#brandpartner\b"
                  r"|paid partnership|sponsored by|\bsponsor(?:ed|ing|s)?\b|in partnership with|\buse (?:my |the )?code\b"
                  r"|promo code|discount code|affiliate link)")


def paid_flag(v):
    """Why a video looks sponsored, or None: the platform's own declaration first, then a marker in its text."""
    if v.get("paid_declared"):
        return "declared"
    text = v.get("text") or v.get("title") or ""
    for m in PAID.finditer(text):
        if not re.search(r"(?i)\b(?:not|no|never|isn'?t|wasn'?t)\s+(?:\w+\s+)?$", text[max(0, m.start() - 20):m.start()]):
            return m.group(0).lower()        # "not sponsored" and "no sponsor" don't count
    return None


# ── report ─────────────────────────────────────────────────
def fmt(n):
    return "" if n is None else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def report(videos, label, a):
    score(videos, a.min_age_days)
    for v in videos:
        v["paid"] = paid_flag(v)
    ranked = breakouts([v for v in videos if v.get("in_query", True)], a.min_score, a.max_age_days)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"trends-{datetime.now():%Y-%m-%d}-{label}"
    stem.with_suffix(".json").write_text(json.dumps(videos, indent=1))
    lines = [f"# Breakouts: {label} ({datetime.now():%Y-%m-%d})", "",
             f"{len(videos)} videos from {len({v['creator'] for v in videos})} creators; "
             f"{len(ranked)} at {a.min_score}x or more of their creator's median" + (f", posted in the last {a.max_age_days:g} days" if a.max_age_days else "") + ".", "",
             "Paid: why a breakout looks sponsored (declared by YouTube, or a marker in its caption); its reach may be bought.", "",
             "| Score | Views | Creator median | Age (days) | Paid | Creator | Video |", "|---|---|---|---|---|---|---|"]
    for v in ranked:
        title = v["title"].replace("|", "/") or v["id"]
        lines.append(f"| {v['score']}x | {fmt(v['views'])} | {fmt(round(v['baseline']))} | {v['age_days']} | {v['paid'] or ''} "
                     f"| {v['creator']} | [{title}]({v['url']}) |")
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:6 + 2 + 15]))
    print(f"\nwrote {stem}.md and .json")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--min-score", type=float, default=3.0, help="breakout threshold, x creator median")
        p.add_argument("--min-age-days", type=float, default=1.0)
        p.add_argument("--max-age-days", type=float, help="rank only videos at most this old (the baseline uses all)")
        p.add_argument("--out", default="research/trends")

    p = sp.add_parser("tiktok"); p.add_argument("users", nargs="*"); p.add_argument("--watchlist")
    p.add_argument("--stale-days", type=float, default=60, help="drop creators with no post in this many days (0: keep all)")
    p.add_argument("--keywords", help="comma-separated niche words; with --min-fit, drop creators mostly off-niche")
    p.add_argument("--min-fit", type=float, default=0.3)
    p.add_argument("--keep", help="comma-separated creators kept whatever the stale and niche filters say")
    p.add_argument("--per-creator", type=int, default=30); common(p); p.set_defaults(fn=cmd_tiktok)
    p = sp.add_parser("tiktok-tag"); p.add_argument("tag"); p.add_argument("--videos", type=int, default=60)
    p.add_argument("--per-creator", type=int, default=20); common(p); p.set_defaults(fn=cmd_tiktok_tag)
    p = sp.add_parser("youtube"); p.add_argument("query"); p.add_argument("--days", type=int, default=14)
    p.add_argument("--max", type=int, default=25); p.add_argument("--per-creator", type=int, default=20)
    common(p); p.set_defaults(fn=cmd_youtube)
    a = ap.parse_args()
    videos, label = a.fn(a)
    if not videos:
        raise SystemExit("no videos came back; check the network or upgrade yt-dlp (python3 -m pip install -U yt-dlp)")
    report(videos, label, a)


if __name__ == "__main__":
    main()
