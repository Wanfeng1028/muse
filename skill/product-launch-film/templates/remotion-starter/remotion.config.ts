import {Config} from '@remotion/cli/config';

// PNG frames -> standard limited-range yuv420p H.264. JPEG frames give full-range yuvj420p,
// which some players and uploaders show washed out.
Config.setVideoImageFormat('png');
Config.setOverwriteOutput(true);
Config.setEntryPoint('./src/index.ts');
