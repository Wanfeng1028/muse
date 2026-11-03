import {Config} from '@remotion/cli/config';

Config.setEntryPoint('./src/index.ts');
// png 比 jpeg 慢一些，但保证输出 yuv420p（jpeg 会得到全范围的 yuvj420p，微信等播放器会黑屏）
Config.setVideoImageFormat('png');
Config.setCodec('h264');
Config.setPixelFormat('yuv420p');
Config.setCrf(18);
Config.setOverwriteOutput(true);
// Windows 上 3D 需要 angle；Linux 服务器改成 'angle-egl' 或 'swangle'
Config.setChromiumOpenGlRenderer('angle');
