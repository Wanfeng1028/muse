# LingCut 画布自动化（Playwright + REST API）

> 建立日期：**2026-10-02**。这一页是踩了 6 个坑才总结出来的，
> **再做 LingCut 自动化前必读**，否则会重复浪费大量时间。

---

## 一、为什么不能只用 `browser_*` 工具

| 需求 | `browser_*` 工具 | 结论 |
|---|---|---|
| 上传本地视频/图片到画布 | ❌ 无头浏览器**不弹文件对话框**，没有 `setInputFiles` | **必须自己起 Playwright** |
| 页面访问 `http://127.0.0.1` | ❌ **Chrome Private Network Access 直接拦**（实测请求根本到不了服务器，加 `Access-Control-Allow-Private-Network` 也没用） | 别走本地服务器 |
| 读/写画布 JSON | ❌ 只能用引擎内存态，不落库 | **走 REST API** |

**结论：用 Playwright 起自己的浏览器 + 直连 LingCut REST API。**

---

## 二、环境（本机实测可用）

```
playwright-core : <DSH>\profiles\desktop\node_modules\playwright-core
                  （版本 1.63.0，但装的 chromium 是 1234 → 必须指定 executablePath 绕开版本检查）
Chromium        : <HOME>\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe
备用            : C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
凭据            : .secrets\lingcut.json  {account, password}
持久化 profile   : .probe\chrome-profile   （登录态会留在这里，不用每次登录）
```

```javascript
const PW = 'file:///<DSH>/profiles/desktop/node_modules/playwright-core/index.js';
const pwMod = await import(PW);
const chromium = pwMod.chromium || pwMod.default?.chromium;   // ⚠️ CJS 互操作，两种都要试

const ctx = await chromium.launchPersistentContext(profileDir, {
  headless: true,
  executablePath: CHROME,       // ★ 不指定会报 Executable doesn't exist
  viewport: { width: 1440, height: 900 },
  args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  locale: 'zh-CN',
});
```

---

## 三、六个坑（按踩到的顺序）

### 坑 1 · 登录弹窗点不到

`button:has-text("登录")` 会被 `div.fixed.inset-0.bg-black\/60` 遮罩拦住 →
`locator.click` 超时。

**解法：不要点顶部按钮，直接填弹窗里的 input**（用 native setter 触发 React）：

```javascript
const setVal = (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(el, v);
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
};
// 弹窗里 input[type=text] + input[type=password]，勾掉所有 checkbox，再点弹窗内的「登录」
```

### 坑 2 · 项目 URL 不是 `/project/3535`

**❌ `https://www.lingcut.cn/project/3535` → 永远等不到画布**
**✅ 正确流程：首页 → 点「我的剧集」→ 点项目卡片 → 落到 `/canvas/<ID>`**

### 坑 3 · 引导弹窗挡住引擎

画布加载后会有「**欢迎使用 LingCut**」弹窗（按钮「开始使用」），
它不关掉的话 React fiber 里找不到引擎。

```javascript
for (let i = 0; i < 4; i++) {
  const hit = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .find(x => /^(开始使用|我知道了|知道了|关闭)$/.test((x.textContent||'').trim()));
    if (b) { b.click(); return true; }
    return false;
  });
  if (!hit) break;
  await page.waitForTimeout(1200);
}
```

### 坑 4 · 引擎注入要穷举 React fiber

```javascript
const isEngine = o => o && typeof o === 'object'
  && o.nodeMap instanceof Map && typeof o.addNode === 'function';
// 从每个元素的 __reactContainer$ / __reactFiber$ 出发，
// 走 stateNode / memoizedState(hook 链表) / 自身，深度 ≤6，seen 去重
```

### 坑 5 · 选节点：**挪节点 AND 挪镜头**，点**中心**

```javascript
focusNode: (id, wx, wy, sx, sy, k) => {
  eng.updateNodePosition(id, wx, wy);              // ① 挪节点
  eng.setTransform(sx/k - wx, sy/k - wy, k);       // ② ★ 挪镜头（漏了这步点击一定落空）
  eng.forceUpdate();
}
// Leafer 节点以「左上角」为 x/y，所以屏幕点击坐标 = 左上角 + (w/2, h/2)
// screen = (world + transform) * k
```

