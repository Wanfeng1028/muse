# Heavy-Scene Structure And Mass

Use this branch for architecture, interiors, terrain, megastructures, and hard-surface environments when the result must feel structurally grounded and physically heavy. Keep portraits, skin close-ups, flat graphic layouts, and purely painterly work on their normal branches.

## 1. Build The Structure Lock

When a source image exists, record only visible or source-proved facts:

- frame, crop, horizon, vanishing directions, camera height, and subject scale;
- fixed landmarks and their count, position, orientation, and proportion;
- entrances, exits, roads, bridges, stairs, windows, negative spaces, and passable routes;
- front/mid/background occupancy and major occlusion relations;
- visible wall, slab, shell, or component thickness;
- opening depth, overlap depth, support contact, ground contact, and apparent center of gravity.

Put these facts in the image transaction before style language. Treat the lock as an acceptance target, not a promise of pixel-perfect generative control. Route exact registered geometry, local pixels, or measurable dimensions to masks, registration/comparison, compositing, or 3D reconstruction.

## 2. Compile Visible Mass Evidence

Make scene weight visible through:

- large continuous masses before small detail;
- readable thickness at edges, openings, cutaways, slabs, and shells;
- credible load paths, overlaps, supports, compression, and grounded contact;
- stable centers of gravity and convincing front-to-back occlusion;
- material-specific absorption, roughness, highlight width, edge response, and reflection falloff;
- localized contact shadows only at real seams, overlaps, supports, and ground contacts.

Do not substitute crushed blacks, global HDR, dense fog, full-frame grain, global sharpening, or repeated microtexture for mass. Keep shadow-side structure readable and let distant detail decay.

Compact prompt block:

```text
Large and medium structural masses dominate. Existing walls, slabs, openings, overlaps, supports, and ground contacts show scale-correct visible thickness and stable load-bearing relations. Weight comes from volume, material response, occlusion, and localized contact shadows; broad surfaces remain continuous and quiet, with small detail limited to camera-readable construction, wear, and contact zones. Highlights retain material texture, shadows retain structural readability, and distant detail decays naturally.
```

## 3. Inspect The Actual Output

Do not mark the task complete from the prompt alone. After the generated result is available, compare it with the structure lock and record `PASS` or `FAIL` for:

1. camera, crop, perspective, subject scale, and depth layers;
2. fixed landmarks, topology, negative spaces, and passable routes;
3. visible thickness, opening depth, overlap, support, ground contact, and balance;
4. continuous large surfaces without uniform tiling or fish-scale microtexture;
5. distinct material responses, protected highlights, readable shadows, and localized contact shadows;
6. mass produced by physical evidence rather than darkness, fog, grain, or sharpening.

If exact comparison is required, use overlays, landmarks, masks, registration, or measurements instead of visual confidence alone.

## 4. Retry One Main Variable

Freeze every control that already passes. Change one main variable per retry:

| Failure evidence | Change only | Freeze |
|---|---|---|
| One landmark drifts while the rest is stable | Add one position/count lock for that landmark | Other structure, style, settings |
| Opening depth is unreadable | Increase interior/exterior value separation at existing openings | Geometry, palette, other lighting |
| Supports or ground contact float | Strengthen contact evidence only at true support/ground zones | Geometry, key light, materials |
| Overlap or load path is unclear | Add grazing-light or edge separation at that junction | Camera, geometry, global exposure |
| Surfaces tile into small repeated units | Lower inherited microtexture or restrict detail to meaningful zones | Structure lock, palette, light direction |
| Materials look uniformly plastic | Separate existing materials by roughness and highlight behavior | Material classes, structure, composition |
| Mass becomes dead black | Raise the readable shadow floor | Thickness, light direction, material classes |
| Seams develop dirty halos | Restrict AO/contact shadow to true seams and contacts | Texture, silhouette, main materials |

Restart from the clean accepted base when a failed output carries residue or structural drift; do not stack corrective image-to-image passes on that failure.

## 5. Record Controls And Handoff

- Keep dimensions, modes, reference weights, seeds, sliders, and output settings outside the content prompt unless the adapter requires prompt syntax.
- Record actual platform values used. Never describe an unverified value as optimal; a midpoint may be only an exploratory starting point.
- Handoff: source/reference assets, structure lock, final prompt and avoid block, selected output, platform/model/mode, actual settings, acceptance result, remaining defect, and the next single variable to change.
