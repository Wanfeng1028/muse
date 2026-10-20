# Real-Scene Light, Atmosphere, and Material Hierarchy

Use this reference for physically grounded IM2 scenes where the image must feel aesthetically selective without sacrificing light geometry, atmospheric behavior, or material credibility.

## 1. Separate invariants from aesthetic freedom

Lock as invariants:

- subject count, identity, pose/action, and essential props;
- camera height, lens family, horizon, verticals, and major spatial relations;
- dominant light-source position, size/hardness, and color family;
- source-to-receiver direction, cast-shadow direction, and reflection alignment;
- dry/wet, opaque/translucent, rough/glossy, and near/far boundaries.

Use aesthetic freedom for:

- one visual thesis and one focal event;
- 3–7 dominant shape groups and at least one calm mass;
- key-to-fill ratio and the amount of information allowed in shadow;
- color separation, atmosphere, and material emphasis;
- selective detail, incomplete contours, and depth-based information loss.

Do not trade an invariant for a locally attractive highlight, glow, reflection, or beam.

## 2. Compile the light path

Write the minimum observable chain:

```text
SOURCE
- world/frame position:
- source size and hardness:
- color family:

SHAPING
- aperture, cloud break, window, doorway, foliage, roof edge, or other occluder:
- beam boundary: none / soft / sharply bounded:

MEDIUM
- clear air, sea mist, humidity, rain spray, dust, smoke, steam, pollen, salt dust:
- localized density and falloff:

RECEIVERS
- first receiving surface:
- hero receiving surface:
- rim-lit edge, if any:

CONSEQUENCES
- cast-shadow direction and softness:
- bounce/reflection path:
- protected highlights:
- readable shadow floor:
```

Every visible lighting claim must map to this chain. If the sun is at frame left, do not place unrelated warm edges on left-facing backsides that the source cannot reach. If a wall light patch ends before the floor, explain the occluder; otherwise continue the geometry onto the floor or water. Keep reflected highlights inside the correct view-dependent path rather than directly beneath every bright object by default.

## 3. Air scattering versus volumetric light

### Atmospheric perspective

Atmospheric perspective comes from extinction plus environmental-light in-scattering. Scale its visibility by distance, humidity, aerosol load, wavelength/color of the environment, and viewing direction.

Use staged information loss:

1. reduce internal small-shape count;
2. reduce edge contrast and contour completeness;
3. reduce local contrast and usually chroma;
4. shift toward the atmospheric-light color only as conditions justify;
5. preserve a few landmark silhouettes or overlaps so depth remains legible.

Do not use global blur. Do not automatically make every distant layer pale, blue, or foggy.

### Volumetric visibility

Visible shafts require participating media and useful source/view geometry. A bounded shaft normally also needs an aperture or occluder. Use these triggers:

- humid interior + doorway/window backlight;
- forest mist + canopy gaps;
- salt/flour/wood dust + industrial opening;
- sea spray + low sun;
- steam/smoke + practical or sun backlight.

Medium density must be spatially owned by its physical source: particles or haze may cluster near an emitting process, settle into a low layer, drift with airflow, or occupy a broader fog bank independently of the light shape. Visible scattering becomes strongest where that distribution intersects the illuminated path under a favorable viewing angle. Solid objects interrupt the illuminated path and create volumetric shadows. Visible shaft radiance and contrast change according to extinction, source divergence, medium density, viewing angle, and exposure; do not force every shaft into a fixed near-bright/far-dark gradient.

Do not add a visible shaft in clean dry air merely to make the frame cinematic. Do not use uniform full-frame haze, particles outside the lit medium, a glow that floats behind an opaque object, or several beams with no apertures.

## 4. Build light ratio without dead shadows

Use one dominant luminous zone and one readable shadow floor.

- Protect texture at the hero highlight; avoid clipped white patches.
- Preserve only the shadow information needed for silhouette, contact, navigation, or story.
- Allow nonessential roof planes, corners, distant objects, or side walls to approach silhouette.
- Use sky fill, bounce, or a practical only when it explains specific visible structure.
- Do not evenly lift every dark region. Flat visibility destroys the focal route.

Thumbnail test: the focal event and dominant value masses must survive at small size. Grayscale test: the focal path must remain clear without relying on saturation alone.

## 5. Make texture conditional on light and scale

For each important material, define:

```text
material class -> roughness/transmission -> receiving angle -> highlight width -> absorption/reflection -> local imperfection ownership
```

Examples:

- matte porous stone: broad diffuse response, grazing-light texture only, dark absorption away from the source;
- wet concrete/asphalt: reflective only inside localized wet regions, with strict wet/dry boundaries;
- water: view-dependent reflection plus transmission/refraction, not global cyan gloss;
- brushed steel: narrow directional highlights, dark flats, no uniform chrome;
- damp nylon: soft satin shoulder highlights, woven folds, no plastic shell;
- salt or sand: granular only at the focal ridge and camera-visible scale, broad compacted planes elsewhere.

Material distinction should come from response, not from covering every surface with texture.

## 6. Prompt assembly

Use this order:

```text
1. Subject/identity/action and setting
2. Style or medium when requested
3. Camera, spatial invariants, visual thesis, 3–7 dominant masses, focal route, and quiet zones
4. Source-medium-receiver light chain
5. Exposure/light-ratio limits and hero material interaction plus one or two supporting separations
6. Distance-based and non-focal information loss
7. Controlled-detail clean layer
8. Compact targeted avoid block
```

Compact module:

```text
One physically located dominant source controls the frame. Its direction, receiving surfaces, cast shadows, rim light, and reflections remain geometrically consistent. Atmospheric perspective appears through staged loss of contrast, chroma, edge definition, and internal detail with distance. Visible volumetric light appears only inside a localized participating medium, is shaped by credible apertures or occluders when bounded, is interrupted by solid objects, and fades outside the light path. Preserve one luminous focal zone, a readable shadow floor, broad calm masses, and material-specific highlights only where light angle and camera scale reveal them.
```

## 7. Output inspection and retry

Inspect the generated output before judging style:

1. Mark the source position.
2. Trace the path to every bright patch, rim, cast shadow, reflection, and visible shaft.
3. Reject any receiver that cannot see the source or a named bounce.
4. Check that solid objects interrupt light and that reflections obey surface orientation and wetness.
5. Check that atmospheric density has a location and a falloff.
6. Compare focal, support, and quiet-zone edge frequency.
7. Check material differences at thumbnail and close view.

If source, camera, or major receiver geometry is wrong, rebuild from a clean prompt. Do not paint isolated light patches onto a structurally inconsistent image. If only one local relationship fails and the base geometry is stable, edit that relationship while locking every unaffected invariant.

Use a single-variable retry record:

```text
Failure owner: source / camera / receiver / medium / exposure / material / density
Observed failure:
Invariant locks:
One changed variable:
Acceptance condition:
```