### 坑 6 · **`addConnection` 不跨页面刷新持久化** ★最坑

实测：
```
第一次会话：addConnection(ref, gen) → 服务端 canvas_data 里有了边 ✅
第二次会话（重新开页面）：边没了 ❌
```

**后果**：分两次跑（先连线、再生成）→ 服务端看不到参考 → 提示词引用 `@图1` 但无图 →
上游插件 502 `task_id is empty`。

**解法：连线 + 设参 + 生成必须在同一次会话内完成。**

---

## 四、REST API（比引擎可靠得多）

```
GET  /api/projects/<ID>      → {"project":{"canvas_data":"{...}"}}
PUT  /api/projects/<ID>      body {"canvas_data":"<json字符串>"}
GET  /api/tasks/active/list?projectId=<ID>
GET  /api/user/subscription
GET  /api/user/configs       → {"configs":{"api_keys":{"mate70":"sk-..."}}}
```

**`canvas_data` 结构：**
```javascript
{
  nodes: [ { type:'image'|'video', id:'p<ID>_n0', x, y, w, h, name, groupId,
             data:{ model, aspectRatio, duration, prompt, content, resolution, count,
                    generating, src, selectedSrc, srcs, genError, genProgress, backendTaskId } } ],
  connections: [ { id:'c4206', sourceId:'p<ID>_n1', targetId:'p<ID>_n331' } ],
  groups, nid, typeCounters, view, selection
}
```

**取 cookies：** 用 Playwright 打开一次页面，`ctx.cookies()` 拼成 `Cookie` 头，之后 Node `fetch` 直连。

**上游（猿拓 mate70）：**
```
baseUrl : https://aa.mate70.com      （OpenAI 兼容）
apiKey  : 从 /api/user/configs 拿     （形如 sk-yPKG...）
可用模型：wan3-720p-t / Seedance2.0
GET /v1/models                        → 模型列表
GET /v1/dashboard/billing/usage       → 用量
```

---

## 四点五、★★★ 改画布数据的唯一正确姿势（血泪教训）

### 三个必须记住的事实

**① 直接写 `name` 字段能落库**
```js
n.name = '一·1章 B01 老街未醒 [图]';
n.data.name = n.name;
await fetch('/api/projects/<ID>', { method:'PUT', body: JSON.stringify({ canvas_data: JSON.stringify(cd) }) });
// → 回读确认持久化 ✅
```
（以前误判为"不能落库"，是因为当时只调了引擎的 `updateNodeData` 而没有自己 PUT。）

**② ★★ REST PUT 会被应用的自动保存覆盖**
LingCut 画布页开着的时候，它会把**内存里的状态**定期存回服务器。
你用 REST 改了 `src` / 坐标 → 应用内存还是旧的 → 它一自动保存，你的修改就没了。
**症状**：改完回读是对的，过一会儿再读又变回旧值。

**③ ★★★ 所以改数据必须走引擎 `updateNodeData`**
```js
// 在画布页里执行，让应用内存同步，再交给它自己保存
eng.updateNodeData('p<ID>_n331',
  { src: URL, selectedSrc: URL, srcs: [URL], model: 'wan3-720p-t', duration: '8s' }, true);
eng.forceUpdate(); eng.repaint();
// 等 10~12 秒让自动保存跑完，再回读验证
```
**如果非要用 REST**：PUT 之前先 `page.goto('about:blank')`，把应用停掉再写。

---

### ★★ 引擎注入的正确 fiber 路径（找了几小时）

