/**
 * ★ 所有脚本的共享配置
 *
 * 安装后**只需要改这一个文件**，其它脚本自动生效。
 *
 * 优先级：环境变量 > 本文件的默认值
 *   LINGCUT_PROJECT   项目根目录（放剧本/成片的地方）
 *   LINGCUT_PROFILE   Playwright 的 Chrome profile 目录
 *   LINGCUT_CHROME    Chromium 可执行文件
 *   LINGCUT_PW        playwright-core 的 index.js 路径
 *   LINGCUT_FFMPEG    ffmpeg 可执行文件
 *   LINGCUT_SECRETS   凭据目录（默认 <项目>/.secrets）
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';

const env = process.env;

// ── 1. 项目根目录 ──────────────────────────────
// 优先环境变量；否则用「脚本所在目录的上一级」作为 skill 目录，项目另找一个
export const PROJ = env.LINGCUT_PROJECT
  || path.join(os.homedir(), 'Desktop', '<WORKSPACE_NAME>', 'projects', '我的片子');

// ── 2. tools 目录（ffmpeg / chrome-profile / secrets 都放这儿）──
export const TOOLS = env.LINGCUT_TOOLS
  || path.join(path.dirname(PROJ), '..', '.tools');

// ── 3. Playwright / Chromium ───────────────────
function findPw() {
  if (env.LINGCUT_PW && fs.existsSync(env.LINGCUT_PW)) return env.LINGCUT_PW;
  const cands = [
    path.join(os.homedir(), '.dsh', 'profiles', 'desktop', 'node_modules', 'playwright-core', 'index.js'),
    path.join(process.cwd(), 'node_modules', 'playwright-core', 'index.js'),
  ];
  for (const c of cands) if (fs.existsSync(c)) return c;
  return cands[0];
}
export const PW = pathToFileURL(findPw()).href;

function findChrome() {
  if (env.LINGCUT_CHROME && fs.existsSync(env.LINGCUT_CHROME)) return env.LINGCUT_CHROME;
  const base = path.join(os.homedir(), 'AppData', 'Local', 'ms-playwright');
  if (fs.existsSync(base)) {
    for (const d of fs.readdirSync(base)) {
      if (!d.startsWith('chromium-')) continue;
      for (const rel of ['chrome-win64/chrome.exe', 'chrome-win/chrome.exe', 'chrome-linux/chrome', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium']) {
        const p = path.join(base, d, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return path.join(base, 'chromium-1234', 'chrome-win64', 'chrome.exe');
}
export const CHROME = findChrome();

export const PROFILE = env.LINGCUT_PROFILE || path.join(TOOLS, 'chrome-profile');

// ── 4. ffmpeg ──────────────────────────────────
function findFfmpeg() {
  if (env.LINGCUT_FFMPEG && fs.existsSync(env.LINGCUT_FFMPEG)) return env.LINGCUT_FFMPEG;
  const cands = [
    path.join(TOOLS, 'ffmpeg.exe'),
    path.join(TOOLS, 'ffmpeg'),
    'ffmpeg',
  ];
  for (const c of cands) if (c === 'ffmpeg' || fs.existsSync(c)) return c;
  return 'ffmpeg';
}
export const FFMPEG = findFfmpeg();

// ── 5. 凭据 ────────────────────────────────────
export const SECRETS = env.LINGCUT_SECRETS || path.join(PROJ, '.secrets');

// ── 6. 常用子目录 ──────────────────────────────
export const DIR = {
  script:    path.join(PROJ, '00-剧本'),
  chars:     path.join(PROJ, '01-角色'),
  scenes:    path.join(PROJ, '02-场景'),
  props:     path.join(PROJ, '03-道具'),
  images:    path.join(PROJ, '04-逐镜图'),
  videos:    path.join(PROJ, '05-逐镜视频'),
  audio:     path.join(PROJ, '06-音频'),
  chapters:  path.join(PROJ, '07-成片'),
  volumes:   path.join(PROJ, '08-三卷'),
  film:      path.join(PROJ, '09-全片'),
  editdesk:  path.join(PROJ, '★剪辑工作台'),
  latest:    path.join(PROJ, '★网站最新'),
  tmp:       path.join(PROJ, '_tmp'),
};

// ── 7. 启动浏览器的统一函数 ────────────────────
export async function launch({ headless = true } = {}) {
  const m = await import(PW);
  const chromium = m.chromium || m.default?.chromium;
  const ctx = await chromium.launchPersistentContext(PROFILE, {
    headless,
    executablePath: CHROME,
    viewport: { width: 1440, height: 900 },
    args: ['--no-sandbox'],
    locale: 'zh-CN',
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  return { ctx, page };
}

/** 关掉引导弹窗（注入引擎前必须先关） */
export async function dismissModals(page, times = 5) {
  for (let i = 0; i < times; i++) {
    const hit = await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')]
        .find(x => /^(开始使用|我知道了|知道了|关闭)$/.test((x.textContent || '').trim()));
      if (b) { b.click(); return true; }
      return false;
    });
    if (!hit) break;
    await page.waitForTimeout(1000);
  }
}

/** 注入引擎：遍历 React fiber 找 nodeMap instanceof Map && addNode */
export async function injectEngine(page, waitMs = 13000) {
  await page.waitForTimeout(waitMs);
  await dismissModals(page);
  const r = await page.evaluate(() => {
    const seen = new Set(); let eng = null;
    function walk(o, d) {
      if (!o || d > 8 || seen.has(o) || eng) return;
      try { seen.add(o); } catch (e) { return; }
      try { if (o.nodeMap instanceof Map && typeof o.addNode === 'function') { eng = o; return; } } catch (e) {}
      for (const k of ['stateNode','child','sibling','return','memoizedState','memoizedProps','pendingProps','ref','current'])
        { try { walk(o[k], d + 1); } catch (e) {} }
      if (o.memoizedState) { let h = o.memoizedState, n = 0;
        while (h && n++ < 60 && !eng) { try { walk(h.memoizedState, d + 1); } catch (e) {} h = h.next; } }
    }
    for (const el of [...document.querySelectorAll('*')].slice(0, 5000)) {
      for (const k in el) if (k.startsWith('__react')) walk(el[k], 0);
      if (eng) break;
    }
    if (eng) { window.__eng = eng; return { ok: true, nodes: eng.nodeMap.size }; }
    return { ok: false };
  });
  if (!r.ok) throw new Error('引擎注入失败（检查是否有关不掉的弹窗 / 是否已登录）');
  return r;
}

/** 拿 cookie 头 */
export async function cookieHeader(ctx) {
  return { Cookie: (await ctx.cookies()).map(c => c.name + '=' + c.value).join('; ') };
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));
export const CANVAS_URL = id => `https://www.lingcut.cn/canvas/${id}`;
export const API = id => `https://www.lingcut.cn/api/projects/${id}`;
export const TASKS = id => `https://www.lingcut.cn/api/tasks/active/list?projectId=${id}`;
export const PROJECT_ID = env.LINGCUT_PROJECT_ID || '<ID>';

// ── 8. 给脚本用的辅助变量（这样脚本只需要一行 import）──
export const WORKDIR = path.resolve(TOOLS, '..');
export const PROJDIR = path.dirname(PROJ);
export const PROBEDIR = path.join(WORKDIR, '.probe');
export const SHOTDIR = path.join(WORKDIR, 'browser-screenshots');
export const LIB = path.join(PROJDIR, '_libtv-audio');
export const HOMEDIR = os.homedir().replace(/\\/g, '/');
export const PYTHON = env.LINGCUT_PYTHON || 'python';
