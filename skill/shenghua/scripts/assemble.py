#!/usr/bin/env python3
"""Join a long-form video's chapters into one master, with one loudness pass, merged captions and YouTube chapters.

  assemble.py <project-dir> [--out <file.mp4>]

<project-dir>/chapters.json lists the chapters in order:

  {"slug": "threads-are-not-cores",
   "chapters": [{"dir": "01-the-question", "title": "The question"}, …]}

Each chapter is a normal project: its work dir is <dir>/work and its render is <dir>/<dir>.mp4 (override either
with "work" / "video", relative to the project dir). Writes <project-dir>/<slug>.mp4 and, in <project-dir>/assembly/,
captions.srt/.vtt shifted onto the joined timeline, chapters.txt (YouTube timestamps for the description) and
credits.json merged from every chapter, so deliver.sh can take assembly/ as its work dir.
"""
import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

TARGET_LUFS = -14.0
# YouTube only turns timestamps into chapters with at least three, starting at 0:00, each 10 s or longer
YOUTUBE_MIN_CHAPTERS = 3
YOUTUBE_MIN_SECONDS = 10.0
CUE = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{3}) --> (\d+):(\d\d):(\d\d)[,.](\d{3})")


def fail(message: str, next_step: str) -> None:
    print(message)
    print(f"Next: {next_step}")
    sys.exit(1)


def load_chapters(project: Path) -> tuple[str, list[dict]]:
    manifest = project / "chapters.json"
    if not manifest.is_file():
        fail(f"No chapters.json in {project}", "write one listing each chapter's dir and title (references/long-form.md)")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"chapters.json is not valid JSON: {error}", "fix the file and re-run")
    chapters = data.get("chapters") or []
    if not chapters:
        fail("chapters.json lists no chapters", 'add {"dir": …, "title": …} entries under "chapters"')
    resolved = []
    for number, entry in enumerate(chapters, 1):
        if not entry.get("title") or not (entry.get("dir") or entry.get("video")):
            fail(f"chapter {number} needs a title and a dir", 'give every entry "dir" and "title"')
        folder = entry.get("dir", "")
        video = project / entry.get("video", f"{folder}/{Path(folder).name}.mp4")
        work = project / entry.get("work", f"{folder}/work")
        if not video.is_file():
            fail(f"chapter {number} ({entry['title']}) has no render at {video}",
                 "render it with render-chunks.sh to that path, or set its \"video\" in chapters.json")
        resolved.append({"title": entry["title"], "video": video, "work": work})
    return data.get("slug") or project.name, resolved


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_read_packets",
         "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout
    stream = json.loads(out)["streams"][0]
    rate = Fraction(stream["r_frame_rate"])
    # The video's frame count fixes where the next chapter starts; container durations drift by the AAC priming
    return {"format": (stream["codec_name"], stream["width"], stream["height"], stream["pix_fmt"], rate),
            "seconds": int(stream["nb_read_packets"]) / rate}


def describe(video_format: tuple) -> str:
    codec, width, height, pix_fmt, rate = video_format
    return f"{codec} {width}x{height} {pix_fmt} at {float(rate):g} fps"


def clock(seconds: float, sep: str) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def shift_cues(srt: str, offset: float) -> list[tuple[float, float, str]]:
    """The cues of one chapter's captions.srt, moved by offset seconds."""
    cues = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = block.splitlines()
        timing = next((i for i, line in enumerate(lines) if CUE.search(line)), None)
        if timing is None:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, CUE.search(lines[timing]).groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000 + offset
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000 + offset
        cues.append((start, end, "\n".join(lines[timing + 1:])))
    return cues


def write_captions(cues: list[tuple[float, float, str]], folder: Path) -> None:
    srt = "".join(f"{i}\n{clock(s, ',')} --> {clock(e, ',')}\n{text}\n\n" for i, (s, e, text) in enumerate(cues, 1))
    vtt = "WEBVTT\n\n" + "".join(f"{clock(s, '.')} --> {clock(e, '.')}\n{text}\n\n" for s, e, text in cues)
    (folder / "captions.srt").write_text(srt, encoding="utf-8")
    (folder / "captions.vtt").write_text(vtt, encoding="utf-8")


def youtube_stamp(seconds: float) -> str:
    whole = int(seconds)
    hours, minutes, secs = whole // 3600, whole // 60 % 60, whole % 60
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def chapter_list(titles: list[str], starts: list[float], total: float) -> tuple[str, list[str]]:
    """chapters.txt for the description, and why YouTube would not show them as chapters, if it would not."""
    text = "".join(f"{youtube_stamp(start)} {title}\n" for title, start in zip(titles, starts))
    problems = []
    if len(titles) < YOUTUBE_MIN_CHAPTERS:
        problems.append(f"YouTube needs at least {YOUTUBE_MIN_CHAPTERS} chapters, this video has {len(titles)}")
    ends = starts[1:] + [total]
    for title, start, end in zip(titles, starts, ends):
        if end - start < YOUTUBE_MIN_SECONDS:
            problems.append(f'"{title}" is {end - start:.1f}s; YouTube chapters must be at least {YOUTUBE_MIN_SECONDS:.0f}s')
    return text, problems


