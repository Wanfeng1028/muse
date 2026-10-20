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

const OVERLAP = Math.round(TRANSITION * FPS);

// Per-segment frame counts and start positions. Consecutive segments overlap
// by OVERLAP frames so the outgoing shot swivels away while the incoming shot
// swivels in (a 3D card-flip transition).
const durations = SEGMENTS.map((s) => Math.round(s.duration * FPS));
const starts = durations.map((_, i) =>
  durations.slice(0, i).reduce((acc, d) => acc + d, 0) - i * OVERLAP
);

export const totalDurationInFrames = () =>
  durations.reduce((acc, d) => acc + d, 0) - (SEGMENTS.length - 1) * OVERLAP;

// Ken Burns: slow zoom + drift, alternating direction per still so the reel
// doesn't feel mechanical.
const KenBurnsImg: React.FC<{src: string; duration: number; index: number}> = ({
  src,
  duration,
  index,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const dir = index % 2 === 0 ? 1 : -1;

  const scale = interpolate(frame, [0, duration], [1.05, 1.18], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const translateX = interpolate(frame, [0, duration], [0, dir * -40], {
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
        transform: `scale(${scale}) translateX(${translateX}px)`,
      }}
    />
  );
};

// Wraps a segment with the 3D swivel: rotates in from the left on entry (unless
// it's the first segment) and out to the right on exit (unless it's the last).
const SwivelSegment: React.FC<{
  segment: Segment;
  duration: number;
  index: number;
  isFirst: boolean;
  isLast: boolean;
}> = ({segment, duration, index, isFirst, isLast}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();

  const enterRot = isFirst
    ? 0
    : interpolate(frame, [0, OVERLAP], [-92, 0], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
        easing: Easing.out(Easing.cubic),
      });
  const exitRot = isLast
    ? 0
    : interpolate(frame, [duration - OVERLAP, duration], [0, 92], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
        easing: Easing.in(Easing.cubic),
      });
  const rotateY = enterRot + exitRot;

  // Fake lighting: faces angled away from camera darken slightly.
  const brightness = interpolate(Math.abs(rotateY), [0, 92], [1, 0.45], {
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
            transform: `rotateY(${rotateY}deg)`,
            transformOrigin: 'center center',
            filter: `brightness(${brightness})`,
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
            <KenBurnsImg src={segment.src} duration={duration} index={index} />
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
          from={starts[i]}
          durationInFrames={durations[i]}
          // Later segments render on top so the incoming swivel covers the
          // outgoing one during the overlap.
          layout="none"
        >
          <SwivelSegment
            segment={segment}
            duration={durations[i]}
            index={i}
            isFirst={i === 0}
            isLast={i === SEGMENTS.length - 1}
          />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
