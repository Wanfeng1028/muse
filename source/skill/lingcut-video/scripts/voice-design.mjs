import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const KEY = readFileSync(`${SECRETS}/minimax.key`, 'utf8').trim();
const FF = FFMPEG;
const PY = PYTHON;
const OUT = `${PROJDIR}/_voice-test`;
mkdirSync(OUT, { recursive: true });

// 用中文自然语言描述音色
const DESIGNS = [
  { key: '老陈', prompt: '58岁中国男性，嗓音低沉沙哑，语速缓慢，带一点常年在灶台前熏出来的粗粝感和疲惫，说话克制不张扬', text: '记账。' },
  { key: '小满', prompt: '9岁中国女孩，声音清亮稚嫩，带一点怯生生的鼻音，轻声细语，句子末尾会微微发颤', text: '我没有钱。' },
];

for (const d of DESIGNS) {
  const r = await fetch('https://api.minimaxi.com/v1/voice_design', {
    method: 'POST',
    headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: d.prompt, preview_text: d.text }),
  });
  const j = await r.json();
  console.log(`\n=== ${d.key} ===`);
  console.log('返回字段:', Object.keys(j).join(', '));
  const hex = j.trial_audio || (j.data && j.data.audio);
  if (!hex) { console.log(JSON.stringify(j).slice(0, 300)); continue; }
  const mp3 = `${OUT}/design-${d.key}.mp3`;
  writeFileSync(mp3, Buffer.from(hex, 'hex'));
  const wav = `${OUT}/design-${d.key}.wav`;
  execFileSync(FF, ['-hide_banner', '-loglevel', 'error', '-y', '-i', mp3, '-ac', '1', '-ar', '16000', wav]);
  console.log('已保存', mp3);
  // 把非音频字段也打出来（可能有 voice_id）
  const meta = { ...j }; delete meta.trial_audio; delete meta.audio;
  console.log('其他字段:', JSON.stringify(meta).slice(0, 400));
  console.log(execFileSync(PY, [`${PROBEDIR}/voice_gender.py`, wav], { encoding: 'utf8' }));
}
