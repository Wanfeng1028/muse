import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
// The Python script extracts frames into public/frames at render time.
Config.setPublicDir('public');
