# Multi-view Scene Continuity

Multi-view work is a set of constrained views of one scene, not a set of unrelated prompts. Start with one locked base contract and create view records with explicit deltas.

## Shared anchors

Keep these identical unless the contract explicitly changes state: world location, dominant spatial grammar, landmarks, entrances/exits, architectural proportions, hero object identity, material families, palette roles, gravity and support, and the relationship between light sources and receivers.

## Allowed deltas

Each view names its purpose and changes only what it needs:

- `establishing`: wider framing and stronger scale anchors.
- `background_plate`: simplified foreground and controlled negative space for compositing.
- `layout`: top-down or elevation information with readable entrances, exits, and traversal.
- `keyframe`: shot-specific pose, damage, prop state, and camera while preserving scene geometry.
- `time_weather`: day phase, weather, and resulting material/light changes with a stated cause.
- `repair`: one local change using `CHANGE`, `PRESERVE_EXACTLY`, and `REBUILD`.

Do not use a new view to hide a contradiction. If a camera cannot see the required landmark or a changed light would alter the story state, record the conflict and return it to the owning shots/effects/continuity module.

## View record

```json
{
  "view_id": "SCENE_001_EST",
  "purpose": "establishing",
  "base_scene_id": "SCENE_001",
  "preserve": ["..."],
  "deltas": [{"path": "/camera/framing", "reason": "...", "value": "..."}],
  "prompt_status": "DRAFT",
  "visual_status": "UNVERIFIED"
}
```
