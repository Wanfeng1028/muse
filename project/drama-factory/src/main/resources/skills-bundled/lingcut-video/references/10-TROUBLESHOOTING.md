# 故障排查对照表

> 遇到报错先查这张表。**99% 的坑都在这里。**

---

## 一、★ 全表速查

| 报错 / 现象 | 原因 | 解法 |
|---|---|---|
| `请求过于频繁，请稍后再试` | 限流（≤5 次/分钟，**含失败**）| 节流 **13–15 秒/次**；一批跑完再提下一批 |
| `HTTP 503 fail_to_fetch_task` | 上游波动 | **原样重试**（等 15–20 秒）|
| `HTTP 502 plugin wan3 hook parseSubmitResponse failed: task_id is empty` | 付费渠道挂了 | 查 `POST /v1/video/generations` 的返回；`No available channel` = 渠道无货 |
| `may violate our content policies` | 内容审核 | **改措辞**再试（见 06-CONTENT-POLICY.md），不要原样重试 |
| `The video generation task failed.` | 生成失败 | 原样重试 1 次；连续失败 → 改提示词 |
| `generate image failed` | 图生成失败 | 等 15 秒重试 |
| `get image url failed` | 同上 | 同上 |
| 节点 `generating` 一直 `true` | 浏览器关掉后没人重置标志 | 查 `/api/tasks?projectId=<id>` 的真实状态 |
| 上传文件后 `PUT 400` | 与应用自动保存竞争 | 无害（应用已保存）；或先 `page.goto('about:blank')` |
| 画布改动被还原 | **应用自动保存覆盖 REST 写入** | 用引擎 `updateNodeData(id, patch, true)`；或先导航 `about:blank` 再 PUT |
| `Cannot read properties of undefined (reading 'nodes')` | 401 / 拉取失败 | 重新登录 + 重试 |
| 浏览器起不来 `Target page, context or browser has been closed` | **profile 被另一个进程占用** | 确认没有别的脚本在跑同一个 `chrome-profile` |
| `ERR_AMBIGUOUS_MODULE_SYNTAX` | 在 `.mjs` 里用了 `require` | 改成 `import` |
| `document is not defined` / Node 里跑浏览器 API | 跑错环境 | 浏览器 API 只在 `page.evaluate` 里用 |
| ffmpeg concat `unknown keyword 'file'` | list.txt 有 BOM | 用 `UTF8Encoding($false)` 写 |
| 成片时长膨胀（12s → 12.6s）| 没做规范化 | 逐段 `-c:v libx264 -r 24 -vf scale=...` 后 concat |
| 旁白比画面早/晚 | 镜头时长改过 | 在变化点插静音（见 08-ASSEMBLY.md）|
| 成片比预期短 | **漏镜** | 从画布全集重下 + 按单元核对镜号 |
| ffmpeg 报 `At least one output file must be specified` | 只是探测（`-i` 没输出）| 正常，忽略 |
| PowerShell 报 `if : 无法将"if"项识别` | `if` 不能当表达式用在 `-f` 里 | 拆开写 |
| PowerShell 变量串了 | **变量名不区分大小写** | `$TOT` vs `$tot` 是同一个 |
| 函数返回数组 | `Write-Output` / `return` 污染 | 用 `Write-Host` + `$global:X` |
| 中文路径乱码 / 语法错误 | 脚本文件缺 BOM | 写完后加 BOM |
| 文件删不掉 `being used by another process` | 被预览/缩略图进程锁住 | 让下游脚本**按文件名过滤**跳过；或重启后删 |

---

## 二、限流（最容易踩）

**规则**：**≤5 次请求/分钟，失败的也算**。

**正确做法**：
```js
for (let k = 0; k < jobs.length; k++) {
  if (k > 0) await sleep(13000);   // ★ 13 秒
  await genNode(jobs[k]);
}
```

**并且**：**一批跑完（全部出片）再提下一批**，不要交叉提交。

**症状**：出现 `请求过于频繁` 后，**后续提交也会连着失败** ——
所以要停下来等 1–2 分钟，不要猛重试。

---

## 三、画布数据改动的唯一正确姿势 ★★★

**问题**：直接 `PUT /api/projects/<id>` 改 `canvas_data`，**会被应用的自动保存覆盖**。

**原因**：打开的画布页面会周期性把内存里的状态写回服务端
（`eng.startSyncLoop` / `syncRaf`）。

**三个正确做法（任选）**：

### ① 引擎法（推荐）

```js
// 先拿到引擎（见下）
eng.updateNodeData(nodeId, { name: '新名字' }, true);
eng.updateNodePosition(nodeId, x, y);
eng.forceUpdate();
```

应用内存同步了，所以自动保存不会覆盖。

### ② 先离开页面再 PUT

```js
await page.goto('about:blank');   // 页面没了，不会自动保存
// 然后 fetch PUT
```

### ③ 引擎的其它 API

```
eng.selectNode(id)                  // 直接选中（不用算坐标）
eng.getSelectedNode()
eng.updateNodeData(id, patch, true)
eng.updateNodePosition(id, x, y)
eng.setTransform(tx, ty, k)         // screen = (world + t) * k
eng.nodeMap                         // Map<id, node>
eng.addNode(type, x, y)
eng.addConnection(from, to)
eng.removeConnectionBetween(from, to)
eng.forceUpdate() / eng.repaint()
```

**⚠️ `addConnection` 不跨刷新持久化** —— 连线和生成要在**同一个会话**里做完。

---

## 四、引擎注入的正确 fiber 路径

```js
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
```

**★ 前置条件：必须先关掉「欢迎使用 LingCut」弹窗**，否则引擎还没挂载。

