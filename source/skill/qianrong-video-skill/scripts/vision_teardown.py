#!/usr/bin/env python3
"""
vision_teardown.py — semantic, multi-angle teardown of a promo film using a vision model.

Split of labour with teardown_video.py:
  teardown_video.py   gives the QUANTITIES  — cuts, motion, loudness, colour statistics.
  vision_teardown.py  gives the MEANING     — what a shot is doing, how it is acted, why it convinces.

They are complementary: the numbers find WHERE it is wrong, the semantics find WHAT TO DO.

Input : a directory of timestamped contact sheets from make_frame_sheets.py (with sheet_manifest.json).
Output: <out>/<film>/<pass>.json — one file per angle, plus a summary.

Usage:
    VISION_ENDPOINT=... VISION_MODEL=... VISION_API_KEY=... \
      python3 scripts/vision_teardown.py \
        --sheets sheets --out analyses --ours my-film \
        [--films a,b] [--passes structure,camera,typography,color,authenticity,transferable,improve_ours] \
        [--jobs 2]
"""
from __future__ import annotations

import argparse, base64, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Provider-agnostic: point these at any OpenAI-compatible vision endpoint.
# The recipe in references/multimodal-teardown.md was validated on a MiMo-V2.6 endpoint, but any
# multimodal model that accepts image_url content blocks works.
ENDPOINT = os.environ.get("VISION_ENDPOINT", "")
MODEL = os.environ.get("VISION_MODEL", "")
KEY = os.environ.get("VISION_API_KEY", "")


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def call(prompt: str, images: list[Path], max_tokens: int = 3000, retries: int = 3) -> str:
    content = [{"type": "text", "text": prompt}]
    for p in images:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + b64(p)}})
    body = json.dumps({"model": MODEL, "stream": True, "max_completion_tokens": max_tokens,
                       "messages": [{"role": "user", "content": content}]}).encode()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, headers={
                "Authorization": "Bearer " + KEY, "Content-Type": "application/json",
                "Accept": "text/event-stream"})
            r = urllib.request.urlopen(req, timeout=900)
            buf = []
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    d = json.loads(line)
                    for ch in d.get("choices", []):
                        c = ch.get("delta", {}).get("content") or ""
                        if c:
                            buf.append(c)
                except Exception:
                    pass
            return "".join(buf)
        except Exception as e:  # noqa: BLE001
            last = e
            msg = getattr(e, "read", lambda: b"")()
            sys.stderr.write(f"  retry {i+1}: {(msg.decode()[:160] if msg else repr(e)[:160])}\n")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"vision call failed: {last}")


