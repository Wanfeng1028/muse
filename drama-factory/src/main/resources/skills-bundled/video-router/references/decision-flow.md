# Decision flow

Start from what must be delivered, not a model leaderboard. The executable counterpart is `scripts/avs.py route`; the machine graph is `registry/navigation.json` plus `registry/workflows.json`.

```mermaid
flowchart TD
  A[Brief and constraints] --> B{Exact copy, UI, charts or editable code?}
  B -->|Yes| C{Need generated footage too?}
  C -->|No| D[Procedural: renderer and motion skill]
  C -->|Yes| E[Hybrid: footage model plus deterministic overlay]
  B -->|No| F{New footage or change an existing clip?}
  F -->|New| G[Text, image, references, audio or multishot mode]
  F -->|Existing| H[Edit, retake, extend or enhance mode]
  G --> I[Filter exact model, backend, capabilities and constraints]
  H --> I
  E --> I
  I --> J{Compatible documented surface?}
  J -->|No| K[Report exclusions; never silently relax constraints]
  J -->|Yes| L[Prefer recent verified releases, then workflow fit]
  L --> M[Read model guide and inspect compatible skill]
  D --> M
  M --> N[Live schema, access, license, budget and asset preflight]
  N --> O[Authorized draft, playback review, targeted revision]
  O --> P[Media, editable project, provenance and QA]
```

Native generated audio is not input-audio conditioning. Motion transfer is not motion graphics. First-frame anchoring is not a loose identity reference. A newer model is not a valid substitute for an older model’s missing edit operation. Exact model requests remain hard constraints; freshness is a preference, not permission to override them.