**验证**：`eng.nodeMap.size` 能返回数字。

---

## 五、上传文件的流程

```js
// ① 必须先选中节点
eng.selectNode(id);
await sleep(2500);
// ② 这时页面上才出现 input[type=file]
const inputs = await page.$$('input[type=file]');
// ③ 按 accept 挑对的那个
for (const h of inputs) {
  const acc = await h.getAttribute('accept');
  if (acc && /image|png/.test(acc)) { await h.setInputFiles(file); break; }
}
```

**注意**：`browser_*` 工具**调不了 setInputFiles**，
且 **Chrome PNA 禁止页面访问 127.0.0.1** → 必须自己起 Playwright。

---

## 六、`generating` 标志会骗人

**问题**：节点 `data.generating === true`，但任务早就结束了（或根本没提交成功）。

**原因**：`generating` 是**应用内存里的标志**，浏览器一关就没人更新它了。

**解法**：查服务端任务表

```js
GET https://www.lingcut.cn/api/tasks/active/list?projectId=<id>
GET https://www.lingcut.cn/api/tasks?projectId=<id>
```

返回 `{ tasks: [{model, status, progress, params: {nodeId}, error_message}] }`。

**判断**：
- 任务表里**没有**这个 nodeId → 请求**根本没提交成功**
- 有且 `status: 'completed'` → 成功了，去看 `data.src`
- 有且 `error_message` → 看错误内容

---

## 七、登录过期

**症状**：`GET /api/projects/<id>` → `401 {"error":"请先登录"}`，页面跳回首页。

**解法**：脚本化重新登录（读 `.secrets/lingcut.json`）：

```js
先点掉「重要通知」弹窗（按钮「我知道了」）
→ 点「登录」
→ 填 input[placeholder="请输入用户名或邮箱"] 和 input[placeholder="请输入密码"]
→ 勾选协议 input[type=checkbox]
→ 点带 w-full 类的「登录」按钮
→ 成功标志：顶部导航出现「订阅中心」
```

登录后取 cookie：
```js
const H = { Cookie: (await ctx.cookies()).map(c => c.name + '=' + c.value).join('; ') };
```

---

## 八、内容渲染问题（不是报错，但更常见）

| 现象 | 原因 | 修法 |
|---|---|---|
| **单物体特写变成九宫格/角色表** | 模型默认排版 | 加硬约束：`★单一的一幅完整画面，绝对不要多格拼贴、不要九宫格、不要角色表排版、不要重复出现同一个物体` |
| **画面里出现两个主角** | 提示词没说人数 | 加 `★画面里只能有一个人` |
| **台词说得太快** | 字数 ÷ 时长 > 4 字/秒 | 加时长，或拆镜（见 04-LONGSHOT.md），或写停顿指示 |
| **台词被砍掉半句** | 时长不够 | 同上 |
| **说话人错了**（A 的台词给 B 说了）| 台词没标归属 | 用 ①②③④ **逐条标注每人说什么**，并强调「问句和答句必须是不同的人」 |
| **声音性别错了** | 画面里没有人，模型无从判断 | 提示词里明确：`用<苍老/年轻>的<男/女>声，不是<另一个性别>声`；**并在画面里放进那个人** |
| **人物一动就折颈拉长** | 动作给太大 | 动作写成**完整的姿态变化**（站直了身子，弯腰从脚边捡起，随即直起腰）|
| **画面定格不动** | 提示词里写了「静止/不动/定格」| **永远不要写这三个词** |
| **字写错了** | AI 画中文不可靠 | 见 05-ASSETS.md |
| **画风像电视剧截图** | 场景写太全、平均曝光 | 见 02-PROMPT.md 的电影感五条 |

---

## 九、排错顺序（遇到问题照这个走）

```
① 看报错文字
   ├─ 含 "policy" → 改措辞（06-CONTENT-POLICY.md）
   ├─ 含 "频繁"   → 节流
   ├─ 含 "503/502" → 上游波动，原样重试
   └─ 其它        → 往下
② 查服务端任务表（/api/tasks）
   ├─ 没这个 nodeId → 请求没提交成功 → 检查提交代码
   └─ 有 error_message → 按错误内容处理
③ 查登录态（401 → 重新登录）
④ 查引擎是否注入成功（nodeMap.size）
⑤ 都正常 → 大概率是**提示词问题**，去看画面/听声音
```

---

## 十、成本核算（花过的钱）

| 项目 | 单价 | 说明 |
|---|---|---|
| 分镜图 | **0.06 元/张** | `gpt-image-2.5` |
| 免费视频 | **0 元** | `lingcut` 模型，5/8/10/12 秒 |
| 付费视频 wan3 | **0.3 元/秒** | 5/8/10/12/15/18/20/25/28/30 秒 |
| 付费视频 Seedance | **4.2 元/条** | 固定 15 秒 |
| LibTV 音色 | **1 积分/条** | `seed-audio-1.0` |

**实测一片 25 分钟古装片的成本**：约 **23.5 元**
（图 ~15 元 + 1 个付费白模镜 2.4 元 + LibTV 约 30 积分；
190+ 个免费视频 = 0 元）

**★ 铁律：付费前必须跟用户报备并获批。** 不要默默花钱。

---

## 十一、免费 vs 付费时长对照

| 模型 | 可用时长 |
|---|---|
| `lingcut`（免费）| **5 / 8 / 10 / 12 秒** |
| `wan3-720p-t`（0.3元/秒）| 5 / 8 / 10 / 12 / 15 / 18 / 20 / 25 / 28 / 30 秒 |
| `Seedance2.0`（4.2元/条）| 固定 15 秒 |

**长镜优先用尾帧接续法（免费），而不是付费。**