普通遍历找不到，**正确的路径是**：
```
元素.__reactFiber$xxx .return .memoizedState .memoizedState .current
                                                          ↑ 引擎在这里
```
通用写法（深度 8、含 `current` 字段）：
```js
const seen = new Set(); let eng = null;
function walk(o, d) {
  if (!o || d > 8 || seen.has(o) || eng) return;
  try { seen.add(o); } catch (e) { return; }
  try { if (o.nodeMap instanceof Map && typeof o.addNode === 'function') { eng = o; return; } } catch (e) {}
  for (const k of ['stateNode','child','sibling','return','memoizedState','memoizedProps','pendingProps','ref','current']) {
    try { walk(o[k], d + 1); } catch (e) {}
  }
  if (o.memoizedState) { let h = o.memoizedState, n = 0;
    while (h && n++ < 60 && !eng) { try { walk(h.memoizedState, d + 1); } catch (e) {} h = h.next; } }
}
for (const el of [...document.querySelectorAll('*')].slice(0, 5000)) {
  for (const k in el) if (k.startsWith('__react')) walk(el[k], 0);
  if (eng) break;
}
```
**★ 首先要关掉「欢迎使用 LingCut」弹窗**（按钮「开始使用」），否则引擎不在树里。

---

### ★ 引擎的实用 API（实测存在）

| API | 用途 |
|---|---|
| **`eng.selectNode(id)`** | **直接选中节点**（不用再算坐标点画布！）|
| `eng.getSelectedNode()` | 取当前选中 |
| `eng.updateNodeData(id, patch, true)` | **改数据并落库** |
| `eng.updateNodePosition(id, x, y)` | 改坐标 |
| `eng.setTransform(tx, ty, k)` | 镜头（`屏幕 = (世界 + t) × k`）|
| `eng.nodeMap` | `Map<id, node>`，共 408 个 |
| `eng.container` / `eng.forceUpdate()` / `eng.repaint()` | 刷新 |
| `eng.startSyncLoop` / `syncRaf` | 它自己的自动保存循环（**这就是覆盖你修改的元凶**）|

---

### ★ 上传本地文件到节点（正确姿势）

```js
await page.evaluate(id => window.__eng.selectNode(id), nodeId);   // ① 必须先选中，file input 才出现
await page.waitForTimeout(2500);
const inputs = await page.$$('input[type=file]');                 // ② 会出现 2 个
for (const h of inputs) {
  const acc = await h.getAttribute('accept');
  if (acc && /video/.test(acc)) { await h.setInputFiles(localPath); break; }   // accept="video/*"
}
// 另一个 input 的 accept 是文档类型（.docx,.xlsx,.pptx,.pdf,…）
await page.waitForTimeout(9000);                                   // ③ 等上传完成
```

---

### ★ 登录态会过期

```js
GET /api/projects/<ID> → 401 {"error":"请先登录"}
// 症状：cookie=0，页面被重定向到首页 https://www.lingcut.cn/
```
**解法**：`.probe\lingcut-login.mjs`（读 `.secrets\lingcut.json`，自动填表 + 勾协议 + 提交）。
登录态存在持久化 profile 里，登录一次可长期复用。

---

### ★ 判断"节点是否有出片"

```js
const noSrc = cd.nodes.filter(n => {
  const d = n.data || {};
  return !(d.src || (d.srcs || []).length);   // src 和 srcs 都为空 = 没出片
});
```
**注意**：节点还可能有 `selectedSrc`。**恢复丢掉的出片**时，`src` / `selectedSrc` / `srcs` 三个都要写。

---

## 五、★ 改名（标注）唯一能持久化的路径

| 方法 | 结果 |
|---|---|
| `updateNodeData(id, {name})` | ❌ 只改内存，`PUT` 后仍是旧名 |
| `setNodeName(id, name)` | ❌ 源码只设 `o.name` + `group._titleText.text`，**不动 `data.name`** |
| **`startRename(id)` → 填 `input[type=text]` → 回车** | ✅ **走 React 提交，落库** |

```javascript
await page.evaluate(id => window.__lc.eng.startRename(id), id);
await page.waitForTimeout(400);
const inp = page.locator('input[type=text]').first();
await inp.click(); await page.keyboard.press('Control+A');
await inp.fill(name); await page.keyboard.press('Enter');
```

（149 个节点批量改名实测：约 1.5 秒/个，失败 0）

---

