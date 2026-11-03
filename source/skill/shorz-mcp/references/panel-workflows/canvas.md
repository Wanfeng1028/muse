# Canvas workflow (`canvas_build`, `canvas_remove`, `canvas_run`, `canvas_stop`, `canvas_pick_take`, `canvas_duplicate`, `canvas_rename`, `canvas_delete`)

Build and run a **Canvas** graph — the node-graph video builder behind the header **⋮ → Canvas** — end to end over MCP. Each node does one job (write, make an image, animate a clip, voice a script, compose music, cut the timeline); wires carry the results from node to node; the **Export** node holds the finished video. An agent describes the graph as JSON, Shorz draws it on screen, and `canvas_run` runs only the nodes that are out of date and returns the finished file's path. Canvases are **not projects**: no `projectType`, no `create_project`, no Create Video. Global rules (Shorz running, bridge connected): **`../../SKILL.md`**.

## What it looks like

- `canvas_build` and `canvas_run` open Canvas full-screen in the Shorz window on the graph they act on, so the user watches the nodes appear and run (running nodes show their progress, the wires into them animate, results land inside each node). `canvas_list`, `canvas_get`, `canvas_stop`, `canvas_pick_take`, `canvas_duplicate`, `canvas_rename` and `canvas_delete` never bring Canvas on screen.
- Canvases save automatically to `<Shorz data folder>/Canvas/<id>.json`. Generated media goes to the usual generation folders (so it also shows in My Assets); Timeline renders go to `Canvas/renders`.
- The user can keep editing while an agent works — it is the same graph.

## Tool contract

| Tool | What it does | Cost |
|------|--------------|------|
| **`canvas_list`** | Every canvas: `{ id, name, updatedAt, nodeCount }`, newest first. | Free |
| **`canvas_get`** `{ canvasId, raw? }` | One canvas without opening it: nodes (`id, type, title, params, status?, error?, result?, ranAt?, credits?, takes?, takeList?` — `takeList` is `[{ take, id, active, ranAt, files }]`, oldest first, when a node has more than one take), edges in the `{ from, fromPort, to, toPort }` shape, `exports` (what each Export node holds) and `outputPath`. `raw: true` returns the whole saved file. | Free |
| **`canvas_build`** `{ canvasId?, name?, nodes?, edges?, updates? }` | Creates a canvas (no `canvasId`) or adds to one; `updates` changes params/titles of nodes already on it. Opens Canvas on it. Returns `added`, `wiresAdded`, `updated`, `warnings` and `runAll: { nodesToRun, estimatedCredits }`. | Free |
| **`canvas_remove`** `{ canvasId, nodes?, edges? }` | Deletes nodes (with all their wires) and wires (`{ from, to, fromPort?, toPort? }` — without ports, every wire from → to), like pressing Delete on the canvas. Strict and all-or-nothing; refused while that canvas runs. Generated files stay on disk and Ctrl+Z in Canvas brings them back; the removed node's takes leave the canvas. | Free |
| **`canvas_run`** `{ canvasId, targets?, force?, maxCredits?, estimateOnly?, awaitCompletion? }` | Runs the out-of-date nodes (async job) and returns the Export node's `outputPath`. Refuses to spend until you pass `maxCredits` ≥ the estimate. | The estimate |
| **`canvas_stop`** `{ canvasId? }` | Stops the running canvas, like the Stop button: no new node starts, generations already sent finish and are kept, and the `canvas_run` job ends with `stopped: true`. Returns `{ wasRunning }` at once. Only the open canvas can be running. | Free |
| **`canvas_pick_take`** `{ canvasId, nodeId, take }` | Chooses which take of a node is used, like the ‹ › take arrows: `take` is a number (1 = oldest, as the node shows "take 2/3") or a take id from `takeList`. Returns the picked take's `result`, `outOfDate` (downstream nodes the next `canvas_run` re-runs — never the picked node) and the new `exports` / `outputPath`. | Free |
| **`canvas_duplicate`** `{ canvasId, name? }` | Copies a canvas — nodes, wires, params and every take — as a new canvas (default name "… (copy)"), not opened. Copying the open canvas saves it first, so the copy has the latest edits. Branch before a risky change: the copy reuses every paid result. | Free |
| **`canvas_rename`** `{ canvasId, name }` | Renames a canvas, open or not. Returns `{ name, previousName }`. | Free |
| **`canvas_delete`** `{ canvasId }` | Only when the user asked. Moves the canvas file to `Canvas/.trash` (recoverable by hand); its generated media stays on disk and in My Assets. Deleting the open canvas switches Canvas to another one (`nowOpen`); a running canvas is refused — `canvas_stop` it first. | Free |
| **`get_job_status`** `{ jobId }` | Poll a started `canvas_run` until `lastStatus` is `completed` or `error`. | Free |

