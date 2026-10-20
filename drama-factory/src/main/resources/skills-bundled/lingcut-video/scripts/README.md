# scripts —— 脚本说明

**所有脚本共享 `_config.mjs` 的配置。安装后只需要改这一个文件。**

---

## 一、安装后要做的唯一一件事

打开 `_config.mjs`，确认/修改这几行（或用环境变量覆盖）：

```bash
LINGCUT_PROJECT      你的项目根目录（放剧本、成片的地方）
LINGCUT_TOOLS        tools 目录（ffmpeg / chrome-profile 放这儿）
LINGCUT_PW           playwright-core 的 index.js 路径
LINGCUT_CHROME       Chromium 可执行文件
LINGCUT_FFMPEG       ffmpeg 可执行文件
LINGCUT_SECRETS      凭据目录（默认 <项目>/.secrets）
LINGCUT_PROJECT_ID   画布项目 ID
```

自检：

```bash
node -e "import('./_config.mjs').then(m=>console.log(m.PROJ, m.CHROME, m.FFMPEG))"
```

`_config.mjs` 会自动探测：
- `~/.dsh/profiles/desktop/node_modules/playwright-core`
- `~/AppData/Local/ms-playwright/chromium-*/chrome-win64/chrome.exe`
- `<tools>/ffmpeg.exe`

---

## 二、脚本清单

### 画布自动化

| 脚本 | 干什么 |
|---|---|
| `_config.mjs` | **共享配置**（路径、启动浏览器、注入引擎）|
| `lingcut-login.mjs` | 自动登录画布（读 `<项目>/.secrets/lingcut.json`）|
| `lingcut-make.mjs` | 建节点 / 改名 / 上传 / 触发生成 |
| `lingcut-audit.mjs` | **逐镜审计**：分镜表 vs 画布，找出①缺台词②台词不全③没写声音方向 |
| `lingcut-download-all.mjs` | **从画布批量下载全部素材**（按剧情顺序编号）|

### 生成与返工

| 脚本 | 干什么 |
|---|---|
| `lingcut-split.mjs` | **★ 尾帧接续拆长镜**（A 段 → 抽尾帧 → B 段 → 拼接）|
| `lingcut-swapimg.mjs` | 把新图接到视频节点，重生成 |
| `lingcut-regen.mjs` | 批量重生成指定镜头 |
| `lingcut-extend.mjs` | 延长时长 + 补全台词 + 重生成 |
| `lingcut-fix-dialog.mjs` | 批量补台词（按 `todo-dialog.json`）|
| `fetch-oldshot.mjs` | **从画布快照恢复旧版本镜头**（对比新旧 src，从 OSS 拉回）|
| `rename-oldshot.mjs` | 把拉回的旧文件改成有意义的镜号名 |

### 拼接与交付

| 脚本 | 干什么 |
|---|---|
| `rebuild-film.mjs` | **★ 逐章 → 三卷 → 全片（含旁白）** |
| `mux-narration.mjs` | 给章节混旁白（`apad` 补到视频长度）|
| `build-editdesk.mjs` | **★ 生成剪辑工作台**（新/旧/音频/参考/素材）|
| `gen-editguide.mjs` | 生成 `读我-怎么剪.txt`（带每镜真实时长）|

### 工具

| 脚本 | 干什么 |
|---|---|
| `concat.mjs` | 无损拼接 |
| `mix-dialogue.mjs` | 混对白 |
| `qa-frames.mjs` | 抽帧 QA |
| `contact_sheet.py` | 抽帧拼联系表 |
| `crop_char_sheet.py` | 角色三视图裁成大头照+全身照 |
| `get-ffmpeg.mjs` | 自动获取 ffmpeg |

### 音频（配套 `libtv-voice` skill）

| 脚本 | 干什么 |
|---|---|
| `tts.mjs` | MiniMax TTS |
| `voice-design.mjs` | LibTV 音色设计 |
| `qiniu-upload.mjs` | 上传七牛拿公网 URL |

### 内部

| 脚本 | 干什么 |
|---|---|
| `_parameterize.mjs` | 把硬编码路径替换成 `_config.mjs` 引用（**分享前跑一次**）|

---

## 三、典型使用顺序

```bash
# 0. 配置
vim _config.mjs

# 1. 登录
node lingcut-login.mjs

# 2. 建节点 + 生成
node lingcut-make.mjs new          # 建节点
node lingcut-make.mjs gen          # 触发生成

# 3. 审计（找出缺台词/缺声音的镜头）
node lingcut-audit.mjs

# 4. 返工
node lingcut-regen.mjs "B05,C06,D04"
node lingcut-split.mjs L11 split-L11.json      # 长镜拆分
node lingcut-swapimg.mjs swap-K.json           # 换图重生成

# 5. 下载全部素材
node lingcut-download-all.mjs

# 6. 拼接成片
node rebuild-film.mjs

# 7. 生成剪辑工作台
node build-editdesk.mjs
node gen-editguide.mjs
```

---

## 四、写新脚本时的注意

1. **不要硬编码路径** —— 从 `_config.mjs` import
2. **启动浏览器用 `launch()`**，注入引擎用 `injectEngine(page)`
3. **改画布数据用 `eng.updateNodeData(id, patch, true)`**，不要直接 PUT
4. **节流 13 秒**（限流 ≤5 次/分钟，含失败）
5. **查任务状态用 `TASKS(PROJECT_ID)`**，不要信 `generating` 标志

---

## 五、分享前必做

```bash
# 检查有没有残留的个人路径
grep -r "C:/Users/" . --include="*.mjs"
# 或
node _parameterize.mjs --dry
```

**必须为空。** 有残留就跑 `node _parameterize.mjs` 自动替换。