## 六、★ 白模付费流水线（已验证出片）

```
① 白模视频        本地 04-3D\moves3\*.mp4
② 上传到画布      选中参考节点 → 点节点上方第一个 [↑] 图标按钮
                  → 等不到 filechooser 就 setInputFiles 兜底
③ 连线            addConnection(白模节点, 生成节点)  ← 必须同一会话
④ 模型            wan3-720p-t（0.3元/秒，10图5视频5音频）或 Seedance2.0（4.2元/条）
⑤ 提示词          必须同时写 data.prompt（用 updateNodeData）和 contenteditable
⑥ 点 ↑ 生成
```

**提示词四区块（官方规范）：**
```
① 参考规则  —— 逐个钉死素材角色和禁区
   「@视频1 只作镜头调度/构图/运动路径/节奏参考，不要参考它的视口界面、灰模材质、
     线框、低模形状、临时灯光、占位贴图、预览画质、网格或任何软件界面」
② 白模身份  —— 颜色图例
③ 动作顺序  —— 逐拍写清
④ 严格不要  —— 禁止灰模风格 / 3D预览风格 / 低模几何块 / 多余人物
```

**实测结果（A04）：** wan3-720p-t，8.03s，1280×720，**30fps**，8260 kb/s，
**画面里完全看不到白模痕迹**。

**⚠️ 已知上游波动**：2026-10-02 05:45 起 `wan3-720p-t` / `Seedance2.0` 连续 502
（插件报 `task_id is empty`），直连上游 `POST /v1/video/generations` 返回
`503 No available channel for model ...`。**这是上游渠道临时不可用，等恢复即可。**

---

## 六点五、★★ 限流：每分钟最多 5 次请求（含失败）

**2026-10-02 实测发现，这解释了本 session 大量间歇性失败。**

批量提交生成时，失败返回：
```
您已达到总请求数限制：1分钟内最多请求5次，包括失败次数，请检查您的请求是否正确
```

**⚠️ 关键：失败次数也算。** 所以「提交 10 个 → 一半失败 → 重试 → 又失败」会雪崩。

**解法：**
```javascript
for (let i = 0; i < jobs.length; i++) {
  if (i > 0) await sleep(13000);   // ★ 每次间隔 13 秒，稳在 5 次/分钟以内
  // 选中 → 设时长 → 打字 → 点 ↑
}
```
实测：加 13 秒节流后，**9~10 个连续生成一次全过**（此前不加节流会失败 30~50%）。

**★★ 补充（2026-10-02 下午实测）：不只是提交间隔，还要等整批跑完。**
我提交完第十二章 8 个之后**立刻**提交第十三章 8 个 → 后一批的头两个报
`请求过于频繁，请稍后再试`（前一批还在生成中）。

**正确做法：**
```javascript
// ① 提交一批（每个间隔 13s）
// ② ★ 等这一批 generating 全部变 false
for (let i = 0; i < 60; i++) { await sleep(15000);
  if (!batch.filter(id => lc.node(id).data.generating).length) break; }
// ③ 再提交下一批
```

**其他两个已知失败：**
| 报错 | 原因 | 解法 |
|---|---|---|
| `We are so sorry, but the prompt may violate our content policy` | 措辞触发审查 | 换中性措辞（见下） |
| `generate image failed` | 偶发 | 隔 13 秒重试 |

**内容策略高危措辞 → 中性替换：**
| ❌ 高危 | ✅ 中性 |
|---|---|
| 从坡上**滚落** | **坐在**石头旁边休息 |
| 脸因为**剧痛**而扭曲 | 微微低着头，表情安静而疲惫 |
| **放在**土炕上 | **扶**少年**坐到**土炕边 |
| **浑身是血**的年轻修士 | **面色苍白、气息微弱**的年轻修士 |

**★ 另一个相关坑：AI 渲染精确中文不可靠。**
实测 H08 要「娘：见字如面。儿不孝。儿尽力了。」+ 地址「雪原」，
结果生成出「**变成诗。**」「思念也变成诗。」——完全错的字。
**解法：宁可让字迹虚化不可读**（提示词写「字迹因极浅的景深而微微虚化、辨认不出具体内容」），
**也不能让它写出错的字**。

