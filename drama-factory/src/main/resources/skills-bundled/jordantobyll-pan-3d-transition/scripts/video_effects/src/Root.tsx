import React from 'react';
import {Composition} from 'remotion';
import {Pan3D, Pan3DProps} from './Pan3D';
import {Montage, getTotalFrames} from './Montage';
import {FPS, HEIGHT, WIDTH} from './montageConfig';

// Pan3D is rendered programmatically (e.g. by an external ffmpeg/insert
// pipeline) via:
//   npx remotion render src/dynamic-index.ts Pan3D <out> --props '{...}'
// The caller passes frameCount / playbackRate / width / height. We rely on
// calculateMetadata so the rendered clip's size and length match the source
// video exactly, which lets the segments be concatenated with stream copy.
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
        durationInFrames={getTotalFrames()}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};
