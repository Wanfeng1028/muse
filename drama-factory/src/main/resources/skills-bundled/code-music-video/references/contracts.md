# Interchange and adapter contracts

## Timeline v1

All times are finite seconds relative to the selected audio excerpt's start.
Use JSON numbers, not strings or booleans. See
[the six-second example](../examples/timeline.json).

| Field | Contract |
|---|---|
| `schema_version` | Integer `1` |
| `duration` | Positive selected-audio duration in seconds |
| `fps` | Positive integer capture rate; v1 does not represent fractional rates |
| `beats` | Strictly increasing seconds in `[0, duration)`; may be empty |
| `sections` | Nonempty `{id,start,end}` array; unique nonempty IDs; positive windows contiguous from `0` through `duration` |
| `lyrics` | Optional `{text,start,end}` array; ordered, nonoverlapping positive windows within duration; gaps allowed |
| `energy` | Optional `low`, `mid`, `high` arrays of `{t,value}`; strictly increasing `t` in `[0,duration)`, finite value in `[0,1]` |

Section endpoints must share the same stored number rather than independently
rounded near-equal values. Windows are half-open `[start,end)`. Lyrics v1 are
line-level; word timings, polyphonic overlapping lyrics, stems, onsets and
confidence remain adapter-specific sidecar data. Do not discard needed detail
to force it into this small schema. The validator checks structure and ranges,
not audio correspondence or the renderer's own native format.

## Tool capabilities

| Capability | Input → output | Acceptance / failure |
|---|---|---|
| Timing analysis | Exact audio excerpt + optional transcript → timeline and any native sidecars | Validator passes; audible anchors match. Low-confidence alignment returns review points, not invented timestamps. |
| Scene evaluation | `{t, start, end, seed, timing, width, height}` → one complete frame | Same inputs yield same frame on the tested stack; unsupported stateful seeks are declared. |
| Preview | Project + seek/play controls → view and captures | Loads actual assets; seeking and playback work; readiness includes fonts, textures and required data. |
| Offline capture | Frozen project + frame range + dimensions/sampling → ordered frames | Captures agreed pixels, no HMR, no missing/duplicate indices; browser/scene errors fail the range. |
| Encoding / inspection | Frames + approved audio + codec settings → media and metadata | Metadata and playback agree with the job; encoding success alone is insufficient. |

Record the current tool/version, available capability, exact invocation and
limits in the project brief. Inspect help/API before adapting commands; do not
infer capabilities from a product name. The Skill's scene contract is conceptual,
not a promised TypeScript ABI.

### Execution bounds

Before a costly operation, state its output path, expected resources and a
bounded wait. Choose the timeout from a representative render measurement;
there is no universal full-MV timeout. On timeout, report the last completed
frame/range and retain logs/outputs. Re-run only failed or demonstrably incomplete
work once the cause is addressed; do not loop blind installs or captures.

Network/model downloads, new dependency installs and external uploads require
the permissions applicable to the current request. Missing binaries, unsupported
features, invalid inputs, unready resources and capture/encode failures remain
distinct errors. A permitted fallback can be manual timing, line-level lyrics,
a simpler scene or smaller test output; changing final specifications needs
agreement. No adapter promises visual quality, cross-GPU pixel identity or
real-time 4K performance merely by connecting.

## Frame and segment accounting

For this package's v1 convention, full-track capture uses `N = ceil(duration *
fps)` frames with `t_i = i / fps`, `0 <= i < N`. Video therefore lasts `N/fps`;
pad/trim audio to that boundary deliberately, at most one frame beyond the
selected duration. If an existing engine uses a different convention, document
and inspect it instead of silently assuming this one.

Describe segments using integer half-open ranges `[i0,i1)`. They must partition
`[0,N)` exactly; convert to seconds only at an adapter boundary. Sub-frame times
may straddle a cut: evaluate the correct active scene for each sample, or use
the renderer's documented cut-safe sampling policy. Keep preview and export
sampling/color settings aligned for comparisons.

Only stream-copy segments with matching codec, dimensions, frame rate, pixel
format and stream layout. Check the joined timestamps and play every join.
Re-encode when those conditions do not hold. `ffprobe` verifies container/stream
metadata; audio-backed playback and frame inspection verify sync and content.
