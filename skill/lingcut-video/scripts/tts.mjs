import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * MiniMax TTS 批量配音
 *
 * 用法: node tts.mjs <lines.json> <outDir>
 * lines.json: [{ "name": "line05-小满", "text": "我没有钱。", "voice": "Chinese (Mandarin)_Soft_Girl", "speed": 0.95 }]
 *
 * 注意:
 *  - 必须用 https://api.minimaxi.com ，api.minimax.io 不认国内 key
 *  - 返回的 data.audio 是 hex 编码的 MP3
 *  - 音色列表: POST /v1/get_voice  {voice_type:"all"}
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const BASE = 'https://api.minimaxi.com';
const KEY = (process.env.MINIMAX_KEY
  || readFileSync(`${SECRETS}/minimax.key`, 'utf8')).trim();

const [, , linesFile, outDir] = process.argv;
const lines = JSON.parse(readFileSync(linesFile, 'utf8').replace(/^\uFEFF/, ''));
mkdirSync(outDir, { recursive: true });

for (const l of lines) {
  const body = {
    model: l.model || 'speech-2.8-turbo',
    text: l.text,
    stream: false,
    voice_setting: { voice_id: l.voice, speed: l.speed ?? 1, vol: l.vol ?? 1, pitch: l.pitch ?? 0 },
    audio_setting: { sample_rate: 32000, bitrate: 128000, format: 'mp3', channel: 1 },
  };
  try {
    const r = await fetch(BASE + '/v1/t2a_v2', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + KEY, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    const code = j?.base_resp?.status_code;
    if (code !== 0) { console.log(`ERR  ${l.name}  MiniMax ${code}: ${j?.base_resp?.status_msg}`); continue; }
    const buf = Buffer.from(j.data.audio, 'hex');
    writeFileSync(`${outDir}/${l.name}.mp3`, buf);
    console.log(`OK   ${l.name}  ${(buf.length / 1024).toFixed(0)}KB  ${j.extra_info.audio_length}ms  voice=${l.voice}`);
  } catch (e) {
    console.log(`ERR  ${l.name}  ${e.message}`);
  }
}
