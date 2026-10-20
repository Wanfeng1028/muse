// Absolute scene frames at 60 fps. Fit these to the MEASURED narration takes (vo-manifest.json),
// not the other way round. Add a scene: append here, add its component in Video.tsx, add its blocks in layout.ts.
export const FPS = 60;
export const SCENES = [{id: 's1', from: 0, dur: 360}] as const;
export type SceneId = (typeof SCENES)[number]['id'];
export const TOTAL = SCENES[SCENES.length - 1].from + SCENES[SCENES.length - 1].dur;
export const sceneFrom = (id: SceneId) => SCENES.find((s) => s.id === id)!.from;
/** Crossfade length between scenes (frames). */
export const XF = 14;
