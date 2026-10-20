// The film's frame rate, defined once. Root registers every composition with it; data helpers use it only as a
// default. Inside components, read fps from useVideoConfig() (official Remotion rule).
export const FPS = 30

export function toFrames(seconds: number, fps: number = FPS): number {
  return Math.round(seconds * fps)
}
