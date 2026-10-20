import {Easing, interpolate} from 'remotion';
import type {CSSProperties} from 'react';

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
/** Calm ease-out for entrances; ease-in-out for camera/slide moves. No bouncy springs. */
export const OUT = Easing.bezier(0.22, 0.61, 0.12, 1);
export const INOUT = Easing.bezier(0.45, 0, 0.25, 1);

export const ease = (frame: number, from: number, dur: number, easing = OUT) =>
	interpolate(frame, [from, from + dur], [0, 1], {...clamp, easing});
export const keys = (frame: number, input: number[], output: number[], easing = INOUT) =>
	interpolate(frame, input, output, {...clamp, easing});
export const rise = (p: number, d = 14): CSSProperties => ({opacity: p, transform: `translateY(${(1 - p) * d}px)`});

/** Characters of a `len`-char string typed by `frame` (typing starts at `start`, `cpf` chars/frame). */
export const typed = (len: number, frame: number, start: number, cpf = 1.4) => Math.max(0, Math.min(len, Math.floor((frame - start) * cpf)));
export const typedEnd = (len: number, start: number, cpf = 1.4) => start + Math.ceil(len / cpf);