**★ 第三个坑：单物体特写会被模型画成多格拼贴。**
实测要「大特写：一枚青玉莲花佩」，结果生成出 **六宫格拼贴**（同一个玉重复 6 次）——
因为角色定板图的「多视图排版」训练惯性会污染单物体特写。

**解法：在提示词里明确加一句硬约束**（实测有效）：
```
★这张图必须是单一的一幅完整画面，绝对不要多格拼贴、不要分割构图、
  不要角色表排版、不要九宫格或六宫格、不要重复出现同一个物体。
```

**★ 第四个坑：动作给「站/坐」这类姿态词不够，要给「完整的动作变化」。**
实测 L06 写「弯腰从雪里捡起一样东西」→ 生成出**趴在雪地里爬行**。
改成「**站直了身子**，弯腰从脚边捡起，随即**直起腰**抬头」→ 正确。

---

## 七、★★ PowerShell 两个反复踩的坑（拼片脚本）

### 坑 A · 变量名不区分大小写
```powershell
$TOT = 23.30          # 音频总长
$tot = ($parts | ... | Measure-Object -Sum).Sum   # ← 字数合计 98
# ★ $TOT 和 $tot 是同一个变量！$TOT 变成 98
# → 切段算出 0→20 / 20→41 / 41→98 秒（全错）
```
**解法：变量名必须有实质差异** —— `$TOTDUR` / `$SUMDUR`，不要靠大小写区分。
（同理 `$HOME`/`$home`、`$PID`/`$pid` 都是同一个。）

### 坑 B · 函数返回值被输出流污染
```powershell
function Concat($files,$dest) {
  Write-Output "  ★ 拼好了"     # ← 这行也会进返回值
  return 65.0
}
$d = Concat ...                 # ★ $d 变成 @("  ★ 拼好了", 65.0)
"$d/60"                         # → op_Division 报错
```
**解法：**
- 函数内的进度输出用 `Write-Host`（不进输出流），或
- 返回值用 `$global:LASTDUR = $x`，调用方读 `$global:LASTDUR`

**同类坑还有：**
- `Cat` 是 `Get-Content` 的别名，自定义函数不能叫 `Cat`（用 `Concat` 就好）
- `Test-Path "$dir\{0:d2}.jpg" -f $n` ❌ —— `-f` 不能用在字符串里，要先 `("{0:d2}.jpg" -f $n)`
- ffmpeg 的 `-f image2` 必须放在输出路径**之前**：`... -frames:v 1 -f image2 out.jpg`

### ★ ffmpeg 抽帧正确写法
```powershell
& $ff -hide_banner -loglevel error -y -ss $t -i $film -frames:v 1 $out
# -y 必须在 -i 之前；输出无扩展名歧义时可不写 -f image2
```

---

## 八、脚本清单（都在 `.probe\`）

| 脚本 | 用途 |
|---|---|
| `lingcut-make.mjs` | 建节点 / 命名 / 上传 / 生成（主脚本）|
| `lingcut-upload.mjs` | 同上（早期版本，含 probe/nodes 模式）|
| `lingcut-label2.mjs` | 批量标注（startRename 路径）|
| `lingcut-api.mjs` | REST API 读画布 / 查边 / 加删边 |
| `lingcut-api-set.mjs` | REST API 改节点字段（model/duration/prompt/...）|
| `lingcut-check.mjs` | 查节点状态（生成结果）|
| `lingcut-neterr.mjs` | 抓完整网络错误 |
| `lingcut-capture-api.mjs` | 抓生成提交请求体 |

**主脚本用法：**
```bash
node lingcut-make.mjs new <image|video> "<名称>" <x> <y>
node lingcut-make.mjs upload <nodeId> <本地文件>
node lingcut-make.mjs rename <nodeId> "<名称>"
node lingcut-make.mjs gen <refIds逗号分隔|none> <genNodeId> <模型key> <时长> <提示词文件> [RUN]
```
