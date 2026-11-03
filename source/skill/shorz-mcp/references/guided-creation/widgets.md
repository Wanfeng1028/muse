# Widget steps (inline cards instead of a question)

Some wizard steps are better as a **card widget** than as a 4-option question: picking an image for a slot, choosing a model, choosing a voice. This file defines exactly when to render one, what it looks like, and how its buttons come back to you. Every other step stays on the normal question tool.

## When a widget is available (check this BEFORE the step — it is a hard rule, not a preference)

1. **Look for a `show_widget` tool.** In the Claude desktop app it belongs to the built-in visualize server (namespaced, e.g. `mcp__visualize__show_widget`). **It is frequently deferred** — not in the initial tool list — so run `ToolSearch` with `select:mcp__visualize__show_widget,mcp__visualize__read_me` (or a keyword search for `show_widget`) before concluding it is absent. Only if the search finds nothing do you run the step with the question tool as written in the flow file.
2. Before the first `show_widget` of a session call its companion `read_me` with `modules: ["mockup"]`. Do it silently; never mention it.
3. **A widget step replaces the tool call, not just the question.** On an image step you do NOT call `select_local_image_for_import` on your own — you render the cards and stop. The native dialog opens only after the user presses *Open file picker ↗* and that phrase arrives as their message. Opening the dialog unprompted is the failure this file exists to prevent.
4. A widget is a **step**: render it, then **stop and wait**. Its buttons send a message on the user's behalf (`sendPrompt`), so the reply arrives as a normal user turn. Do not re-ask the same thing in text while the widget is on screen, and do not batch it with other questions.
5. Never put base64 in a widget, never use `<input type="file">` (the browser gives bytes, never a path — Shorz needs the path), never load images from disk or the web (blocked). Image slots show an icon, the file name once chosen, and the buttons.
6. Every button carries one of the **fixed phrases** below so you recognise it verbatim. Substitute only the `<…>` parts. Keep ≤ 12 cards per widget.

## Fixed phrases → what you do when they arrive

| Phrase the button sends | Action |
|---|---|
| `Open the Shorz file picker for the <slot> image` | `select_local_image_for_import { options: { title: "Select <Slot> image", extensions: [<allowed>] } }` (blocks until the dialog closes). `canceled` → re-render the same widget untouched. Otherwise apply the path with the flow's select tool (table in the flow file), then re-render the widget with that slot marked **Selected · file.png**; when no required slot is empty, continue to the next step. |
| `Use <path> as the <slot> image` | Same as above without the dialog: `file_exists`, check the extension, apply, re-render. |
| `Use <path> as the song` | Music video song slot (there is no audio file dialog over MCP, so this is the only song phrase): check the extension (`.mp3 .wav .m4a .ogg .flac`), probe it with `get_media_info { inputPath }`, report the length, and continue to the next step. The copy into the project (`select_music_video_audio`) runs at execution. |
| `Generate the <slot> image with AI` | Run the flow's generate branch (it will ask for a description with the question tool), apply the output, re-render. |
| `Skip the <slot> image` | Only ever offered on optional slots. Leave it empty, re-render. |
| `Use <model label> as the <role> model` | Map the label to its id from the flow file and write it with the flow's `set_*_settings` call; continue. |
| `Use the voice <voice name> for <role>` | Resolve the name against `list_elevenlabs_voices` (ids are stable; names are display-only), write with the flow's call; continue. |
| `Show more <role> voices` / `Show more <role> models` | Re-render with the next 8 options. |

If a message matches none of these, treat it as the user's free text for the current step.

## Template A — Image slot picker

Use for: advertisement product / character (Q3), avatar presenter image + own angle images, podcast interviewer / interviewee, text-to-video style / character / environment references, music video artist (optional). One card per slot. Slots that allow generation get the AI button; only optional slots get Skip. `--bg-accent` border on the first empty required slot.

```html
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;padding:0.5rem 0 1rem;">
  <!-- one card per slot -->
  <div style="background:var(--surface-2);border:2px solid var(--border-accent);border-radius:12px;padding:1rem 1.25rem;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
      <i class="ti ti-box" style="font-size:20px;color:var(--text-secondary)" aria-hidden="true"></i>
      <span style="font-size:15px;font-weight:500;color:var(--text-primary)">Product</span>
      <span style="margin-left:auto;font-size:12px;padding:2px 8px;border-radius:var(--radius);background:var(--bg-accent);color:var(--text-accent)">Required</span>
    </div>
    <p style="margin:0 0 12px;font-size:13px;color:var(--text-secondary)">One clear photo on a simple background · JPEG or PNG</p>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <button onclick="sendPrompt('Open the Shorz file picker for the product image')"><i class="ti ti-folder-open" aria-hidden="true"></i> Open file picker ↗</button>
      <div style="display:flex;gap:8px;">
        <input id="p-product" type="text" placeholder="C:\Users\you\Pictures\product.png" style="flex:1;min-width:0;" />
        <button onclick="var v=document.getElementById('p-product').value.trim();if(v){sendPrompt('Use '+v+' as the product image')}">Use path ↗</button>
      </div>
    </div>
  </div>
  <div style="background:var(--surface-2);border:0.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
      <i class="ti ti-user" style="font-size:20px;color:var(--text-secondary)" aria-hidden="true"></i>
      <span style="font-size:15px;font-weight:500;color:var(--text-primary)">Character</span>
      <span style="margin-left:auto;font-size:12px;color:var(--text-muted)">Optional</span>
    </div>
    <p style="margin:0 0 12px;font-size:13px;color:var(--text-secondary)">A portrait of the person presenting the product · JPEG or PNG</p>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <button onclick="sendPrompt('Open the Shorz file picker for the character image')"><i class="ti ti-folder-open" aria-hidden="true"></i> Open file picker ↗</button>
      <button onclick="sendPrompt('Generate the character image with AI')"><i class="ti ti-sparkles" aria-hidden="true"></i> Generate with AI ↗</button>
      <button onclick="sendPrompt('Skip the character image')">Skip ↗</button>
    </div>
  </div>
</div>
```

