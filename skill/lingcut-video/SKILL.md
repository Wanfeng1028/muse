---
name: lingcut-video
description: 端到端 AI 影视/短剧流水线。用 LingCut（lingcut.cn）无限画布生成分镜图与视频、LibTV 生成配音与旁白、ffmpeg 拼接成片，并交付一个可直接剪辑的工作台。当用户要求"做一部 AI 短剧/AI 电影/AI 视频/MV"、"用 lingcut 生成视频"、"把剧本做成视频"、"这个剧本拍出来"、"给这段文字配画面"时使用。
whenToUse: 用户给出剧本/分镜/文案/一句话创意，希望产出有配音、有电影感、可直接发布的完整视频（几秒到几十分钟）。
---

# AI 影视流水线（LingCut + LibTV + ffmpeg）

**这是一套被一部 25 分钟古装片（180+ 镜头、成本约 23 元）实战验证过的流程。**

---

## 三十秒速览

```
剧本 → 结构化拆解 → 定板图 → 分镜表 → 建画布 → 生成图 → 生成视频
     → 配音/旁白 → ★返工循环 → 逐章拼接 → 混旁白 → 拼卷 → 交付
```

**三个最值钱的知识点**：
1. **尾帧接续法** —— 免费模型做出付费长镜（`references/04-LONGSHOT.md`）
2. **道具基底引用法** —— 解决"每封信都一样"和"字写不对"（`references/05-ASSETS.md`）
3. **返工循环** —— 占总工时 45%，要靠自动审计收敛（`references/01-PIPELINE.md` 第 ⑧ 节）

---

## 开始前必读（按优先级）

| # | 文件 | 为什么 |
|---|---|---|
| ⭐⭐⭐ | `references/01-PIPELINE.md` | **总纲**：12 阶段全流程 + 14 条铁律 |
| ⭐⭐⭐ | `references/04-LONGSHOT.md` | **尾帧接续法**：长镜头免费做 |
| ⭐⭐⭐ | `references/10-TROUBLESHOOTING.md` | **报错对照表**：99% 的坑都在里面 |
| ⭐⭐ | `references/02-LINGCUT-PROMPT.md` | 提示词规范（中文短提示 + `@图N` 引用）|
| ⭐⭐ | `references/03-CINEMATIC.md` | 电影感五条铁律（做减法）|
| ⭐⭐ | `references/05-ASSETS.md` | 道具基底法 + AI 画中文的实战规则 |
| ⭐⭐ | `references/06-CONTENT-POLICY.md` | 内容审核规避（遗体/伤害/痛苦）|
| ⭐⭐ | `references/07-AUDIO.md` | 台词归属 + 声音性别 + 旁白 |
| ⭐⭐ | `references/08-ASSEMBLY.md` | 拼接/混音/时长膨胀/漏镜检测 |
| ⭐⭐ | `references/09-DELIVERY.md` | 剪辑工作台 + 旧版恢复 + 抖音发布 |
| ⭐ | `references/11-LINGCUT-AUTOMATION.md` | 画布自动化（引擎注入 / REST API / 坑）|
| ⭐ | `references/12-CHARACTER-ASSET.md` | 角色定板模板 + 负面词表 |
| ⭐ | `references/13-DRAMA-RULES.md` | 工业化规则（段缝衔接/景别阶梯/对白四查）|
| — | `playbook/PLAYBOOK.md` | 历史经验库 + 变更日志 |
| — | `references/archive/` | 已作废但保留的（H3 官方长提示词、旧版规范）|

> **音色确定走 `libtv-voice` skill**（LibTV `seed-audio-1.0`）。
> ⚠️ 「几乎听不见」→ 生成近静音；「说书人」→ 容易出女声；
> **同一角色的多句台词必须一次生成**（分次生成 F0 会漂）。

---

## 前置条件（缺一不可，缺了就问用户）

1. 用户有 **lingcut.cn 订阅会员**，账户有余额
2. 画布「API 设置」里已配置猿拓开放平台密钥（状态显示「已启用」）
3. 本地凭据：
   - `.secrets/lingcut.json` —— `{account, password}`
   - LibTV 凭据（见 `libtv-voice` skill）
4. 环境：
   - **Node**：用于发 HTTP（**Windows PowerShell 的 TLS 是坏的**）
   - **ffmpeg**：`.tools/ffmpeg.exe` 或系统版
   - **playwright-core** + **Chromium**：自动化画布用

---

## ★ 十四条铁律（背下来，能省几天的返工）

### 提示词

1. **画面里不写情绪名词，只写动作链**
   ❌ `神情疲惫` → 面瘫脸
   ✅ `先直起腰缓一口气 → 视线扫过空店 → 嘴角想提一下没提起来 → 呼吸变浅`

2. **台词必须进提示词**（不写模型就自己编），**并且放在提示词最后**

3. **多人对话必须逐条标归属**（①②③④），并写明「问句和答句必须是不同的人」

4. **每帧重复角色外貌关键词**，不能只写名字

5. **永远不要写「静止/不动/定格」** → 会真的定格

