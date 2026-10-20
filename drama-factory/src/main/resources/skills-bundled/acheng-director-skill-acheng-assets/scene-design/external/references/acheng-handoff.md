# Acheng Director Handoff｜scene-art-v1

This reference defines the boundary between the scene-concept-art-director specialist and Acheng Director. It is read for `handoff`, `repair`, and any request routed through the Acheng assets branch.

## Handoff envelope

Return one reviewable envelope with these fields:

```json
{
  "contract_version": "scene-art-v1",
  "request_id": "...",
  "scene_id": "...",
  "input_revision": "sha256:...",
  "artifact": {
    "scene_contract": "scene_art_direction.json",
    "image_prompt": "scene-<id>.image.txt",
    "upload_manifest": "UPLOAD.md",
    "qa": "qa.json"
  },
  "owner": "assets",
  "advisory_patch": {
    "write_paths": [],
    "proposed_facts": [],
    "preserve_exactly": [],
    "unresolved": []
  },
  "prompt_status": "READY_TO_SUBMIT",
  "visual_status": "UNVERIFIED",
  "evidence": []
}
```

`write_paths` is always empty. The specialist may propose facts and artifacts, but it never edits Acheng `production.json`, `scene_registry`, `asset_cards`, ShotSpec, VFX fields, H3 text, or continuity ledger.

## Fact authority

The receiving assets owner classifies every proposed fact as `adopted`, `rejected`, or `deferred` and records `reason` and `source`. Existing approved production facts win over aesthetic suggestions. A proposed camera or effect constraint is advisory until the shots or effects owner accepts it. A proposed persistent state is advisory until continuity accepts it.

Use this mapping:

| Scene specialist may propose | Receiving Acheng owner | Merge target |
| --- | --- | --- |
| thesis, spatial grammar, boundaries, landmarks, traversal, materials, human use, lighting intent, atmosphere, reference roles | assets | `scene_registry`, asset cards |
| composition intent, sightline, depth and scale anchors | shots | ShotSpec constraints |
| material response, occlusion, atmosphere, destruction consequences | effects | VFX and scale evidence |
| complete scene description and model-neutral constraints | model | independent H3 segment input |
| visible weather, damage, time-state assumptions | continuity | continuity ledger after approval |

## Reference and evidence rules

Each reference keeps its role, `preserve`, `exclude`, approval state, local path when supplied, and SHA-256 when available. A moodboard supplies aesthetic direction; it is not automatically `STYLE_MOTHER`. A reference image is not proof that a generated image exists. `prompt_status=READY_TO_SUBMIT` only means the text and required inputs are present. Keep `visual_status=UNVERIFIED` until an actual output is manually reviewed.

## Revision and continuation

For a partial result, return `status=PARTIAL`, `current_cursor`, completed artifact paths, and the next contract section. Never mark a partial envelope accepted. For a repair, identify the scene, field, and preserved facts; use `CHANGE`, `PRESERVE_EXACTLY`, and `REBUILD` entries. The assets owner may request a local delta without forcing a full scene redesign.

## Blockers

Pause only for a missing user decision, missing irreplaceable reference, missing permission, or unavailable external capability. Missing optional inspiration is an assumption to document, not a reason to fabricate a reference or claim visual approval.
