# Scene Art Contract v1

`scene_art_direction.json` is the scene specialist's portable contract. It is a design artifact, not a replacement for Acheng `production.json`. The specialist may create and revise this artifact; the Acheng assets owner decides which approved facts enter `scene_registry`, asset cards, and final prompts.

## Minimum shape

```json
{
  "schema_version": "scene-art-v1",
  "scene_id": "SCENE_001",
  "revision": 1,
  "status": "DRAFT",
  "purpose": "concept_keyart",
  "source": {"kind": "brief", "refs": [], "assumptions": []},
  "thesis": {"statement": "...", "primary_tension": "..."},
  "world_context": {
    "location": "...", "era": "...", "season": "...", "day_phase": "...",
    "function": "...", "power_or_maintenance": "...", "recent_event": "...", "offscreen_world": "..."
  },
  "spatial": {
    "dominant_grammar": "...", "secondary_grammar": "...",
    "boundary": "...", "entrances": [], "exits": [], "landmarks": [],
    "traversal": [], "foreground": "...", "midground": "...", "background": "...",
    "scale_anchors": []
  },
  "design": {
    "materials": [], "aging_behavior": [], "cultural_logic": [], "motifs": [],
    "human_use": [], "iconic_object": "...", "weather": "...", "atmosphere": "..."
  },
  "camera": {"intent": "...", "framing": "...", "height": "...", "lens_feel": "...", "target": "...", "path": "..."},
  "lighting": {"sources": [], "key_direction": "...", "contrast": "...", "color_roles": [], "depth_strategy": "..."},
  "references": [],
  "constraints": {"preserve": [], "exclude": [], "unknowns": []},
  "generation": {"intent": "GENERATE", "model_family": "model-neutral", "input_mode": "text", "execution_settings": {}},
  "handoff": {"owner": "scene-design", "consumers": ["assets"], "write_paths": [], "frozen_facts": [], "advisory_paths": []},
  "prompt_status": "DRAFT",
  "visual_status": "UNVERIFIED",
  "evidence": [],
  "unresolved": []
}
```

## Enumerations and invariants

- `status`: `DRAFT`, `DIRECTION_LOCKED`, `PROMPT_READY`, `BLOCKED`, `SUPERSEDED`.
- `purpose`: `concept_keyart`, `establishing_shot`, `background_plate`, `set_design`, `matte_painting`, `game_environment`, `layout`, `style_probe`, `repair`, or `multi_view`.
- `generation.intent`: `GENERATE`, `EDIT`, `REBUILD`, or `MIXED`.
- `prompt_status`: `DRAFT`, `DRAFT_MISSING_REFERENCES`, `READY_TO_SUBMIT`, or `BLOCKED`.
- `visual_status` is `UNVERIFIED` until an actual image is reviewed by a human. `PASS` is not a synonym for generated.
- `scene_id` and `revision` are stable. A revision changes when a design fact, reference, or prompt changes.
- `references[].id` is unique. Each reference has `file`, `role`, `preserve`, `exclude`, and `status`; an approved reference also has a matching `sha256`.
- `EDIT`, `REBUILD`, and `MIXED` require at least one real reference. `GENERATE` may use zero references and must say `reference_policy: none` in the exported index.
- `handoff.write_paths` is always empty. The scene specialist returns advice and artifacts; the owning Acheng module performs any production merge.
- `unresolved` contains missing decisions, missing files, cultural uncertainty, unsupported model capabilities, and visual checks still waiting for real output.

## Handoff ownership

| Fact | Final owner | Scene specialist contribution |
|---|---|---|
| Scene identity, geometry, entrances, landmarks | `assets` / scene registry | proposed spatial contract and evidence |
| Shot-specific framing, lens, movement, frame range | `shots` | camera intent and composition constraints only |
| VFX, destruction, scale proofs | `effects` | material/atmosphere consequences only |
| H3 scene prose and segment references | `model` | complete scene description as input, never H3 syntax |
| Damage, state, continuity | `continuity` | recent event and visible state assumptions |

If a scene proposal conflicts with a confirmed production fact, keep the confirmed fact, record `rejected/adopted/reason/source`, and return the conflict instead of silently rewriting another owner.