**Selected state** (re-render after a pick): replace the buttons with
`<div style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-success)"><i class="ti ti-check" aria-hidden="true"></i> Selected · product.png</div>` plus a single `Change ↗` button that sends the file-picker phrase again. Multi-image slots (angles ≤3, style refs ≤3, characters ≤4) show `n / max` in the badge and keep the picker button until the cap.

**Song slot (music video Q1)** — same card, but audio has no file dialog over MCP, so it carries only the path field; once the length is known, re-render it as selected with `Selected · song.mp3 · 3:12`.

```html
<div style="background:var(--surface-2);border:2px solid var(--border-accent);border-radius:12px;padding:1rem 1.25rem;max-width:420px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
    <i class="ti ti-music" style="font-size:20px;color:var(--text-secondary)" aria-hidden="true"></i>
    <span style="font-size:15px;font-weight:500;color:var(--text-primary)">Song</span>
    <span style="margin-left:auto;font-size:12px;padding:2px 8px;border-radius:var(--radius);background:var(--bg-accent);color:var(--text-accent)">Required</span>
  </div>
  <p style="margin:0 0 12px;font-size:13px;color:var(--text-secondary)">MP3, WAV, M4A, OGG or FLAC on this computer</p>
  <div style="display:flex;gap:8px;">
    <input id="p-song" type="text" placeholder="C:\Users\you\Music\song.mp3" style="flex:1;min-width:0;" />
    <button onclick="var v=document.getElementById('p-song').value.trim();if(v){sendPrompt('Use '+v+' as the song')}">Use path ↗</button>
  </div>
</div>
```

## Template B — Model picker

Use for: avatar / podcast avatar model, text-to-video image + video model, music video video + image model. Cards in the flow's order, recommended first with the accent border and a "Recommended" badge; the price line quotes the rate from the flow file / live catalog; the fit line is the flow's one-sentence note (e.g. the clip-cap warning). Only models the flow allows in that branch.

```html
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;padding:0.5rem 0 1rem;">
  <div style="background:var(--surface-2);border:2px solid var(--border-accent);border-radius:12px;padding:1rem 1.25rem;">
    <span style="display:inline-block;font-size:12px;padding:2px 8px;border-radius:var(--radius);background:var(--bg-accent);color:var(--text-accent);margin-bottom:8px">Recommended</span>
    <p style="margin:0;font-size:15px;font-weight:500;color:var(--text-primary)">Kling Avatar Pro</p>
    <p style="margin:2px 0 8px;font-size:13px;color:var(--text-secondary)">Balanced quality and cost</p>
    <p style="margin:0 0 12px;font-size:13px;color:var(--text-muted)">≈ 6 credits / s</p>
    <button style="width:100%" onclick="sendPrompt('Use Kling Avatar Pro as the avatar model')">Select ↗</button>
  </div>
  <!-- … one card per allowed model … -->
</div>
```

## Template C — Voice picker

Use for: avatar voice, text-to-video narration voice, podcast interviewer / interviewee voice (one widget per role, title says which). Cards come from `list_elevenlabs_voices`, pre-filtered by the flow's fit logic (warm / bright / energetic / authoritative), max 8, with a final "Show more" card. Pills are the voice's `language` / `accent` / `useCase` in sentence case. When `audioSrc` is non-empty add a `Sample` link — it opens in the host's link dialog; the widget itself cannot play audio.

```html
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;padding:0.5rem 0 1rem;">
  <div style="background:var(--surface-2);border:0.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;">
    <p style="margin:0 0 6px;font-size:15px;font-weight:500;color:var(--text-primary)">Rachel</p>
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px;">
      <span style="font-size:11px;padding:2px 6px;border-radius:9999px;border:0.5px solid var(--border);color:var(--text-secondary)">English</span>
      <span style="font-size:11px;padding:2px 6px;border-radius:9999px;border:0.5px solid var(--border);color:var(--text-secondary)">American</span>
      <span style="font-size:11px;padding:2px 6px;border-radius:9999px;border:0.5px solid var(--border);color:var(--text-secondary)">Narration</span>
    </div>
    <div style="display:flex;gap:8px;">
      <button style="flex:1" onclick="sendPrompt('Use the voice Rachel for the narrator')">Select ↗</button>
      <a href="https://…/preview.mp3" style="align-self:center;font-size:13px;color:var(--text-accent)">Sample</a>
    </div>
  </div>
  <!-- … up to 8 … then: -->
  <div style="border:0.5px dashed var(--border-strong);border-radius:12px;padding:1rem 1.25rem;display:flex;align-items:center;justify-content:center;">
    <button onclick="sendPrompt('Show more narrator voices')">Show more ↗</button>
  </div>
</div>
```

## Style rules (from the widget design system — these are enforced, not suggestions)

Flat surfaces, `0.5px` borders, `12px` card radius, no gradients or shadows, sentence case, weights 400/500 only, Tabler outline icons (`ti ti-…`, never `-filled`), colours only through the CSS variables above, no emoji, no `position: fixed`, every `sendPrompt` button ends with `↗`. Explanatory prose goes in your chat message above the widget, never inside it.
