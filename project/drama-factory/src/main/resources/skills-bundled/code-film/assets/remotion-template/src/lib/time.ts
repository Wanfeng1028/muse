import {storyboard} from '../storyboard';

const {fps, bpm = 120, beatOffsetFrames = 0} = storyboard.meta;

export const FPS = fps;
export const framesPerBeat = (fps * 60) / bpm;

/** 第 n 拍所在的帧（从 beatOffsetFrames 起算，n 可以是小数，比如 0.5 表示半拍）。 */
export const beat = (n: number) => Math.round(beatOffsetFrames + n * framesPerBeat);

/** n 拍的时长（帧）。 */
export const beats = (n: number) => Math.round(n * framesPerBeat);

/** 秒转帧。 */
export const sec = (s: number) => Math.round(s * fps);
