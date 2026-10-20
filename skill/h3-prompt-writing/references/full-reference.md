# H3 full-reference mode (Ref2VA)

Read [shared syntax](shared-syntax.md) for shots, camera, speakers, dialogue, and sound. This guide adds reference semantics and format differences. Always write in English, regardless of the user's language or any requested prompt language, preserving dialogue, lyrics, and visible text verbatim unless the user requests translation/rewriting. Keep field names and fixed markers unchanged.

## Six fields, in order

```text
subject_definitions: ...
summary: ...
retention_analysis: ...
detailed_description: ...
overall_soundscape: ...
non_diegetic_music: ...
```

Each definition and retention entry occupies its own line. The summary is one short paragraph. Scale the detailed description to the actual shots; there is no mandatory word count. The retention field specifies observable reference relationships, not internal reasoning.

## Define reference roles

| Label | Role |
| --- | --- |
| `<Subject N>` | Reusable visible content: person, animal, prop, scene, clothing, style, action, expression, or effect |
| `<Picture N>` | Concrete first/last/intermediate/edited frame or storyboard/composition anchor |
| `<Video N>` | Whole-video editing source, continuation boundary, or temporal/camera/cut structure |
| `<Audio N>` | Copied audio signal or a reference for timbre, content, texture, music, rhythm, or continuity |

Define each independently tracked item with its source, intended role, and known relevant attributes. One asset can supply several subjects; several assets can jointly define one subject. A video supplying reusable visible content still defines a `<Subject N>`, not a replacement `<Video N>` subject label.

For appearance-only images, cite the source inside the subject entry without a separate picture entry. A standalone picture entry is appropriate when the actual frame or storyboard is tracked. Likewise, a source video mentioned only as provenance need not get an independently tracked definition.

```text
<Subject 1> is the character whose appearance comes from <Picture 1> and walking action comes from <Video 1>.
<Picture 2> is the first frame of [Shot 1].
<Picture 3> is the storyboard reference for [Shot 1] and [Shot 2], supplying viewpoint, blocking, and shot order.
```

These are independent syntax examples, not a combined default inventory. Preserve existing asset labels and roles; never invent attributes of inaccessible media.

Visual and audio labels are numbered separately. A source may supply `<Video 1>` and `<Audio 2>`; equal indices do not imply pairing. A video containing sound does not automatically activate an audio reference. Name shared provenance when ambiguity requires it.

When an audio reference binds to a target speaker, its definition reuses that speaker's global ID:

```text
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).
```

## Summary task prefixes

Start `summary` with the applicable types in brackets, joining multiple types with ` + ` without duplication:

| Type | Meaning |
| --- | --- |
| `keyframe completion` | Concrete target-frame anchor, including edited frames |
| `reference generation` | Semantic guidance for subject, style, action, camera, or storyboard |
| `video editing` | Direct modification of an existing video |
| `video continuation` | New material extends/resumes/transitions from a source video |
| `audio reuse` | All or part of the same signal is copied |
| `audio reference` | Audio characteristics/content guide new sound without signal copying |

The mere presence of video or audio does not create editing/reuse. Camera-only video reference is reference generation. Editing an image is not video editing. An edit retaining original audible sound also uses audio reuse; continuity of newly generated sound may instead use audio reference.

For video editing, the prose after the prefix begins `The target video is an edited version of <Video 1>.` Use the actual master label if different. Summarize the target and established reference relationships without introducing new tracked labels.

## Retention markers

Use one line per independently defined reference. Evaluate fidelity within its declared role: a new action/background does not imply loss of an appearance-only reference.

| Visual marker | Meaning |
| --- | --- |
| `fully_preserved` | All characteristics of the defined role retained |
| `partially_preserved` | Some defined characteristics changed or omitted |
| `attribute_transfer` | Characteristics transferred to a different identifiable target |
| `weak_reference` | Broad category/style/composition similarity only |

```text
<Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - the defined appearance is retained.
<Picture 2> ([Shot 1] first frame): fully_preserved - the opening frame is retained.
<Video 1> (cut and pacing structure): weak_reference - broad pacing is followed.
```

| Audio marker | Meaning |
| --- | --- |
| `fully_copy` | Complete source is the target's entire final audio track |
| `partially_copy` | Partial timeline/layers copied, or sounds added/removed/replaced |
| `reference` | New signal follows timbre, rhythm, music, words, or sound texture |
| `weak_reference` | Broad category/atmosphere similarity only |

```text
<Audio 1>: reference - voice timbre guides the target speaker without copying source words.
```

Do not mark a copied music layer as fully_copy if other sounds are mixed into the final track. Do not put `(Sx)` speaker IDs in retention entries.

## Detailed timeline

Place one or two style sentences before `[Shot 1]` in `detailed_description`, unlike the base-mode style opening after that tag. The first shot has no timestamp; subsequent cuts use `[Shot N] At MM:SS.mmm, ...`, increasing within the duration.

At the first visible appearance of a subject, bind its label to relevant known appearance, position, and action. Keep that meaning across shots. Cite frame anchors naturally: `the shot begins from <Picture 1>`, `the shot's keyframe corresponds to <Picture 2>`, or `the shot ends on <Picture 3>`. Cite video sources where editing, structure, or continuation applies. Cite audio at the shot/phase where copying or reference is active.

### Speakers and source sound

Assign `(S1)`, `(S2)`, etc. once in order of actual target vocal events, independently of subject numbers. A speaking referenced subject uses both `<Subject N> (Sx)`; keep that binding off-screen. Unmapped voices use a stable voice description and ID. Audio definitions bound to a speaker reuse this ID, never assign their own.

```text
<Subject 2> (S1) turns toward the doorway and says, <d>[English] Come in.</d>
```

Words occurring only inside a directly reused soundtrack/BGM use `<Audio N>` as the audible source; do not invent a separate speaker because a visible subject gestures to those words. A concrete person, narrator, or independent vocal source producing words does receive a speaker ID.

For reused or reperformed speech/lyrics, retain the source words and language in `<d>`. Mark genuinely unintelligible spans of an inspected transcription `[unclear]`; do not label wholly inaccessible audio as transcribed. User-supplied words/punctuation remain verbatim unless editing is requested. Timbre-only references do not bring source dialogue into the target. Shared syntax covers voiceover, group speech, cross-cut `<scenetrans>`, and ending `<cutoff>`.

## Global sound fields

Keep full dialogue/lyrics only in `<d>` within `detailed_description`. Summarize ambience/physical sounds in `overall_soundscape`; audience-only score belongs in `non_diegetic_music`. Put reference-copy relationships in the field for the actual audible layer. An audio supplying both ambience and score may appear in both fields, describing each layer. Do not duplicate the complete transcript there.

Use `N/A` for soundscape only for complete silence, and for music when no non-diegetic score is present. Preserve a fully copied soundtrack without inventing added layers. See [examples](examples.md) for a complete concise Ref2VA prompt.
