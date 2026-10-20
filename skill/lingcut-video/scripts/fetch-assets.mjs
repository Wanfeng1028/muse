/**
 * 批量下载素材
 *
 * 用法: node fetch-assets.mjs <list.json> <outDir>
 * list.json: [{ "name": "char-老陈.png", "url": "https://oss.ytop.cc/..." }]
 */
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';

const list = JSON.parse(readFileSync(process.argv[2], 'utf8').replace(/^\uFEFF/, ''));
const dir = process.argv[3];
mkdirSync(dir, { recursive: true });

let ok = 0, fail = 0;
for (const { name, url } of list) {
  try {
    const r = await fetch(url);
    if (!r.ok) { console.log(`FAIL ${name}  HTTP ${r.status}`); fail++; continue; }
    const buf = Buffer.from(await r.arrayBuffer());
    writeFileSync(`${dir}/${name}`, buf);
    console.log(`OK   ${name}  ${(buf.length / 1024).toFixed(0)}KB`);
    ok++;
  } catch (e) {
    console.log(`ERR  ${name}  ${e.message}`); fail++;
  }
}
console.log(`\n完成: ${ok} 成功, ${fail} 失败`);
