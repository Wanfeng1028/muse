import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {FPS, SEGMENTS, Segment, TRANSITION} from './montageConfig';

// How many frames two neighbouring segments overlap during the swivel.
const SWIVEL_FRAMES = Math.round(TRANSITION * FPS);

// Convert the per-segment second durations into frames.
const segmentFrames = SEGMENTS.map((s) => Math.round(s.duration * FPS));

// Each segment starts after all previous ones, minus one swivel per boundary.
const segmentOffsets = segmentFrames.map((_, i) =>
  segmentFrames.slice(0, i).reduce((sum, n) => sum + n, 0) - i * SWIVEL_FRAMES
);

export const getTotalFrames = () =>
  segmentFrames.reduce((sum, n) => sum + n, 0) -
  (SEGMENTS.length - 1) * SWIVEL_FRAMES;

// Slow Ken Burns push for still photos. Direction alternates per index so the
// montage does not feel like the same move repeated.
const DriftingStill: React.FC<{src: string; frames: number; index: number}> = ({
  src,
  frames,
  index,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const drift = index % 2 === 0 ? -40 : 40;

  const zoom = interpolate(frame, [0, frames], [1.05, 1.18], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const offsetX = interpolate(frame, [0, frames], [0, drift], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <Img
      src={staticFile(src)}
      style={{
        width,
        height,
        objectFit: 'cover',
        transform: `scale(${zoom}) translateX(${offsetX}px)`,
      }}
    />
  );
};

// One card in the montage. It flips in on entry (except the first) and flips
// out on exit (except the last), producing the 3D swivel look.
const SwivelCard: React.FC<{
  segment: Segment;
  frames: number;
  index: number;
  isFirst: boolean;
  isLast: boolean;
}> = ({segment, frames, index, isFirst, isLast}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();

  const entryAngle = isFirst
    ? 0
    : interpolate(frame, [0, SWIVEL_FRAMES], [-92, 0], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
        easing: Easing.out(Easing.cubic),
      });

  const exitAngle = isLast
    ? 0
    : interpolate(frame, [frames - SWIVEL_FRAMES, frames], [0, 92], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
        easing: Easing.in(Easing.cubic),
      });

  const angle = entryAngle + exitAngle;

  // Simple fake lighting: the more the card turns away, the darker it gets.
  const shade = interpolate(Math.abs(angle), [0, 92], [1, 0.45], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div style={{perspective: 2000, width, height}}>
        <div
          style={{
            width,
            height,
            transformStyle: 'preserve-3d',
            transform: `rotateY(${angle}deg)`,
            transformOrigin: 'center center',
            filter: `brightness(${shade})`,
            overflow: 'hidden',
            backfaceVisibility: 'hidden',
          }}
        >
          {segment.type === 'video' ? (
            <OffthreadVideo
              src={staticFile(segment.src)}
              trimBefore={Math.round(segment.trimStart * FPS)}
              muted
              style={{width, height, objectFit: 'cover'}}
            />
          ) : (
            <DriftingStill src={segment.src} frames={frames} index={index} />
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const Montage: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {SEGMENTS.map((segment, i) => (
        <Sequence
          key={i}
          from={segmentOffsets[i]}
          durationInFrames={segmentFrames[i]}
          layout="none"
        >
          <SwivelCard
            segment={segment}
            frames={segmentFrames[i]}
            index={i}
            isFirst={i === 0}
            isLast={i === SEGMENTS.length - 1}
          />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
