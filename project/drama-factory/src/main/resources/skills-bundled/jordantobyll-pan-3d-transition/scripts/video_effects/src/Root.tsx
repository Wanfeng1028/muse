import React from 'react';
import {Composition} from 'remotion';
import {Pan3D, Pan3DProps} from './Pan3D';
import {Montage, totalDurationInFrames} from './Montage';
import {FPS, HEIGHT, WIDTH} from './montageConfig';

// The Python script (insert_3d_transition.py) renders this composition via:
//   npx remotion render src/dynamic-index.ts Pan3D <out> --props '{...}'
// passing frameCount, playbackRate, width and height as props. We use
// calculateMetadata so the rendered clip matches the source video's
// dimensions and frame count exactly (segments are concatenated with -c copy,
// so dimensions must line up).
export const RemotionRoot: React.FC = () => {
  return (
    <>
    <Composition
      id="Pan3D"
      component={Pan3D}
      durationInFrames={300}
      fps={60}
      width={1920}
      height={1080}
      defaultProps={
        {
          frameCount: 300,
          playbackRate: 1,
          width: 1920,
          height: 1080,
        } as Pan3DProps
      }
      calculateMetadata={({props}) => ({
        durationInFrames: Math.max(1, Math.round(props.frameCount)),
        width: Math.round(props.width),
        height: Math.round(props.height),
        fps: 60,
      })}
    />
      <Composition
        id="DroneMontage"
        component={Montage}
        durationInFrames={totalDurationInFrames()}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};
