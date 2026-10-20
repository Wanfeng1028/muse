export const FPS = 30;

const durations = [
  { id: "S1", name: "Meet the product", dur: 90 },
  { id: "S2", name: "Idea to launch", dur: 150 },
  { id: "S3", name: "Make it yours", dur: 90 },
] as const;

export type SceneId = (typeof durations)[number]["id"];
export const SCENES = durations.map((scene, index) => ({
  ...scene,
  from: durations.slice(0, index).reduce((sum, previous) => sum + previous.dur, 0),
}));
export const TOTAL_FRAMES = durations.reduce((sum, scene) => sum + scene.dur, 0);

export const CUES = {
  S1: { mark: 4, headline: 8, wipe: 54, meter: 66 },
  S2: { headline: 4, chips: [25, 29, 33], fill: 36, complete: 92, merge: 116 },
  S3: { lockup: 4, url: 22 },
} as const satisfies Record<SceneId, Record<string, number | readonly number[]>>;