## Graph format

Same JSON shape as the in-app **Build with AI**, plus `updates`:

```json
{
  "name": "Mars in 30 seconds",
  "nodes": [{ "id": "brief", "type": "text", "title": "Brief", "params": { "text": "..." } }],
  "edges": [{ "from": "brief", "fromPort": "text", "to": "scenes", "toPort": "context" }],
  "updates": [{ "id": "music", "params": { "prompt": "calm piano" } }],
  "remove": { "nodes": ["oldNode"], "edges": [{ "from": "stills", "to": "cut", "toPort": "clips" }] }
}
```

- **Ids are yours and they stick**: 1–40 letters, digits, `_` or `-`, unique on the canvas. `canvas_run` `targets`/`force` and later `updates` use them. A wire may also run from or into a node already on the canvas by its id (from `canvas_get`).
- **`fromPort` / `toPort`** may be left out only when exactly one port fits; otherwise the error lists the ports.
- **`params`**: only the keys the node type has (table below); anything left out keeps its default. Unknown keys are ignored with a warning.
- **Strict, all-or-nothing validation**: an unknown type, a port that does not exist or does not fit, a second wire into a single input, a loop, a wrong value type or choice, a media path that is not absolute or not on disk → `{ success: false, errors: [...] }` and **nothing changes**. Fix every listed error and send the whole request again.
- **`remove`** is applied before anything is added, so a rewire is one call: remove the old wire into a single input and add the new one. A removed node's id can be reused by a new node in the same call.
- **Warnings** (graph still built): an unwired required input (it will not run until wired), an empty Text node, a Media node without files, a Voiceover without a voice.

## Lists: how one graph makes a whole video

Everything on a wire is a **list**. A `[per-item]` input runs its node once per item: an **AI Writer** in `mode: "list"` with `count: 6` emits 6 scene prompts; wired into **Image** `prompt` that is 6 images; wired on into **Video** `image` it is 6 clips. Several `[per-item]` inputs zip by index; a single item is reused for every run. `[many]` inputs take several wires and read their sources top to bottom (canvas layout order). The **Timeline** stitches its clips in order and lays voice and music under them.

## Node types

| type | Inputs | Outputs | params (defaults) | Cost |
|------|--------|---------|-------------------|------|
| `text` | — | `text` | `text: ""`, `asList: false` (true → one item per line) | Free |
| `media` | — | `image`, `video`, `audio` | `files: []` — absolute paths of local images, clips, audio | Free |
| `writer` | `context` (text, many) | `text` | `instruction: ""`, `mode: "single"` \| `"list"`, `count: 5` (≤ 20), `model: ""` (a `list_main_ai_models` id; empty = default) | Credits (LLM) |
| `image` | `prompt` (text, per-item), `refs` (image, many) | `image` | `prompt: ""`, `model: "nano-banana"`, `aspectRatio: "9:16"` \| `"16:9"` \| `"1:1"`, `variants: 1` (1–4) | Credits per image; refs switch Nano to Pro Edit (~26 cr) |
| `video` | `prompt` (text, per-item), `image` (image, per-item — start frame) | `video` | `prompt: ""`, `model: ""` (empty = default), `duration: 5`, `aspectRatio: "9:16"` \| `"16:9"`, `sound: false` | Credits per second — the expensive node |
| `voice` | `text` (text, per-item) | `audio` | `text: ""`, `voiceId: ""` (from `list_elevenlabs_voices`; default = first voice), `voiceName: ""` | Credits per character |
| `music` | `prompt` (text) | `audio` | `prompt: ""`, `durationSec: 30` (10–300) | Credits |
| `sfx` | `prompt` (text, per-item) | `audio` | `prompt: ""`, `durationSec: 3` (0.5–22) | Credits |
| `lastFrame` | `video` (video, per-item, required) | `image` | — | Free |
| `sequence` (Timeline) | `clips` (video \| image, many, required), `voice` (audio, many), `music` (audio) | `video` | `aspectRatio: "9:16"` \| `"16:9"` \| `"1:1"`, `imageSec: 3`, `fitToVoice: true`, `musicVolume: 0.25`, `voiceVolume: 1`, `clipAudio: false`, `fit: "cover"` \| `"contain"` | Free (renders locally) |
| `output` (Export) | `media` (video \| image \| audio, many, required) | — | — | Free |
| `note` | — | — | `text: ""` | Free, never runs |

