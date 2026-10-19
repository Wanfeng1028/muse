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

// A "3D swivel teaser" clip. It plays back a sequence of pre-extracted JPEG
// frames one-to-one while a panel holding the frame rotates in on the Y axis
// at the start and rotates back out at the end, over a blurred and darkened
// background. Frames live at public/frames/frame_0001.jpg ... and the backdrop
// is public/frames/bg_image.png.
export const Pan3D: React.FC<Pan3DProps> = ({frameCount}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();

  // Map the timeline frame to a 1-indexed, zero-padded extracted frame.
  const clampedIndex = Math.min(Math.max(frame + 1, 1), frameCount);
  const frameSrc = staticFile(
    `frames/frame_${String(clampedIndex).padStart(4, '0')}.jpg`
  );

  // Duration of the swivel-in and swivel-out phases (in frames), capped so
  // short clips do not lose their middle section.
  const swivel = Math.max(1, Math.min(30, Math.round(frameCount * 0.2)));
  const swivelOutStart = Math.max(swivel, frameCount - swivel);

  const rotateY = interpolate(
    frame,
    [0, swivel, swivelOutStart, frameCount],
    [-78, 0, 0, 78],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.inOut(Easing.cubic),
    }
  );

  const scale = interpolate(
    frame,
    [0, swivel, swivelOutStart, frameCount],
    [0.72, 1, 1, 0.72],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.inOut(Easing.cubic),
    }
  );

  const opacity = interpolate(
    frame,
    [0, swivel * 0.6, swivelOutStart + swivel * 0.4, frameCount],
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
            src={frameSrc}
            style={{width, height, objectFit: 'cover', display: 'block'}}
          />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
