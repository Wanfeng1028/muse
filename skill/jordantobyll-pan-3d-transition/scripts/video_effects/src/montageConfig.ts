// Montage configuration for the DroneMontage composition.
//
// Edit SEGMENTS to change which drone clips / stills appear, their order,
// their durations, and where each video is trimmed from. All durations are in
// seconds and converted to frames using FPS inside Montage.tsx.

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

// Duration in seconds of the 3D swivel where two consecutive segments overlap.
export const TRANSITION = 0.6;

export type Segment =
  | {type: 'video'; src: string; duration: number; trimStart: number}
  | {type: 'image'; src: string; duration: number};

// Order is an editorial decision: lead with the strongest aerial move (video),
// weave the stills through, and drop a second video in the middle as an anchor.
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
