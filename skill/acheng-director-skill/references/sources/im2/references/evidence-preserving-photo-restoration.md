# Evidence-Preserving Photo Restoration

Use this branch when the image is a record of a real person, product, event, place, document, or transaction. The objective is **truthful photographic correction**, not attractive reconstruction.

## Truth Locks

Write a lock ledger before editing:

- people: identity, count, relative placement, pose/action, age range and distinguishing features;
- products: SKU/type, geometry, color, count, label, logo, packaging, defects and arrangement;
- scene: location facts, signs, furniture, event setup, weather/time cues and evidence-bearing background details;
- text/data: spelling, numbers, date, time, price, QR code, badges, certificates and measurement marks;
- food/objects: portion, ingredients, container, doneness/state and quantity.

Text, logo, QR, date, price and identity are zero-tolerance surfaces. If they cannot be recovered from evidence, preserve the uncertainty or replace them only from an authoritative reference supplied for that exact role.

## Lowest-Necessary Edit

Apply the smallest sufficient sequence:

1. crop, horizon and perspective correction;
2. white balance and global exposure;
3. highlight recovery and readable shadow lift;
4. noise, compression and restrained sharpness correction;
5. local color/contrast repair;
6. localized generative repair only where evidence uniquely supports the missing content.

Prefer remaining blur, glare or partial occlusion over invented faces, letters, labels, limbs, products, ingredients or environmental facts.

## Category Priorities

| category | preserve first | common overreach |
|---|---|---|
| event | participants, action, signage, time/place evidence | adding people, decor or dramatic light |
| store/office | layout, fixtures, brand surfaces, cleanliness evidence | turning it into a showroom render |
| product | exact shape, color, package, label and defect | redesigning package or perfecting geometry |
| team/group | identity, headcount, row order and body relation | face replacement or body synthesis |
| food | ingredients, portion, vessel and real surface state | inventing garnish, steam or gloss |
| social snapshot | relationship, moment, place and device artifacts | beauty retouch that changes identity |
| document/evidence | all characters, numbers, layout, stamps and marks | hallucinated OCR or reconstructed text |

## Post-Edit Truth Review

Compare before/after on the truth-lock ledger. Mark each field `preserved`, `improved without semantic change`, `uncertain`, or `changed`. Any unsupported semantic change fails the edit even if the result looks more polished.

Actual image editing still uses the active image-edit executor. This reference defines what may change; it is not an editing engine.
