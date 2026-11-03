// Edit this file to change the drone montage: segment order, durations, and
// where each video clip is trimmed from. Durations are in seconds; the
// composition converts them to frames at FPS. Used by Montage.tsx / the
// "DroneMontage" composition in Root.tsx.

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

// Length of the 3D swivel transition where two segments overlap (seconds).
export const TRANSITION = 0.6;

export type Segment =
  | {type: 'video'; src: string; duration: number; trimStart: number}
  | {type: 'image'; src: string; duration: number};

// Order is a craft choice: open on the strongest aerial move (a video),
// weave the stills through, drop the second video in the middle as an anchor.
export const SEGMENTS: Segment[] = [
  {type: 'video', src: 'montage/DJI_0281.MP4', duration: 8, trimStart: 1},
  {type: 'image', src: 'montage/DJI_0278.JPG', duration: 3.5},
  {type: 'image', src: 'montage/DJI_0279.JPG', duration: 3.5},
  {type: 'image', src: 'montage/DJI_0283.JPG', duration: 3.5},
  {type: 'video', src: 'montage/DJI_0282.MP4', duration: 8, trimStart: 0.5},
  {type: 'image', src: 'montage/DJI_0284.JPG', duration: 3.5},
  {type: 'image', src: 'montage/DJI_0285.JPG', duration: 3.5},
  {type: 'image', src: 'montage/DJI_0286.JPG', duration: 3.5},
  {type: 'image', src: 'montage/DJI_0287.JPG', duration: 3.5},
];
