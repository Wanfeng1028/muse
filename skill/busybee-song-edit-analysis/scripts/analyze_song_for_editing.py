#!/usr/bin/env python3
import argparse
import json
import math
import re
from pathlib import Path

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.ndimage import median_filter
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


def fmt_time(seconds):
    minutes = int(seconds // 60)
    secs = seconds - 60 * minutes
    return f"{minutes}:{secs:05.2f}"


def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value or "song"


def z01(x):
    x = np.asarray(x, dtype=float)
    lo = np.nanpercentile(x, 5)
    hi = np.nanpercentile(x, 95)
    if hi <= lo:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def nearest_index(values, target):
    values = np.asarray(values)
    return int(np.argmin(np.abs(values - target)))


def label_energy(score):
    if score >= 0.78:
        return "peak"
    if score >= 0.60:
        return "high"
    if score >= 0.42:
        return "medium"
    if score >= 0.24:
        return "low"
    return "very low"


def footage_fit(energy, bass, brightness, transient):
    if energy >= 0.78:
        if bass >= 0.65:
            return "fast, heavy, impact-heavy shots; action hits, reveals, collisions, camera whips"
        return "fast bright shots; flashes, crowds, quick motion, kinetic B-roll"
    if energy >= 0.60:
        return "active movement; short 1-2 beat clips, push-ins, gestures, cuts on snares/fills"
    if energy >= 0.42:
        return "medium motion; 2-4 beat clips, character beats, context shots, rhythmic pans"
    if energy >= 0.24:
        return "slow setup footage; 4-8 beat clips, establishing shots, anticipation, detail shots"
    return "quiet visuals; holds, titles, atmosphere, breath before the next hit"


def cut_strategy(energy, transient):
    if energy >= 0.78 or transient >= 0.72:
        return "cut every 1/2-1 beat, with hard cuts on strong onsets"
    if energy >= 0.60:
        return "cut every 1-2 beats; use the strongest beat in each bar for accents"
    if energy >= 0.42:
        return "cut every 2-4 beats; reserve fast cuts for fills"
    return "hold 4-8 beats; use cuts to mark phrase boundaries"


def describe_section(row):
    pieces = []
    pieces.append(f"{row.energy_label} energy")
    if row.bass_norm >= 0.65:
        pieces.append("bass-heavy")
    elif row.bass_norm <= 0.30:
        pieces.append("light low end")
    if row.brightness_norm >= 0.65:
        pieces.append("bright/top-end forward")
    elif row.brightness_norm <= 0.30:
        pieces.append("dark/muted")
    if row.transient_norm >= 0.65:
        pieces.append("transient/choppy")
    elif row.transient_norm <= 0.30:
        pieces.append("smooth")
    return ", ".join(pieces)


def safe_kmeans_labels(features, max_k=7):
    n = len(features)
    if n < 8:
        return np.zeros(n, dtype=int)
    best = None
    for k in range(2, min(max_k, n - 1) + 1):
        model = KMeans(n_clusters=k, random_state=8, n_init=20)
        labels = model.fit_predict(features)
        try:
            score = silhouette_score(features, labels)
        except Exception:
            score = -1
        if best is None or score > best[0]:
            best = (score, labels)
    return best[1] if best else np.zeros(n, dtype=int)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sr", type=int, default=44100)
    args = parser.parse_args()

    audio_path = Path(args.audio)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = slugify(audio_path.stem)

    y, sr = librosa.load(audio_path, sr=args.sr, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    hop = 512

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop, trim=False)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    if len(beat_times) < 8:
        raise RuntimeError("Beat tracker found too few beats for reliable editing analysis.")

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop)
    onset_norm = z01(onset_env)

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=hop)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)

    stft = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=4096)
    low = stft[(freqs >= 20) & (freqs < 160)].mean(axis=0)
    mid = stft[(freqs >= 160) & (freqs < 2500)].mean(axis=0)
    high = stft[(freqs >= 2500) & (freqs < 12000)].mean(axis=0)

    frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    def beat_mean(feature):
        vals = []
        for i, t in enumerate(beat_times):
            end = beat_times[i + 1] if i + 1 < len(beat_times) else min(duration, t + (60 / tempo))
            mask = (frame_times >= t) & (frame_times < end)
            vals.append(float(np.mean(feature[mask])) if np.any(mask) else float(feature[nearest_index(frame_times, t)]))
        return np.array(vals)

    beat_rms = beat_mean(rms)
    beat_low = beat_mean(low[: len(frame_times)])
    beat_mid = beat_mean(mid[: len(frame_times)])
    beat_high = beat_mean(high[: len(frame_times)])
    beat_centroid = beat_mean(centroid)
    beat_onset = np.array([
        float(np.max(onset_norm[(onset_times >= t) & (onset_times < (beat_times[i + 1] if i + 1 < len(beat_times) else t + 60 / tempo))]))
        if np.any((onset_times >= t) & (onset_times < (beat_times[i + 1] if i + 1 < len(beat_times) else t + 60 / tempo)))
        else 0.0
        for i, t in enumerate(beat_times)
    ])

    energy = 0.45 * z01(beat_rms) + 0.25 * z01(beat_low) + 0.15 * z01(beat_high) + 0.15 * z01(beat_onset)
    energy_smooth = median_filter(energy, size=5)
    beat_period = 60 / tempo

    beats = pd.DataFrame({
        "beat": np.arange(1, len(beat_times) + 1),
        "time_sec": beat_times,
        "time": [fmt_time(t) for t in beat_times],
        "bar_est": ((np.arange(len(beat_times)) // 4) + 1),
        "beat_in_bar_est": ((np.arange(len(beat_times)) % 4) + 1),
        "energy": energy,
        "energy_smooth": energy_smooth,
        "energy_label": [label_energy(v) for v in energy_smooth],
        "bass_norm": z01(beat_low),
        "mid_norm": z01(beat_mid),
        "high_norm": z01(beat_high),
        "brightness_norm": z01(beat_centroid),
        "transient_norm": z01(beat_onset),
    })
    beats["cut_priority"] = (
        0.40 * beats["transient_norm"]
        + 0.25 * beats["energy"]
        + 0.20 * (beats["beat_in_bar_est"] == 1).astype(float)
        + 0.15 * beats["bass_norm"]
    )
    beats["recommended_cut"] = beats["cut_priority"].apply(lambda v: "primary" if v >= 0.74 else ("secondary" if v >= 0.55 else "hold"))

    beat_features = []
    for i, t in enumerate(beat_times):
        frame_idx = nearest_index(frame_times, t)
        vals = [
            energy_smooth[i],
            z01(beat_low)[i],
            z01(beat_high)[i],
            z01(beat_centroid)[i],
            z01(beat_onset)[i],
        ]
        vals.extend(chroma[:, min(frame_idx, chroma.shape[1] - 1)].tolist())
        vals.extend(mfcc[:6, min(frame_idx, mfcc.shape[1] - 1)].tolist())
        vals.extend(contrast[:, min(frame_idx, contrast.shape[1] - 1)].tolist())
        beat_features.append(vals)
    scaled = StandardScaler().fit_transform(np.asarray(beat_features))
    cluster_labels = safe_kmeans_labels(scaled)
    cluster_labels = median_filter(cluster_labels, size=5)

    changes = [0]
    for i in range(1, len(cluster_labels)):
        if cluster_labels[i] != cluster_labels[i - 1]:
            min_gap = 4
            if i - changes[-1] >= min_gap:
                changes.append(i)
    if len(beat_times) - changes[-1] < 4 and len(changes) > 1:
        changes.pop()
    changes.append(len(beat_times))

    section_rows = []
    for si in range(len(changes) - 1):
        a, b = changes[si], changes[si + 1]
        seg = beats.iloc[a:b]
        start = float(seg.time_sec.iloc[0])
        end = float(beat_times[b]) if b < len(beat_times) else duration
        row = {
            "section": si + 1,
            "start_sec": start,
            "end_sec": end,
            "start": fmt_time(start),
            "end": fmt_time(end),
            "beats": int(b - a),
            "bars_est": round((b - a) / 4, 2),
            "avg_energy": float(seg.energy_smooth.mean()),
            "peak_energy": float(seg.energy_smooth.max()),
            "energy_label": label_energy(float(seg.energy_smooth.mean())),
            "bass_norm": float(seg.bass_norm.mean()),
            "brightness_norm": float(seg.brightness_norm.mean()),
            "transient_norm": float(seg.transient_norm.mean()),
            "primary_cuts": int((seg.recommended_cut == "primary").sum()),
            "secondary_cuts": int((seg.recommended_cut == "secondary").sum()),
        }
        section_rows.append(row)
    sections = pd.DataFrame(section_rows)
    sections["character"] = sections.apply(describe_section, axis=1)
    sections["footage_fit"] = sections.apply(lambda r: footage_fit(r.avg_energy, r.bass_norm, r.brightness_norm, r.transient_norm), axis=1)
    sections["cut_strategy"] = sections.apply(lambda r: cut_strategy(r.avg_energy, r.transient_norm), axis=1)

    phrase_rows = []
    phrase_len = 8
    for a in range(0, len(beats), phrase_len):
        b = min(a + phrase_len, len(beats))
        seg = beats.iloc[a:b]
        if len(seg) < 2:
            continue
        phrase_rows.append({
            "phrase": len(phrase_rows) + 1,
            "start_sec": float(seg.time_sec.iloc[0]),
            "end_sec": float(beat_times[b]) if b < len(beat_times) else duration,
            "start": fmt_time(float(seg.time_sec.iloc[0])),
            "end": fmt_time(float(beat_times[b]) if b < len(beat_times) else duration),
            "beats": int(len(seg)),
            "avg_energy": float(seg.energy_smooth.mean()),
            "energy_label": label_energy(float(seg.energy_smooth.mean())),
            "primary_cut_times": "; ".join(seg.loc[seg.recommended_cut == "primary", "time"].head(8).tolist()),
            "editing_note": cut_strategy(float(seg.energy_smooth.mean()), float(seg.transient_norm.mean())),
        })
    phrases = pd.DataFrame(phrase_rows)

    beats.to_csv(out_dir / f"{prefix}_beats.csv", index=False)
    sections.to_csv(out_dir / f"{prefix}_sections.csv", index=False)
    phrases.to_csv(out_dir / f"{prefix}_phrases.csv", index=False)

    def tc_30(sec):
        frames = round(float(sec) * 30)
        h = frames // (3600 * 30)
        frames %= 3600 * 30
        m = frames // (60 * 30)
        frames %= 60 * 30
        s = frames // 30
        f = frames % 30
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

    markers = beats[beats.recommended_cut != "hold"].copy()
    markers["timecode_30fps"] = markers.time_sec.apply(tc_30)
    markers["marker_name"] = markers.recommended_cut.str.title() + " cut - beat " + markers.beat.astype(str)
    markers["note"] = (
        "bar " + markers.bar_est.astype(str)
        + ", beat " + markers.beat_in_bar_est.astype(str)
        + ", " + markers.energy_label
        + ", energy " + markers.energy_smooth.round(2).astype(str)
    )
    markers[[
        "time_sec", "time", "timecode_30fps", "marker_name", "recommended_cut",
        "bar_est", "beat_in_bar_est", "energy_label", "energy_smooth", "cut_priority", "note"
    ]].to_csv(out_dir / f"{prefix}_cut_markers_30fps.csv", index=False)

    primary = beats[beats.recommended_cut == "primary"].copy()
    secondary = beats[beats.recommended_cut == "secondary"].copy()
    top_cuts = beats.sort_values("cut_priority", ascending=False).head(40).sort_values("time_sec")

    fig, axes = plt.subplots(4, 1, figsize=(16, 10), sharex=True)
    librosa.display.waveshow(y, sr=sr, ax=axes[0], alpha=0.65)
    axes[0].set_title("Waveform")
    axes[1].plot(beats.time_sec, beats.energy_smooth, color="#d62728", label="energy")
    axes[1].scatter(primary.time_sec, primary.energy_smooth, color="black", s=18, label="primary cuts")
    axes[1].scatter(secondary.time_sec, secondary.energy_smooth, color="#777", s=8, label="secondary cuts")
    axes[1].legend(loc="upper right")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_title("Beat-synced energy and cut priority")
    axes[2].plot(beats.time_sec, beats.bass_norm, label="bass", color="#1f77b4")
    axes[2].plot(beats.time_sec, beats.brightness_norm, label="brightness", color="#ff7f0e")
    axes[2].plot(beats.time_sec, beats.transient_norm, label="transients", color="#2ca02c")
    axes[2].legend(loc="upper right")
    axes[2].set_ylim(0, 1.05)
    axes[2].set_title("Footage matching cues")
    axes[3].step(beats.time_sec, cluster_labels, where="post", color="#9467bd")
    for _, row in sections.iterrows():
        for ax in axes:
            ax.axvspan(row.start_sec, row.end_sec, alpha=0.055, color="black")
        axes[3].text(row.start_sec + 0.25, max(cluster_labels) + 0.1, f"S{int(row.section)}", fontsize=9)
    axes[3].set_title("Detected structural sections")
    axes[3].set_xlabel("Time (seconds)")
    fig.tight_layout()
    fig.savefig(out_dir / f"{prefix}_energy_timeline.png", dpi=180)
    plt.close(fig)

    guide_lines = []
    guide_lines.append(f"# {audio_path.stem} Editing Analysis")
    guide_lines.append("")
    guide_lines.append(f"Audio: `{audio_path.name}`")
    guide_lines.append(f"Duration: {fmt_time(duration)} ({duration:.2f}s)")
    guide_lines.append(f"Estimated tempo: {tempo:.2f} BPM")
    guide_lines.append(f"Estimated beat length: {beat_period:.3f}s")
    guide_lines.append("")
    guide_lines.append("## How To Cut This Track")
    guide_lines.append("")
    guide_lines.append("- Use the beat grid as the main edit clock, but treat the first beat of each estimated 4-beat bar as the safest place for strong scene changes.")
    guide_lines.append("- Primary cut points are beats with strong onset/energy/bass weight. Use these for hard cuts, impact cuts, major motion changes, title hits, or camera direction changes.")
    guide_lines.append("- Secondary cut points are good for B-roll swaps, angle changes, speed ramps, and less obvious rhythmic edits.")
    guide_lines.append("- Low-energy sections should breathe with longer holds; high-energy sections can tolerate shorter clips and more aggressive cuts.")
    guide_lines.append("")
    guide_lines.append("## Section Map")
    guide_lines.append("")
    for _, row in sections.iterrows():
        guide_lines.append(
            f"- S{int(row.section)} {row.start}-{row.end} ({int(row.beats)} beats / ~{row.bars_est} bars): "
            f"{row.character}. Footage: {row.footage_fit}. Edit: {row.cut_strategy}."
        )
    guide_lines.append("")
    guide_lines.append("## Best Cut Points")
    guide_lines.append("")
    guide_lines.append(", ".join(top_cuts.time.tolist()))
    guide_lines.append("")
    guide_lines.append("## Phrase-Level Notes")
    guide_lines.append("")
    for _, row in phrases.iterrows():
        primary_text = row.primary_cut_times if row.primary_cut_times else "none"
        guide_lines.append(
            f"- P{int(row.phrase)} {row.start}-{row.end}: {row.energy_label} energy. "
            f"{row.editing_note}. Primary cuts: {primary_text}."
        )
    guide_lines.append("")
    guide_lines.append("## Output Files")
    guide_lines.append("")
    guide_lines.append(f"- `{prefix}_beats.csv`: every detected beat with energy and cut priority.")
    guide_lines.append(f"- `{prefix}_cut_markers_30fps.csv`: primary and secondary edit points with 30fps timecode.")
    guide_lines.append(f"- `{prefix}_agent_footage_brief.json`: structured instructions for an editing agent to select footage.")
    guide_lines.append(f"- `{prefix}_sections.csv`: structural sections with footage-fit guidance.")
    guide_lines.append(f"- `{prefix}_phrases.csv`: 8-beat phrase map.")
    guide_lines.append(f"- `{prefix}_energy_timeline.png`: waveform, energy, footage cues, and sections.")
    guide_lines.append(f"- `{prefix}_analysis.json`: machine-readable summary.")
    (out_dir / f"{prefix}_editing_guide.md").write_text("\n".join(guide_lines), encoding="utf-8")

    macro_sections = []
    for _, row in sections.iterrows():
        level = {"very low": 1, "low": 2, "medium": 3, "high": 4, "peak": 5}[row.energy_label]
        if level <= 1:
            types = ["atmosphere", "setup"]
            clip_len = "4-8"
            density = "very_low"
        elif level == 2:
            types = ["setup", "medium_action"]
            clip_len = "4"
            density = "low"
        elif level == 3:
            types = ["medium_action", "high_action"]
            clip_len = "2-4"
            density = "medium"
        elif level == 4:
            types = ["high_action", "peak_impact"]
            clip_len = "1-2"
            density = "high"
        else:
            types = ["peak_impact"]
            clip_len = "0.5-1"
            density = "maximum"
        macro_sections.append({
            "id": f"S{int(row.section)}",
            "start_sec": round(float(row.start_sec), 2),
            "end_sec": round(float(row.end_sec), 2),
            "energy_level": level,
            "energy_label": row.energy_label,
            "clip_length_beats": clip_len,
            "cut_density": density,
            "footage_types": types,
            "character": row.character,
            "selection_instruction": row.footage_fit,
            "transition_instruction": row.cut_strategy,
        })

    agent_brief = {
        "track": audio_path.name,
        "duration_sec": round(duration, 2),
        "tempo_bpm": round(tempo, 2),
        "beat_length_sec": round(beat_period, 3),
        "purpose": "Guide an editing agent or human editor in choosing footage that matches musical energy, rhythm density, and section function.",
        "global_rules": {
            "primary_cut_points": "Use for hard cuts, major subject changes, action impacts, reveals, speed-ramp landings, title hits, or camera direction changes.",
            "secondary_cut_points": "Use for angle changes, B-roll swaps, movement continuation, speed-ramp starts, or smaller rhythmic changes.",
            "bar_estimates": "Bar labels are estimated from the detected beat grid; verify downbeat by ear or waveform before final lock.",
        },
        "footage_taxonomy": {
            "atmosphere": "Establishing shots, scenic context, empty spaces, title backgrounds, slow pans, environmental detail.",
            "setup": "Preparation, anticipation, character/context introduction, slow movement, pre-action.",
            "medium_action": "Clear motion without maximum intensity: gestures, reactions, movement, gameplay/context, rhythmic B-roll.",
            "high_action": "Fast motion, action hits, strong gestures, quick camera movement, energetic B-roll, visible impact.",
            "peak_impact": "Most intense moments: collisions, reveals, eliminations, explosive motion, fast whips, crowd peaks, VFX hits, dramatic closeups.",
        },
        "sections": macro_sections,
        "strong_primary_cut_points": top_cuts.time.tolist(),
        "agent_selection_algorithm": [
            "Assign every candidate footage clip a motion_intensity from 1-5 and a content_type from the footage_taxonomy.",
            "For each music section, choose clips whose motion_intensity is within plus/minus 1 of the section energy_level.",
            "Reserve motion_intensity 5 or peak_impact clips for peak sections unless there is an explicit creative reason.",
            "Place clip boundaries on primary cut points for section starts, subject changes, impacts, and reveals.",
            "Use secondary cut points for angle changes or continuation cuts.",
            "If footage lacks enough high-intensity clips, use speed ramps, tighter crops, or shorter durations in high/peak sections rather than moving quiet footage into the peak.",
            "Prefer narrative escalation until the highest-energy section, then resolve.",
        ],
    }
    (out_dir / f"{prefix}_agent_footage_brief.json").write_text(json.dumps(agent_brief, indent=2), encoding="utf-8")

    payload = {
        "audio": str(audio_path),
        "duration_sec": duration,
        "tempo_bpm": tempo,
        "beat_length_sec": beat_period,
        "beat_count": int(len(beats)),
        "section_count": int(len(sections)),
        "sections": sections.to_dict(orient="records"),
        "top_cut_points": top_cuts[["beat", "time_sec", "time", "bar_est", "beat_in_bar_est", "cut_priority", "energy_label"]].to_dict(orient="records"),
    }
    (out_dir / f"{prefix}_analysis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps({
        "duration_sec": duration,
        "tempo_bpm": tempo,
        "beats": len(beats),
        "sections": len(sections),
        "outputs": [str(p) for p in sorted(out_dir.glob(f"{prefix}_*"))],
    }, indent=2))


if __name__ == "__main__":
    main()
