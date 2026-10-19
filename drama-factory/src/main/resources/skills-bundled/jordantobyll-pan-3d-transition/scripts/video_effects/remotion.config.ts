import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
// Frames used by the Pan3D teaser are extracted into public/frames before the
// render is started, so point Remotion at the local public directory.
Config.setPublicDir('public');