def stale_music(chapters: list[dict], starts: list[float]) -> list[str]:
    """Chapters whose music slice was made for a different start than the chapter now has."""
    stale = []
    for chapter, start in zip(chapters, starts):
        try:
            made_for = json.loads((chapter["work"] / "mix.json").read_text(encoding="utf-8")).get("music_offset")
        except (OSError, json.JSONDecodeError):
            continue
        # 2 ms: well under a frame, well over the 4-decimal rounding of each chapter's duration
        if made_for is not None and abs(made_for - start) > 0.002:
            stale.append(f'"{chapter["title"]}" music starts at {made_for:.2f}s but the chapter starts at {start:.2f}s')
    return stale


def merge_credits(works: list[Path]) -> list[dict]:
    merged, seen = [], set()
    for work in works:
        path = work / "credits.json"
        if not path.is_file():
            continue
        for entry in json.loads(path.read_text(encoding="utf-8")):
            if entry.get("source") not in seen:
                seen.add(entry.get("source"))
                merged.append(entry)
    return merged


def join(chapters: list[dict], lengths: list[float], scratch: Path, out: Path) -> float:
    total = float(sum(lengths))
    concat = scratch / "concat.txt"
    concat.write_text("".join("file '{}'\n".format(str(c["video"].resolve()).replace("'", r"'\''")) for c in chapters))
    # Every chapter came out of the same encoder settings, so the video joins without re-encoding
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-map", "0:v", "-c", "copy", str(scratch / "video.mp4")], check=True)
    inputs, chains = [], []
    for i, (chapter, length) in enumerate(zip(chapters, lengths)):
        inputs += ["-i", str(chapter["video"])]
        chains.append(f"[{i}:a]aresample=48000,apad,atrim=0:{float(length):.6f}[a{i}]")
    graph = ";".join(chains) + ";" + "".join(f"[a{i}]" for i in range(len(chapters))) + f"concat=n={len(chapters)}:v=0:a=1[out]"
    joined = scratch / "joined.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-c:a", "pcm_f32le", str(joined)], check=True)
    measured = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(joined), "-af",
                               "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                              capture_output=True, text=True).stderr
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", measured, re.S)
    if not match:
        fail(f"Could not measure the loudness of {joined}", "check that every chapter mp4 has an audio track")
    gain = TARGET_LUFS - float(json.loads(match.group(0))["input_i"])
    # One static gain over the whole video keeps the chapters' relative levels; 0.8414 = -1.5 dBFS ceiling
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(scratch / "video.mp4"), "-i", str(joined),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-af", f"volume={gain:.2f}dB,alimiter=limit=0.8414:level=disabled",
                    "-c:a", "aac", "-b:a", "256k", "-t", f"{total:.6f}", "-movflags", "+faststart", str(out)], check=True)
    joined.unlink()
    (scratch / "video.mp4").unlink()
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="master mp4 (default <project>/<slug>.mp4)")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    slug, chapters = load_chapters(project)
    out = (args.out or project / f"{slug}.mp4").expanduser().resolve()

    probes = [probe(c["video"]) for c in chapters]
    first = probes[0]["format"]
    for chapter, found in zip(chapters, probes):
        if found["format"] != first:
            fail(f"{chapter['video'].name} is {describe(found['format'])}; the first chapter is {describe(first)}",
                 "render every chapter with the same --format, --resolution and render-chunks.sh settings")
    lengths = [p["seconds"] for p in probes]
    starts = [float(sum(lengths[:i])) for i in range(len(lengths))]
    stale = stale_music(chapters, starts)
    if stale:
        for line in stale:
            print(f"{line}; an earlier chapter changed length")
        fail("the music would jump at those joins",
             "re-run synth_audio.py and render-chunks.sh in each chapter named above (complete video chunks are kept), then assemble again")

    scratch = project / "assembly"
    scratch.mkdir(exist_ok=True)
    total = join(chapters, lengths, scratch, out)

    cues, missing = [], []
    for chapter, start in zip(chapters, starts):
        srt = chapter["work"] / "captions.srt"
        if srt.is_file():
            cues += shift_cues(srt.read_text(encoding="utf-8"), start)
        else:
            missing.append(chapter["title"])
    if cues:
        write_captions(cues, scratch)
    text, problems = chapter_list([c["title"] for c in chapters], starts, total)
    (scratch / "chapters.txt").write_text(text, encoding="utf-8")
    credits = merge_credits([c["work"] for c in chapters])
    (scratch / "credits.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8")

    minutes, seconds = divmod(round(total), 60)
    print(f"{out.name} · {len(chapters)} chapters · {minutes}:{seconds:02d} · {TARGET_LUFS:.0f} LUFS · {len(cues)} caption cues · {len(credits)} credit(s)")
    print(text, end="")
    for title in missing:
        print(f"⚠ no captions.srt for \"{title}\"; run build_captions.py in its work dir and re-run")
    for problem in problems:
        print(f"⚠ {problem}")

    print(f"Next: bash deliver.sh \"{scratch}\" \"{out}\", then paste assembly/chapters.txt into the YouTube description")
    return 0


if __name__ == "__main__":
    sys.exit(main())
