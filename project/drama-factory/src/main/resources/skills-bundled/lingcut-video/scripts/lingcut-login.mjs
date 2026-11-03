import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * LingCut 自动登录（登录态过期时用）
 *
 * 用法: node lingcut-login.mjs
 * 凭据: .secrets/lingcut.json
 *
 * 登录后登录态存在 .probe/chrome-profile，后续 lingcut-*.mjs 直接复用。
 */
import fs from 'node:fs';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const CRED = JSON.parse(fs.readFileSync(`${SECRETS}/lingcut.json`, 'utf8'));

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: true, executablePath: CHROME, viewport: { width: 1440, height: 900 },
  args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'], locale: 'zh-CN',
});
const page = ctx.pages()[0] || await ctx.newPage();

async function status(tag) {
  const ck = await ctx.cookies();
  const H = { Cookie: ck.map(c => c.name + '=' + c.value).join('; ') };
  const r = await fetch('https://www.lingcut.cn/api/projects/<ID>', { headers: H });
  let ok = false, info = '';
  try { const j = await r.json(); info = (j && j.error) ? j.error : ('nodes=' + (JSON.parse(j.canvas_data || j.project?.canvas_data || '{}').nodes || []).length); ok = r.status === 200; }
  catch (e) { info = String(e).slice(0, 50); }
  console.log(`  [${tag}] HTTP ${r.status}  cookie=${ck.length}  ${info}`);
  return ok;
}

await page.goto('https://www.lingcut.cn/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(6000);

if (await status('登录前')) {
  console.log('✅ 已经是登录状态，无需重新登录');
  await ctx.close();
  process.exit(0);
}

// 打开登录弹窗：先试自动弹出的，再试点顶部「登录」
const setVal = `(el, v) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}`;

let opened = false;
for (let i = 0; i < 6; i++) {
  const hasPwd = await page.evaluate(() => !!document.querySelector('input[type=password]'));
  if (hasPwd) { opened = true; break; }
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button,a,div,span')]
      .find(x => /^(登录|立即登录|登录\/注册)$/.test((x.textContent || '').trim()));
    if (b) b.click();
  });
  await page.waitForTimeout(2000);
}
console.log('登录弹窗:', opened ? '已打开' : '未检测到（仍尝试填写）');

// 填表（用 native setter 触发 React）
const filled = await page.evaluate((setterSrc) => {
  const setVal = eval(setterSrc);
  const ins = [...document.querySelectorAll('input')].filter(i => i.type !== 'hidden' && i.offsetParent !== null);
  const pwd = ins.find(i => i.type === 'password');
  const txt = ins.filter(i => i.type === 'text' || i.type === 'email' || !i.type);
  return { count: ins.length, types: ins.map(i => i.type + ':' + (i.placeholder || '')), hasPwd: !!pwd, txtCount: txt.length };
}, setVal);
console.log('  可见 input:', JSON.stringify(filled));

const ok = await page.evaluate(({ setterSrc, acct, pwd }) => {
  const setVal = eval(setterSrc);
  const ins = [...document.querySelectorAll('input')].filter(i => i.type !== 'hidden' && i.offsetParent !== null);
  const pwdEl = ins.find(i => i.type === 'password');
  const txtEls = ins.filter(i => i !== pwdEl && (i.type === 'text' || i.type === 'email' || !i.type));
  if (!pwdEl || !txtEls.length) return 'no-inputs';
  setVal(txtEls[0], acct);
  setVal(pwdEl, pwd);
  // 勾选所有未勾的 checkbox（用户协议）
  [...document.querySelectorAll('input[type=checkbox]')].forEach(c => { if (!c.checked) c.click(); });
  [...document.querySelectorAll('[role=checkbox],[class*=checkbox]')].forEach(c => {
    const t = (c.textContent || '') + (c.className || '');
    if (/agree|协议|未勾/i.test(t)) { try { c.click(); } catch (e) {} }
  });
  return 'filled';
}, { setterSrc: setVal, acct: CRED.account, pwd: CRED.password });
console.log('  填表:', ok);
await page.waitForTimeout(1200);

// 点登录
const clicked = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => /^(登录|立即登录|登 录)$/.test((b.textContent || '').trim()));
  if (btns.length) { btns[btns.length - 1].click(); return 'clicked'; }
  return 'no-button';
});
console.log('  提交:', clicked);

for (let i = 0; i < 10; i++) {
  await page.waitForTimeout(3000);
  if (await status(`第${i + 1}次检查`)) { console.log('\n🎉 登录成功'); await ctx.close(); process.exit(0); }
}
console.log('\n❌ 登录失败，请人工检查 .secrets/lingcut.json 或验证码');
await page.screenshot({ path: `${PROJ}/_tmp/login-fail.png` });
await ctx.close();
process.exit(1);