Model ids come from the server catalog — never hard-code a list; leave `model` empty for the default.

## Credits and the cache

- A node's result is **current** when its params and the items wired into it are unchanged since that result was made. `canvas_run` executes only nodes that are missing a result or out of date, plus what depends on them. Change the music prompt and re-run: Music and the Timeline run again, every paid image and clip is reused.
- **Spending is two-step.** When the plan costs credits, `canvas_run` without `maxCredits` (or with `estimateOnly: true`) runs **nothing** and returns `willRun: [{ id, type, title, runs, estimatedCredits, paid, missingInputs? }]`, `estimatedCredits`, `creditBalance`, `signedIn`. Show the user the total (and the per-node lines when it is large), get a yes, then call again with `maxCredits` ≥ the estimate. If the graph changed in between and the estimate rose above `maxCredits`, the run refuses and nothing is charged.
- Plans that cost nothing (Text, Media, Last Frame, Timeline, Export) start without `maxCredits`.
- `force: [id]` makes a new take of an up-to-date node (charged again); earlier takes are kept in the node.
- AI nodes need a signed-in Shorz account with credits (`get_shorz_credits`; sign in with `shorz_sign_in_send_code`).

## Execution sequence

1. **Pick the canvas.** `canvas_list`; reuse one the user names, else build a new one (omit `canvasId`).
2. **Build.** `canvas_build` with the whole graph. On `success: false`, fix every entry in `errors` and resend. Read `warnings` and `runAll.estimatedCredits`.
3. **Estimate.** `canvas_run { canvasId }` (or `estimateOnly: true`). Up to date → `upToDate: true` with `outputPath`, nothing charged. Needs approval → show `estimatedCredits` to the user and wait for a clear yes.
4. **Run.** `canvas_run { canvasId, maxCredits }` → `{ started, jobId }`. Poll `get_job_status` every ~15–30 s (video nodes take minutes). Never re-call `canvas_run` because polling is slow — the run is still going and a second call would be refused anyway while it is busy.
5. **Read the result.** `result.outputPath` is the finished file (first video of the Export nodes); `result.exports` lists every Export item; `ran`, `failed: [{ id, error }]`, `partial` (nodes where some list items failed), `stopped` (the user pressed Stop).
6. **Iterate.** `canvas_build { canvasId, updates: [...] }` → `canvas_run` again: only the changed nodes and their dependents run.
   - **Compare takes:** `force: [nodeId]` makes another take; `canvas_get` lists them (`takeList`); `canvas_pick_take` puts the one the user prefers back in use, then `canvas_run` re-runs only what is downstream of it.
   - **Rewire / restructure:** `canvas_build { canvasId, remove, nodes, edges }` swaps parts of the graph in one step; `canvas_remove` just deletes. Paid results of untouched nodes are kept.
   - **Branch:** `canvas_duplicate` before a big change keeps the current version as its own canvas.
   - **Stop** a run the user wants to abandon with `canvas_stop`, then keep polling the job until it ends (`stopped: true`). A later `canvas_run` resumes: finished nodes are not run or charged again.
7. **Deliver** the `outputPath`: `import_frontend_assets` into a project, `save_file_as`, or `social_publish`.

## Examples

Free slideshow from local files (no credits, no sign-in needed):

