import raw from './storyboard.json';

export type SfxAlign = 'start' | 'peak' | 'end';

export type SfxEvent = {
  at: number;
  sfx: string;
  volume?: number;
  rate?: number;
  align?: SfxAlign;
};

export type Shot = {
  id: string;
  from: number;
  duration: number;
  scene: string;
  section?: string;
  intensity?: number;
  text?: string[];
  transitionOut?: string;
  props?: Record<string, unknown>;
  events?: SfxEvent[];
  note?: string;
  overlapOk?: boolean;
  gapOk?: boolean;
  longOk?: boolean;
};

export type StoryboardMeta = {
  title: string;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  bpm?: number;
  beatOffsetFrames?: number;
  music?: string;
  musicVolume?: number;
  musicStartFrame?: number;
};

export type Storyboard = {meta: StoryboardMeta; shots: Shot[]};

export const storyboard = raw as unknown as Storyboard;
