import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export type Pan3DProps = {
  frameCount: number;
  playbackRate: number;
  width: number;
  height: number;
};

// 3D "swivel teaser": plays the extracted frame sequence 1:1 while the panel
// rotates in on the Y axis at the start and rotates back out at the end, over a
// blurred, dimmed copy of the background image. Frames are written by the
// Python script to public/frames/frame_0001.jpg ... and a background to
// public/frames/bg_image.png.
export const Pan3D: React.FC<Pan3DProps> = ({frameCount}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();

  // Timeline frame -> 1-indexed, zero-padded extracted frame.
  const imageIndex = Math.min(Math.max(frame + 1, 1), frameCount);
  const src = staticFile(`frames/frame_${String(imageIndex).padStart(4, '0')}.jpg`);

  // Length of the swivel-in / swivel-out segments (in frames).
  const edge = Math.max(1, Math.min(30, Math.round(frameCount * 0.2)));
  const outStart = Math.max(edge, frameCount - edge);

  const rotateY = interpolate(
    frame,
    [0, edge, outStart, frameCount],
    [-78, 0, 0, 78],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.inOut(Easing.cubic),
    }
  );

  const scale = interpolate(
    frame,
    [0, edge, outStart, frameCount],
    [0.72, 1, 1, 0.72],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.inOut(Easing.cubic),
    }
  );

  const opacity = interpolate(
    frame,
    [0, edge * 0.6, outStart + edge * 0.4, frameCount],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <AbsoluteFill>
        <Img
          src={staticFile('frames/bg_image.png')}
          style={{
            width,
            height,
            objectFit: 'cover',
            filter: 'brightness(0.4) blur(8px)',
          }}
        />
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          justifyContent: 'center',
          alignItems: 'center',
          perspective: 1600,
        }}
      >
        <div
          style={{
            transform: `rotateY(${rotateY}deg) scale(${scale})`,
            opacity,
            boxShadow: '0 40px 120px rgba(0,0,0,0.6)',
          }}
        >
          <Img
            src={src}
            style={{width, height, objectFit: 'cover', display: 'block'}}
          />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
