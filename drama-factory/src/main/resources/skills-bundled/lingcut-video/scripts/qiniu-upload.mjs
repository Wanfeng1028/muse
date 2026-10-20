/**
 * 七牛云上传（LingCut 的 OSS）
 *
 * 用法: node qiniu-upload.mjs <jobs.json>
 * jobs.json: [{ "name":"line05", "localFile":"C:/.../a.mp3", "key":"lingcut/audios/...mp3",
 *               "token":"<upload-token>", "domain":"https://oss.ytop.cc", "mime":"audio/mpeg" }]
 *
 * token 获取（在页面里，需要登录态）:
 *   POST /api/system/qiniu/upload-token   {key}  ->  {token, domain}
 *   key 格式: lingcut/{images|videos|audios}/<Date.now()>-<rand8>.<ext>
 *
 * ⚠️ 上传域名必须是 https://up-z1.qiniup.com
 *    （bucket duanju1019 在 z1 区；用通用域名会报 incorrect region）
 */
import { readFileSync } from 'node:fs';

const jobs = JSON.parse(readFileSync(process.argv[2], 'utf8').replace(/^\uFEFF/, ''));
const UPLOAD = 'https://up-z1.qiniup.com';

for (const j of jobs) {
  try {
    const buf = readFileSync(j.localFile);
    const form = new FormData();
    form.append('token', j.token);
    form.append('key', j.key);
    form.append('file', new Blob([buf], { type: j.mime || 'application/octet-stream' }), j.key.split('/').pop());
    const r = await fetch(UPLOAD, { method: 'POST', body: form });
    const txt = await r.text();
    if (!r.ok) { console.log(`FAIL ${j.name}  ${r.status}  ${txt.slice(0, 150)}`); continue; }
    const url = `${j.domain}/${j.key}`;
    const head = await fetch(url, { method: 'HEAD' });
    console.log(`OK   ${j.name}  ${url}  verify=${head.status} ${head.headers.get('content-type')}`);
  } catch (e) {
    console.log(`ERR  ${j.name}  ${e.message}`);
  }
}
