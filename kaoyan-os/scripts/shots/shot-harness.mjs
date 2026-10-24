// shot-harness.mjs：kaoyan-os 视觉验收截图 harness。
// route 注册顺序铁律：静态路由先注册、/api 路由后注册（后注册优先）。

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..', '..');
const APPS_SERVER = path.join(repoRoot, 'apps', 'server');
const WEB_DIST = path.join(repoRoot, 'apps', 'web', 'dist');

function resolvePlaywright() {
  const req = createRequire(import.meta.url);
  try {
    return req('playwright-core');
  } catch (_) {}
  if (process.env.PLAYWRIGHT_CORE_PATH) {
    try {
      return req(process.env.PLAYWRIGHT_CORE_PATH);
    } catch (_) {}
  }
  try {
    return req('/home/hatch/workspace/muse-build/shot/node_modules/playwright-core');
  } catch (_) {}
  throw new Error('找不到 playwright-core');
}

function spawnServer({ port, dbPath }) {
  return spawn('node', ['dist/index.js'], {
    cwd: APPS_SERVER,
    env: { ...process.env, PORT: String(port), DATABASE_PATH: dbPath },
    stdio: 'ignore'
  });
}

function waitForHealth(port, { timeoutMs = 60000, intervalMs = 500 } = {}) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      if (Date.now() - start > timeoutMs) {
        reject(new Error(`server not ready: ${port} 在 ${timeoutMs}ms 内未就绪`));
        return;
      }
      const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
        if (res.statusCode === 200) {
          console.log('[harness] server ready on port', port);
          resolve();
        } else {
          setTimeout(check, intervalMs);
        }
      });
      req.on('error', () => {
        setTimeout(check, intervalMs);
      });
    };
    check();
  });
}

function apiRequest(port, method, apiPath, { token, body, contentType, cookie } = {}) {
  return new Promise((resolve, reject) => {
    const headers = {};
    let payload = undefined;

    if (cookie) {
      headers['cookie'] = cookie;
    } else if (token) {
      headers['cookie'] = `kaoyan_session=${token}`;
    }

    if (body !== undefined && body !== null) {
      if (typeof body === 'object') {
        payload = JSON.stringify(body);
        headers['content-type'] = 'application/json';
      } else if (typeof body === 'string') {
        payload = body;
        headers['content-type'] = contentType || 'application/json';
      }
    }

    const req = http.request(
      { hostname: '127.0.0.1', port, path: apiPath, method, headers },
      (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf-8');
          let json = null;
          try { json = JSON.parse(text); } catch (_) {}
          resolve({ status: res.statusCode, headers: res.headers, text, json });
        });
      }
    );
    req.on('error', reject);
    if (payload !== undefined) req.write(payload);
    req.end();
  });
}

async function registerAndLogin(port, username, password) {
  const reg = await apiRequest(port, 'POST', '/api/auth/register', { body: { username, password } });
  if (reg.status !== 201 && reg.status !== 409) {
    throw new Error(`注册失败，状态码 ${reg.status}`);
  }

  const login = await apiRequest(port, 'POST', '/api/auth/login', { body: { username, password } });
  if (login.status < 200 || login.status >= 300) {
    throw new Error(`登录失败，状态码 ${login.status}`);
  }

  const setCookie = login.headers['set-cookie'];
  const cookieArr = Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : [];
  let token = null;
  for (const c of cookieArr) {
    const m = c.match(/kaoyan_session=([^;]+)/);
    if (m) { token = m[1]; break; }
  }
  if (!token) throw new Error('登录响应中未找到 kaoyan_session token');
  return token;
}