PASSES = {
 "structure": (
   "{film} 是一部产品宣传片。附图为整片总览关键帧板（每格左下角有时间戳 t=…）。\n"
   "请：1) 按时间逐格说明画面主体/可辨文字/这一格的作用；2) 归纳成 3-5 幕，给出时间区间与任务；"
   "3) 一句话概括叙事弧线；4) 开场 3 秒的钩子是什么、结尾怎么收。简体中文 Markdown。"),
 "camera": (
   "{film} 的宣传片。请只从「镜头语言」分析附图：1) 运镜类型（静帧/推近/拉远/横移/旋转/手持）并举时间点；"
   "2) 构图与景别怎么变；3) 转场方式（硬切/叠化/形变匹配/匹配剪辑），找出最妙的一处并说明怎么接的；"
   "4) 画面里「一直在动」的是什么，和一张静止 5 秒的贴图差在哪。简体中文 Markdown。"),
 "typography": (
   "{film} 的宣传片。请只从「屏幕文字与信息设计」分析：1) 逐条列出能看清的文案（按时间）+字号层级；"
   "2) 文案风格是产品内部词还是用户原话、每句多长；3) 字体/对齐/留白/每屏信息量；"
   "4) 文字与画面动效的关系。简体中文 Markdown。"),
 "color": (
   "{film} 的宣传片。请只从「色彩与视觉风格」分析：1) 主/辅/背景色及十六进制近似值；2) 明度/饱和度/对比度倾向；"
   "3) 是否单色系、不同幕色彩是否变化及其叙事作用；4) 品牌色如何出现。简体中文 Markdown。"),
 "authenticity": (
   "{film} 的宣传片。请只从「真实感与技术展示」分析：1) 哪些是真实界面/录屏、哪些是插画或纯排版、比例；"
   "2) 产品能力是怎么被证明的（真数据/真操作/真结果 vs 口号）；3) 有无「假界面当真界面」迹象；"
   "4) 事实性内容（人名/机构/数字）如何出现。简体中文 Markdown。"),
 "transferable": (
   "{film} 的宣传片。综合附图回答：1) 有哪些**具体可复用手法**（越具体越好，例如「用 3 秒巨字标题当节拍器」）；"
   "2) 哪些依赖它自己的素材/预算、我们借不了；3) 若只有「代码+真实产品截图」的小团队要复现其中一幕，你选哪幕、怎么复现。简体中文 Markdown。"),
 "improve_ours": (
   "第一组图是**一线大厂参考片**（{film}）的关键帧；第二组图是**我们自己的产品宣传片**（{ours}）关键帧。\n"
   "请对比后只回答一件事：**我们的片子具体可以从这支参考片学哪些可落地的改进**。"
   "按「结构/运镜与动效/文字信息/配色/真实性/声音节奏」分点，每条给出：参考片的做法 → 我们现在的问题 → 具体怎么改。"
   "要具体到可在代码里实现的动作。简体中文 Markdown。"),
}


def run_film(film_dir: Path, ours_dir: Path | None, out_dir: Path, passes: list[str]) -> dict:
    man = json.loads((film_dir / "sheet_manifest.json").read_text(encoding="utf-8"))
    label = man["label"]
    overview = film_dir / "overview.jpg"
    fines = sorted(film_dir.glob("fine-*.jpg"))
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {"label": label, "probe": man["probe"], "passes": {}}
    for name in passes:
        outp = out_dir / f"{name}.json"
        if outp.exists():
            results["passes"][name] = "cached"
            print(f"  [{label}] {name}: cached"); continue
        prompt = PASSES[name].format(film=label)
        if name == "improve_ours" and ours_dir:
            images = [overview] + fines[:5] + [ours_dir / "overview.jpg"] + sorted(ours_dir.glob("fine-*.jpg"))[:5]
        else:
            images = [overview] + fines[:10]
        images = [p for p in images if p.exists()][:14]
        print(f"  [{label}] {name}: {len(images)} imgs ...")
        text = call(prompt, images)
        rec = {"label": label, "pass": name, "model": MODEL, "n_images": len(images), "text": text}
        outp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        results["passes"][name] = rec
        print(f"  [{label}] {name}: done ({len(text)} chars)")
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default="reference/vlm-analysis/sheets")
    ap.add_argument("--ours", default="", help="subdir of --sheets holding YOUR film")
    ap.add_argument("--out", default="analyses")
    ap.add_argument("--films", default="")
    ap.add_argument("--passes", default=",".join(PASSES))
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    if not KEY:
        print("ERROR: set VISION_ENDPOINT and VISION_MODEL (and VISION_API_KEY if required)", file=sys.stderr); return 2
    base = Path(args.sheets).resolve(); out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    ours = base / args.ours
    want = [x.strip() for x in args.films.split(",") if x.strip()]
    dirs = [d for d in sorted(base.iterdir()) if d.is_dir() and (not want or d.name in want)]
    passes = [p.strip() for p in args.passes.split(",") if p.strip()]
    summary = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_film, d, ours, out / d.name, passes): d for d in dirs}
        for f in as_completed(futs):
            d = futs[f]
            try: summary[d.name] = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [{d.name}] FAILED: {e}"); summary[d.name] = {"error": str(e)}
    (out / "summary.json").write_text(json.dumps({"model": MODEL, "films": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out/'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
