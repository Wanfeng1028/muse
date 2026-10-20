# MiniMax H3 prompting, reference semantics, and continuity

Use this guide when a clip will be sent to MiniMax H3 or when a project uses multiple reference images, videos, or audio assets.

## Choose the H3 mode

- **T2VA**: no frame reference; write the complete audiovisual timeline.
- **I2VA**: one first-frame image; establish the exact opening state before motion.
- **FL2VA**: first and last images; describe the continuous physical path between them and land on the last frame.
- **L2VA**: one last-frame image; infer a compatible opening and converge toward the supplied end state.
- **Ref2VA**: multiple reference assets; define subjects separately from source files, then describe retention and use.

The provider-facing prompt may use H3's English field names while preserving Chinese dialogue, lyrics, and visible text:

```text
integrated_multimodal_description: ...

overall_soundscape: ...

non_diegetic_music: ...
```

For Ref2VA use, in order: `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`. Keep the human-facing Chinese director prompt as the source of truth; generate this provider adapter only at submission time.

## Reference semantics

Give every material reference a stable label and role. Separate the reusable subject from the file that supplies it:

- `<Subject 1>`: the character, location, prop, style, pose, or action actually used.
- `<Picture 1>`: a concrete first frame, keyframe, last frame, or composition anchor.
- `<Video 1>`: a source video whose motion, edit structure, or continuation is used.
- `<Audio 1>`: a copied or referenced voice, music, ambience, or effect track.

For each reference record one relationship: `fully_preserved`, `partially_preserved`, `attribute_transfer`, or `weak_reference`; for audio use `fully_copy`, `partially_copy`, `reference`, or `weak_reference`. State what is inherited and what is explicitly excluded. Never allow a character sheet's grid, studio background, or neutral pose to become the scene.

## Shot state and handoff

Every shot table row must contain:

- fixed landmarks and their screen-relative positions;
- lighting baseline and changes;
- each important character's position, facing, pose, and mouth state;
- prop/object state, contact points, and motion direction;
- exited characters and their off-screen destination;
- `continuity_from` and `continuity_to` handoffs.

The next shot must inherit the previous shot's end state unless a deliberate cut, time jump, or transformation explains the change. For a compatible same-view H3 continuation, use the preceding visually approved retained end frame as the first reference slot, then identity anchors, location, prop, and layout references. State that the end frame controls opening composition while identity sheets control identity only.

## Audio master timeline

For projects longer than one generated clip, define one `master_audio` asset or timeline before rendering. Record dialogue, lyric, ambience, SFX, music, ducking, and cut points against absolute project time. Prefer cuts on breath, lyric pauses, beat subdivisions, or deliberate motion matches. Do not create disconnected per-clip music when one continuous score is intended. Preserve diegetic sound through cuts when the action continues.

## H3 writing rules

Use concrete composition, subject, action, camera, and sound descriptions. Camera movement includes type, meaningful amplitude, and speed. A cut must introduce new information; use camera motion for a small viewpoint change. For dialogue, assign stable speaker IDs, preserve exact wording, and state listener silence and mouth closure. Keep the final-frame instruction free of dialogue text. Keep total described duration equal to the requested clip duration (4–15 seconds).

For multi-clip boundary choice, staged rendering, and moving-footage acceptance, follow [continuity-and-edit-design.md](continuity-and-edit-design.md). A new viewpoint or scene does not automatically require literal end-frame reuse.
