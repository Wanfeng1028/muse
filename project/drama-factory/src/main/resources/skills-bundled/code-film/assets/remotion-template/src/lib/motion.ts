import {Easing, interpolate, spring} from 'remotion';
import {theme} from '../theme';

export const ease = {
  out: Easing.bezier(0.16, 1, 0.3, 1),
  soft: Easing.bezier(0.33, 1, 0.68, 1),
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
  in: Easing.bezier(0.7, 0, 0.84, 0),
  linear: (t: number) => t,
};

export const springs = {
  smooth: {damping: 200},
  gentle: {damping: 20, stiffness: 120, mass: 1},
  bouncy: {damping: 10, stiffness: 140, mass: 0.8},
  heavy: {damping: 30, stiffness: 80, mass: 2},
};

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export const mix = (a: number, b: number, t: number) => a + (b - a) * t;

/** 从 start 帧开始，duration 帧内从 0 走到 1，带缓动，两端夹住。 */
export const progress = (frame: number, start: number, duration: number, easing: (t: number) => number = ease.out) =>
  interpolate(frame, [start, start + Math.max(1, duration)], [0, 1], {
    easing,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

/** 从 start 帧开始的弹簧，0 到 1（可能略微超过 1）。 */
export const springAt = (frame: number, fps: number, start: number, config: Partial<typeof springs.gentle> = springs.gentle) =>
  spring({frame: Math.max(0, frame - start), fps, config});

/** 镜头末尾的退场：返回 1 到 0 的可见度。 */
export const exitFade = (frame: number, shotDuration: number, len: number = theme.motion.exit) =>
  1 - progress(frame, shotDuration - len, len, ease.in);

/** 缩放按对数插值，推拉的速度感才均匀。 */
export const logZoom = (t: number, from: number, to: number) => Math.exp(Math.log(from) + (Math.log(to) - Math.log(from)) * t);

/** 定格感：每 every 帧才更新一次。 */
export const stepped = (frame: number, every = 2) => Math.floor(frame / every) * every;

export const smoothstep = (edge0: number, edge1: number, x: number) => {
  const t = clamp01((x - edge0) / (edge1 - edge0));
  return t * t * (3 - 2 * t);
};
