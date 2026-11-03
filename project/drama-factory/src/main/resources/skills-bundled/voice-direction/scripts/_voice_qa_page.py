"""Listening page for voice_qa.py --screen-voices: players per probe, rank selects, static ticks, results as JSON."""
import html
import json
import random
import shutil
import string
from pathlib import Path

STYLE = """
:root{--bg:#f7f6f2;--fg:#1d1c1a;--muted:#6b6862;--line:#dcd8cf;--card:#fff;--accent:#2f5d50}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a19d94;--line:#34322d;--card:#1f1e1b;--accent:#8fc4b2}}
*{box-sizing:border-box}body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}p{color:var(--muted);margin:0 0 20px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--card)}
th,td{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}th{font-weight:600}
td.probe{font-weight:600;white-space:nowrap}audio{width:190px;display:block;margin-bottom:6px}
select,textarea,button{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{background:var(--accent);color:var(--bg);border:0;padding:8px 14px;margin-top:16px;cursor:pointer}
textarea{width:100%;min-height:120px;margin-top:12px}.meta{color:var(--muted);font-size:13px}
"""

SCRIPT = """
const voices = JSON.parse(document.body.dataset.voices);
const probes = JSON.parse(document.body.dataset.probes);
const storageKey = "voice-screen:" + document.title;
function collect() {
  const value = (name) => document.querySelector(`[name="${name}"]`);
  const rows = {};
  probes.forEach((probe, row) => { rows[probe] = {}; voices.forEach((voice) => { rows[probe][voice] = value(`r${row}-${voice}`).value || null; }); });
  const overall = {}; const staticVoices = [];
  voices.forEach((voice) => { overall[voice] = value(`overall-${voice}`).value || null; if (value(`static-${voice}`).checked) staticVoices.push(voice); });
  return { rows, overall, static: staticVoices, notes: value("notes").value };
}
function save() { try { localStorage.setItem(storageKey, JSON.stringify(collect())); } catch (error) { console.warn(error); } }
function restore() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(storageKey) || "null"); } catch (error) { console.warn(error); }
  if (!saved) return;
  const set = (name, value) => { const element = document.querySelector(`[name="${name}"]`); if (element && value) element.value = value; };
  probes.forEach((probe, row) => voices.forEach((voice) => set(`r${row}-${voice}`, saved.rows?.[probe]?.[voice])));
  voices.forEach((voice) => { set(`overall-${voice}`, saved.overall?.[voice]); document.querySelector(`[name="static-${voice}"]`).checked = (saved.static || []).includes(voice); });
  set("notes", saved.notes);
}
document.addEventListener("change", save);
document.getElementById("done").addEventListener("click", async () => {
  const output = document.getElementById("output");
  output.value = JSON.stringify(collect(), null, 2);
  try { await navigator.clipboard.writeText(output.value); document.getElementById("done").textContent = "Copied"; } catch (error) { output.select(); }
});
restore();
"""


def _rank_select(name: str, count: int) -> str:
    options = "".join(f"<option>{rank}</option>" for rank in range(1, count + 1))
    return f'<select name="{name}" aria-label="rank"><option value="">rank</option>{options}</select>'


def _cell(audio_src: str, name: str, count: int) -> str:
    return f'<td><audio controls preload="none" src="{html.escape(audio_src)}"></audio>{_rank_select(name, count)}</td>'


def render(title: str, columns: list[tuple[str, str]], probes: list[str], sources: dict[tuple[str, int], str]) -> str:
    """columns: (label, caption); sources: (label, probe index) -> relative audio path."""
    labels = [label for label, _ in columns]
    head = "".join(f"<th>{html.escape(label)}<div class='meta'>{html.escape(caption)}</div></th>" for label, caption in columns)
    rows = []
    for row, probe in enumerate(probes):
        cells = "".join(_cell(sources[(label, row + 1)], f"r{row}-{label}", len(labels)) for label in labels)
        rows.append(f"<tr><td class='probe'>{html.escape(probe)}</td>{cells}</tr>")
    overall = "".join(f"<td>{_rank_select(f'overall-{label}', len(labels))}</td>" for label in labels)
    static = "".join(f"<td><label><input type='checkbox' name='static-{label}'> static</label></td>" for label in labels)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{STYLE}</style></head>
<body data-voices='{html.escape(json.dumps(labels))}' data-probes='{html.escape(json.dumps(probes))}'><main>
<h1>{html.escape(title)}</h1><p>Rank every row (1 = best), then rank each voice overall and tick any voice with static or hiss.
Press "Copy results" and paste the JSON back.</p>
<div class="scroll"><table><thead><tr><th>probe</th>{head}</tr></thead><tbody>{''.join(rows)}
<tr><td class='probe'>overall</td>{overall}</tr><tr><td class='probe'>noise</td>{static}</tr></tbody></table></div>
<textarea name="notes" placeholder="notes"></textarea><button id="done" type="button">Copy results</button>
<textarea id="output" readonly placeholder="results JSON"></textarea></main><script>{SCRIPT}</script></body></html>
"""


def write_blind(out: Path, rows: list[dict], probes: list[str], files: dict[tuple[str, int], Path]) -> tuple[Path, Path]:
    blind_dir = out / "blind"
    if blind_dir.exists():
        shutil.rmtree(blind_dir)
    blind_dir.mkdir(parents=True)
    voices = [row for row in rows if row["verdict"] == "pass"] or rows
    shuffled = random.SystemRandom().sample(voices, len(voices))
    letters = list(string.ascii_uppercase[: len(shuffled)])
    sources: dict[tuple[str, int], str] = {}
    for letter, row in zip(letters, shuffled, strict=True):
        for probe in range(1, len(probes) + 1):
            name = f"{letter}{probe}.mp3"
            shutil.copyfile(files[(row["voice_id"], probe)], blind_dir / name)
            sources[(letter, probe)] = name
    page = blind_dir / "index.html"
    page.write_text(render("Voice listening test", [(letter, "") for letter in letters], probes, sources))
    key = out / "key.json"
    mapping = {letter: {"voice_id": row["voice_id"], "name": row["name"]} for letter, row in zip(letters, shuffled, strict=True)}
    key.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
    return page, key


def write_open(out: Path, rows: list[dict], probes: list[str], files: dict[tuple[str, int], Path]) -> Path:
    columns = [(row["voice_id"], f"{row['name']} · {row['verdict']}") for row in rows]
    sources = {(row["voice_id"], probe): files[(row["voice_id"], probe)].name for row in rows for probe in range(1, len(probes) + 1)}
    page = out / "screen.html"
    page.write_text(render("Voice screen", columns, probes, sources))
    return page