async function seedDemoData(port, token) {
  async function post(apiPath, body) {
    const res = await apiRequest(port, 'POST', apiPath, { token, body });
    if (res.status < 200 || res.status >= 300) {
      throw new Error(`播种数据失败：${apiPath} 返回状态码 ${res.status}：${res.text.slice(0, 200)}`);
    }
    return res;
  }

  async function patch(apiPath, body) {
    const res = await apiRequest(port, 'PATCH', apiPath, { token, body });
    if (res.status < 200 || res.status >= 300) {
      throw new Error(`播种数据失败：${apiPath} 返回状态码 ${res.status}：${res.text.slice(0, 200)}`);
    }
    return res;
  }

  function d(n) {
    const dt = new Date();
    dt.setDate(dt.getDate() - n);
    const y = dt.getFullYear();
    const m = String(dt.getMonth() + 1).padStart(2, '0');
    const day = String(dt.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function dt(n, hm) {
    return `${d(n)}T${hm}:00`;
  }

  // 6 条 plans（done 经 PATCH 置 true）
  const planDefs = [
    { date: d(0), title: '数学：2015 真题概率论大题', subject: 'math', plannedMinutes: 120, done: true },
    { date: d(0), title: '英语：阅读理解 2018 年 Text3', subject: 'english', plannedMinutes: 60, done: false },
    { date: d(1), title: '政治：马原唯物辩证法框架梳理', subject: 'politics', plannedMinutes: 90, done: true },
    { date: d(1), title: '专业课：数据结构红黑树插入', subject: 'major', plannedMinutes: 80, done: false },
    { date: d(2), title: '数学：线性代数特征值计算', subject: 'math', plannedMinutes: 100, done: true },
    { date: d(2), title: '英语：翻译真题长难句分析', subject: 'english', plannedMinutes: 50, done: false },
  ];
  for (const p of planDefs) {
    const res = await post('/api/plans', { date: p.date, title: p.title, subject: p.subject, plannedMinutes: p.plannedMinutes });
    if (p.done) {
      await patch(`/api/plans/${res.json.id}`, { done: true });
    }
  }

  // 8 条 focus
  await post('/api/focus', { subject: 'math', minutes: 45, startedAt: dt(0, '08:00') });
  await post('/api/focus', { subject: 'english', minutes: 30, startedAt: dt(0, '09:00') });
  await post('/api/focus', { subject: 'politics', minutes: 50, startedAt: dt(0, '10:00') });
  await post('/api/focus', { subject: 'major', minutes: 55, startedAt: dt(1, '08:30') });
  await post('/api/focus', { subject: 'math', minutes: 60, startedAt: dt(1, '14:00') });
  await post('/api/focus', { subject: 'english', minutes: 25, startedAt: dt(2, '09:15') });
  await post('/api/focus', { subject: 'major', minutes: 40, startedAt: dt(2, '15:00') });
  await post('/api/focus', { subject: 'politics', minutes: 35, startedAt: dt(3, '10:30') });

  // 5 条 mistakes（mastered 经 PATCH 置 true）
  const mistakeDefs = [
    { subject: 'math', title: '二次型正交变换化标准形', content: '把特征向量没有单位化就直接写变换矩阵', analysis: '正交变换要求列向量是标准正交基，必须对特征向量施密特正交化后单位化', mastered: false },
    { subject: 'english', title: '虚拟语气倒装', content: '省略 if 后未部分倒装', analysis: 'had/were/should 提前时，主句语序不变，从句部分倒装', mastered: false },
    { subject: 'politics', title: '社会必要劳动时间概念', content: '混淆了社会必要劳动时间与个别劳动时间', analysis: '社会必要劳动时间是在现有社会正常生产条件下，由社会平均劳动熟练程度决定的时间', mastered: true },
    { subject: 'major', title: 'AVL 树旋转方向', content: '在 RL 型失衡时先右旋再左旋，方向写反', analysis: 'RL 型：先对右子树右旋，再对根左旋；LR 型则反过来', mastered: false },
    { subject: 'math', title: '条件概率与独立性', content: 'P(A|B)=P(A) 时判断独立，未验证 P(AB)=P(A)P(B)', analysis: '定义法验证独立性必须检查 P(AB)=P(A)P(B)，不能只看条件概率等于无条件概率', mastered: true },
  ];
  for (const m of mistakeDefs) {
    const res = await post('/api/mistakes', { subject: m.subject, title: m.title, content: m.content, analysis: m.analysis });
    if (m.mastered) {
      await patch(`/api/mistakes/${res.json.id}`, { mastered: true });
    }
  }

  // 1 次 seed-vocab
  await post('/api/words/seed-vocab');

  // 4 条 exams
  await post('/api/exams', { subject: 'math', paper: '2024 真题卷', score: 118, totalScore: 150, takenAt: dt(3, '08:30'), durationMinutes: 180 });
  await post('/api/exams', { subject: 'english', paper: '2023 真题卷', score: 62, totalScore: 100, takenAt: dt(5, '14:00'), durationMinutes: 180 });
  await post('/api/exams', { subject: 'politics', paper: '2022 真题卷', score: 71, totalScore: 100, takenAt: dt(7, '08:30'), durationMinutes: 180 });
  await post('/api/exams', { subject: 'major', paper: '2024 真题卷', score: 108, totalScore: 150, takenAt: dt(10, '14:00'), durationMinutes: 180 });

  console.log('[harness] 演示数据播种完成');
}

const MIME = { '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf' };

async function createShotContext({ port, token }) {
  const { chromium } = resolvePlaywright();
  const browser = await chromium.launch({ executablePath: '/opt/meta-chromium/chrome', args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  // Playwright context.route 后注册优先；本静态路由的 /** 通配同样匹配 /api/*，
  // 因此它必须先注册、/api 代理路由后注册；顺序颠倒时 /api 请求会被本路由
  // fulfill 成 index.html，接口永远走不到真实后端。
  await context.route(`http://127.0.0.1:${port}/**`, async (route) => {
    const u = new URL(route.request().url());
    let p = u.pathname;
    if (p === '/') p = '/index.html';
    const f = path.join(WEB_DIST, p);
    if (fs.existsSync(f) && fs.statSync(f).isFile()) {
      await route.fulfill({ body: fs.readFileSync(f), contentType: MIME[path.extname(f).toLowerCase()] || 'application/octet-stream' });
    } else {
      await route.fulfill({ body: fs.readFileSync(path.join(WEB_DIST, 'index.html')), contentType: 'text/html' });
    }
  });
  // 本路由必须保持在静态路由之后注册（后注册优先），不许把两路合并成一个 handler
  // 除非仍保证 /api 优先；改动注册顺序前必须跑 route-order-probe.mjs 验证。
  await context.route('**/api/**', async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const cookie = req.headers()['cookie'];
    const postData = req.postDataBuffer();
    try {
      const r = await apiRequest(port, req.method(), u.pathname + u.search, { cookie, body: postData && postData.length ? postData.toString() : undefined, contentType: req.headers()['content-type'] });
      await route.fulfill({ status: r.status, body: r.text, contentType: r.headers['content-type'] || 'application/json' });
    } catch (e) {
      await route.fulfill({ status: 502, body: '代理错误: ' + e.message });
    }
  });
  await context.addCookies([{ name: 'kaoyan_session', value: token, url: `http://127.0.0.1:${port}` }]);
  console.log('[harness] 浏览器上下文已创建');
  return { browser, context };
}

async function runShotPlan(page, plan, outDir, port) {
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200)); });
  fs.mkdirSync(outDir, { recursive: true });
  const shots = [];
  for (const item of plan) {
    const url = `http://127.0.0.1:${port}${item.route}`;
    console.log(`[harness] 访问 ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector(item.waitFor, { timeout: 15000 });
    for (const a of item.actions || []) {
      if (a.clickLast) {
        await page.locator(a.clickLast).last().click();
      } else {
        await page.locator(a.click).click();
      }
      await page.waitForTimeout(a.waitMs || 800);
    }
    await page.waitForTimeout(800);
    const file = path.join(outDir, item.shotName || (item.name + '.png'));
    await page.screenshot({ path: file });
    shots.push(file);
    console.log(`[harness] 截图 ${item.name} -> ${file}`);
  }
  if (errors.length) throw new Error('页面错误 ' + errors.length + ' 条：' + errors.slice(0, 5).join(' | '));
  return shots;
}

async function shutdown(serverProc, browser) {
  if (browser) await browser.close().catch(() => {});
  if (serverProc && !serverProc.killed) {
    serverProc.kill('SIGTERM');
    const dead = await new Promise((resolve) => {
      const t = setTimeout(() => resolve(false), 5000);
      serverProc.once('exit', () => { clearTimeout(t); resolve(true); });
    });
    if (!dead) serverProc.kill('SIGKILL');
  }
  console.log('[harness] 已关闭');
}

export { spawnServer, waitForHealth, apiRequest, registerAndLogin, seedDemoData, createShotContext, runShotPlan, shutdown };