6. **单物体特写必须加**：`★单一的一幅完整画面，绝对不要多格拼贴、不要九宫格、不要角色表排版`

7. **电影感五条固定加**：浅景深虚化背景 / 主体占 1/3 以上 / 大面积暗部留白 /
   单一主光源方向明确 / 背景只留 2-3 个可辨识元素

### 操作

8. **提示词必须从 UI 的 `contenteditable` 打进去**（只改节点数据不生效）

9. **改画布数据要用引擎 `eng.updateNodeData(id, patch, true)`**，不要直接 PUT
   （会被应用自动保存覆盖）

10. **限流 ≤5 次/分钟（含失败）** → 节流 13 秒；一批跑完再提下一批

11. **内容被拒 → 换措辞，不删剧情**（见 `06-CONTENT-POLICY.md`）

### 纪律

12. **付费前必须报备并获批**（图 0.06/张、wan3 0.3/秒、Seedance 4.2/条）

13. **覆盖成片前必须备份** —— 实测把用户旧版全片覆盖了，只能靠画布快照重建

14. **每次 QA 都要真的看图/听声音**；每次做完把新经验写回 `PLAYBOOK.md`

---

## 关键操作速查

### 登录画布

```
打开 https://www.lingcut.cn/
→ 点掉「重要通知」（按钮「我知道了」）
→ 登录（读 .secrets/lingcut.json）
→ 成功标志：顶部导航出现「订阅中心」
```

### 注入引擎

前置：**先关掉「欢迎使用 LingCut」弹窗**，否则引擎还没挂载。

用 `references/11-LINGCUT-AUTOMATION.md` 里的 fiber 遍历代码拿到引擎对象。
验证：`eng.nodeMap.size` 返回数字。

### 生成一个节点

```js
eng.selectNode(id); await sleep(1300);
const ce = [...document.querySelectorAll('[contenteditable="true"]')]
  .find(e => e.getBoundingClientRect().width > 300);
ce.focus();
const s = getSelection(), r = document.createRange();
r.selectNodeContents(ce); s.removeAllRanges(); s.addRange(r);
document.execCommand('delete', false, null);
document.execCommand('insertText', false, prompt);
await sleep(1000);
[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '↑').click();
```

### 查任务真实状态（不要信 `generating`）

```
GET /api/tasks/active/list?projectId=<id>
GET /api/tasks?projectId=<id>
```

### 批量下载画布素材

```bash
node scripts/lingcut-download-all.mjs
```
按剧情顺序编号输出到 `★网站最新/视频/` 和 `图片/`。

### 尾帧接续拆长镜

```bash
node scripts/lingcut-split.mjs <镜号> <配置.json>
```

### 拼接

```bash
node scripts/rebuild-film.mjs      # 逐章 → 三卷 → 全片（含旁白）
```

---

## 脚本清单

| 脚本 | 干什么 |
|---|---|
| `scripts/lingcut-login.mjs` | 自动登录画布 |
| `scripts/lingcut-make.mjs` | 建节点 / 改名 / 上传 / 生成 |
| `scripts/lingcut-split.mjs` | **尾帧接续拆长镜** ★ |
| `scripts/lingcut-swapimg.mjs` | 把新图接到视频节点重生成 |
| `scripts/lingcut-regen.mjs` | 批量重生成指定镜头 |
| `scripts/lingcut-download-all.mjs` | **从画布批量下载全部素材** ★ |
| `scripts/lingcut-audit.mjs` | **逐镜审计（台词/声音/特写）** ★ |
| `scripts/rebuild-film.mjs` | **逐章→三卷→全片（含旁白）** ★ |
| `scripts/build-editdesk.mjs` | **生成剪辑工作台** ★ |
| `scripts/gen-editguide.mjs` | 生成 `读我-怎么剪.txt` |
| `scripts/fetch-oldshot.mjs` | 从快照恢复旧版本镜头 |
| `scripts/contact_sheet.py` | 抽帧拼联系表 |
| `scripts/libtv-audio.mjs` | LibTV 配音（见 libtv-voice skill）|

---

## 边界（不要做的事）

- **不要**用站点自带的「剧本分析」节点（质量差，只写角色名）
- **不要**在提示词里写「配乐」（用户自己加 BGM）
- **不要**用人物三视图做视频参考（会加剧漂移）
- **不要**直接 PUT 服务端 `canvas_data` 改数据（会被覆盖）
- **不要**在没有 Node 的情况下用 PowerShell 发 HTTP（TLS 坏）
- **不要**用 `browser_*` 工具做画布自动化（调不了 `setInputFiles`；
  且 Chrome PNA 禁止页面访问 127.0.0.1）→ **自己起 Playwright**
- **不要**默默花钱
- **不要**在交付文件里放凭据（账号密码 / API key）
- 用户已有的项目**只读参考，不要写入**

---

## ★ 这个 skill 怎么变强

**每次做完，把新发现追加到 `playbook/PLAYBOOK.md` 的变更日志，并补进对应的 references。**

这是唯一的机制。这份文档里每一条"实测踩坑"，
都是有人真的烧过钱、返过工之后写下来的。