```json
{
  "name": "Holiday slideshow",
  "nodes": [
    { "id": "photos", "type": "media", "params": { "files": ["C:\\Users\\me\\Pictures\\a.jpg", "C:\\Users\\me\\Pictures\\b.jpg"] } },
    { "id": "song", "type": "media", "params": { "files": ["C:\\Users\\me\\Music\\song.mp3"] } },
    { "id": "cut", "type": "sequence", "params": { "aspectRatio": "16:9", "imageSec": 2.5 } },
    { "id": "final", "type": "output" }
  ],
  "edges": [
    { "from": "photos", "fromPort": "image", "to": "cut", "toPort": "clips" },
    { "from": "song", "fromPort": "audio", "to": "cut", "toPort": "music" },
    { "from": "cut", "to": "final" }
  ]
}
```

Narrated AI short (paid — estimate first):

```json
{
  "name": "Mars in 30 seconds",
  "nodes": [
    { "id": "brief", "type": "text", "params": { "text": "Why Mars is red, for curious teenagers." } },
    { "id": "scenes", "type": "writer", "params": { "mode": "list", "count": 5, "instruction": "One vivid, self-contained visual prompt per scene: subject, setting, lighting, camera." } },
    { "id": "script", "type": "writer", "params": { "instruction": "A 30-second voiceover script, plain sentences, no stage directions." } },
    { "id": "stills", "type": "image", "params": { "aspectRatio": "9:16" } },
    { "id": "clips", "type": "video", "params": { "aspectRatio": "9:16", "duration": 5 } },
    { "id": "narration", "type": "voice" },
    { "id": "bed", "type": "music", "params": { "prompt": "curious, light ambient synth", "durationSec": 30 } },
    { "id": "cut", "type": "sequence" },
    { "id": "final", "type": "output" }
  ],
  "edges": [
    { "from": "brief", "to": "scenes" },
    { "from": "brief", "to": "script" },
    { "from": "scenes", "to": "stills" },
    { "from": "stills", "to": "clips", "toPort": "image" },
    { "from": "script", "to": "narration" },
    { "from": "clips", "to": "cut", "toPort": "clips" },
    { "from": "narration", "to": "cut", "toPort": "voice" },
    { "from": "bed", "to": "cut", "toPort": "music" },
    { "from": "cut", "to": "final" }
  ]
}
```

Keep the look consistent by describing the character identically in every scene prompt, or wire a reference image (a Media node) into each Image node's `refs`.

## Common failures

| Symptom | Cause → fix |
|---------|-------------|
| `success: false, errors: [...]` from `canvas_build` | Nothing was changed. Fix each listed error (they name the node, port or param and the valid choices) and resend the whole request. |
| `Media files not found — nothing was changed` | A `params.files` path is not on disk. Use absolute paths the machine running Shorz can read. |
| `needsApproval: true` | Not an error: the run costs credits. Show `estimatedCredits`, then call with `maxCredits`. |
| `…now estimated at ~N credits, above maxCredits…` | The graph changed after the estimate. Re-estimate and ask again. |
| `Not signed in` / `no paid credits` / `needs about N credits — you have M` | Sign the user in or have them buy credits. Nothing ran. |
| `Canvas is running …` | A run is in progress (yours or the user's). Wait for it (`get_job_status`) or `canvas_stop` it, then retry. |
| `… is running — stop it first (canvas_stop)` from `canvas_delete` | The canvas to delete is mid-run. `canvas_stop`, wait for the job to end, then delete. |
| `No canvas with id …` / `No node … on this canvas` | Take ids from `canvas_list` / `canvas_get`. |
| `No take …` / `no takes yet` from `canvas_pick_take` | Use a number or id from the node's `takeList` in `canvas_get`; a node that never ran has no takes. |
| Job `error` with `failed: [{ id, error }]` | Those nodes failed; nodes depending on them were skipped. Finished nodes are kept — fix the cause (a prompt, a missing wire) and `canvas_run` again; only the failed and skipped nodes re-run. |
| `Canvas did not answer` / `window reloaded` | The Shorz window was closed or reloaded mid-request. (Calls made while Shorz is still starting are not lost — they wait for the window.) `canvas_get` to see what finished, then retry. |
| Several `canvas_build` calls at once | Fine: each lands on its own canvas. They are applied one after another. |
