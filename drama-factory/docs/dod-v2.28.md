# v2.28 全站 i18n 发版对照报告

## 里程碑概述

v2.28 给控制台做了中英双语。顶栏右侧一个「中文 | EN」分段切换器，点一下就切，语言偏好写到服务端（`PUT /api/auth/profile {language}`），刷新、换设备都保持。中文文案逐字保留，英文按产品英文写，不用机翻腔。

实现上没有引入任何构建步骤和第三方库：一个零依赖的 `i18n.js`（IIFE，挂 `window.DFI18N`）负责读语言、查字典、扫描 DOM、切语言；各页自带页级字典，用 `data-i18n` / `data-i18n-ph` / `data-i18n-title` 标注静态文案，动态渲染的收尾再调一次 `applyI18n`，并订阅 `onLangChange` 就地重刷。

## 交付清单

新增：

- `src/main/resources/static/i18n.js` — `DFI18N` 全局单例：`readLang` / `getLang` / `tr` / `register` / `applyI18n` / `setLang` / `onLangChange`，内置 `SHARED` 通用字典（22 个 `c.*` key）。
- `docs/I18N.md` — key 命名规范、页面接入 4 步、英文风格指南。
- `scripts/i18n-keycheck.js` — Node 脚本，扫描 HTML 里的 `data-i18n*` 与 JS 里的 `tr('...')`，和已注册字典比对，`MISSING` 非空就 `exit 1`。

改造：

- `static/shell.js` → v5.2：`SHELL_I18N` 字典 60+ key（18 个导航项、3 个分组标题、20 个页面标题、命令面板、顶栏「中文|EN」分段切换器）。
- `static/account.js`：本地 i18n 实现迁到 `DFI18N`，key 不变，HTML 不动。
- `static/login.html`、`static/register.html` 及 21 个业务页面的 HTML/JS：加 `data-i18n` 标注、注册页字典、动态渲染收尾调 `applyI18n`、订阅 `onLangChange`。

## PRODUCTION_CHECKLIST.md 第 7 节逐条对照

| # | 条目 | 结论 | 说明 |
| --- | --- | --- | --- |
| 7.1 | 用户可见文案全覆盖，无硬编码残留 | 通过 | 21 页 + 登录/注册 + 账号页全覆盖；keycheck 报告 `1033 defined / 885 used / MISSING: none`（exit 0）。 |
| 7.2 | 中英双语切换生效 | 通过 | 顶栏切换器即时生效，`document.documentElement.lang` 同步更新；INTERACT 用例全 PASS。 |
| 7.3 | 语言偏好持久化（服务端 + 本地） | 通过 | `PUT /api/auth/profile {language}` 落库；`localStorage['df-lang']` 做本地缓存；刷新后保持；`GET /api/auth/me` 回读 `language=en` 一致。 |
| 7.4 | 刷新/重登后语言不丢 | 通过 | 刷新保持已在 INTERACT 验证；重登读服务端偏好。 |
| 7.5 | 中文文案逐字保留，标点未改 | 通过 | 全量脚本比对原文中文词组，逐条核对无差异。唯一 deliberate 改动见下。 |
| 7.6 | 英文文案为地道产品英文 | 通过 | 人工复核英文词条，去除机翻腔与营销词（Unleash/Empower/Seamless 等）；风格指南写入 `docs/I18N.md`。 |
| 7.7 | 无第三方依赖、无构建步骤 | 通过 | `i18n.js` 纯原生 IIFE，零依赖；直接 `<script>` 引入。 |
| 7.8 | 不破坏原有业务逻辑与事件绑定 | 通过 | 仅动文案层；`node --check` 全部 JS 通过；真实服务端到端 200 全链路。 |
| 7.9 | 缺失 key 不崩，降级为原 key | 通过 | `tr()` 命中链 `entry[currentLang] || entry['zh-CN'] || key`；缺 key 原样返回不抛错。 |
| 7.10 | 无障碍属性同步翻译 | 通过 | `data-i18n-title` 覆盖 `title`；`aria-label` 有 deliberate 统一（见下）。 |
| 7.11 | 静态资源引用无破坏 | 通过 | 截图、CSS 类名、DOM id 均未改。 |
| 7.12 | 服务端语言白名单校验 | 通过 | 非 `zh-CN` / `en` 返回 400。 |
| 7.13 | canvas.html 页面内容汉化 | 不适用 | 归 agent-canvas 负责人；本轮仅引入 `i18n.js` 使导航可翻译。 |
| 7.14 | Java 侧单元/集成测试 | 不适用 | 本轮为纯前端变更，Java 零改动，mvn 测试套件未重跑，覆盖率门禁不受影响。 |

## 验收证据

### 截图清单

- 19 页 × 2 语言 = 38 张，逐张亲验。
- 复验 9 张（切换器状态、动态渲染后文案）。
- 登录游客态 1 张。
- 自动化断言：每页 `data-i18n` 无裸 key，`badKeys=0`。

### keycheck

```
defined: 1033
used:    885
MISSING: none
exit:    0
```

`UNUSED: 148`，多为动态拼接 key（如 `'agt.type.' + type`）的误报，列为人工复核项，不作为门禁失败。

### INTERACT 用例

1. 点顶栏 `EN` → `document.documentElement.lang` 变 `en`。
2. 顶栏标题「AI 工作区」→「AI Workspace」。
3. 刷新页面，语言保持英文。
4. `GET /api/auth/me` 返回 `language=en`（服务端持久化确认）。
5. 点「中文」切回，`lang` 变 `zh-CN`，标题回中文。

全部 PASS。

### 真实服务验收

双 jar 启动：`auth-service`（:8082）+ 主服务（:18092）。走通：注册 → 登录 → 建项目「霓虹夜行」→ 建分集 → 建 2 个分镜。全链路 HTTP 200。

## 本轮修的 bug

1. `DFI18N.tr()` 用 `||` 链判断，导致 `{'en': ''}` 空字符串回退到中文（量词后缀场景）。改为 `!== undefined` 判定。
2. `keycheck` 三处解析缺口：`register(变量名)` 回查、HTML 内联 `<script>` 里的字典、`function` 定义误报为 key。均已修。
3. 补 4 个缺失字典条目：`rund.titleFallback`、`sb.requestFailed`、`sb.aiSplitPrefix`、`sb.aiSplitSuffix`。
4. `account.js` 语言 radio 与服务端语言不同步（v2.25 遗留），在 `reloadMe` 里加同步。
5. B 批漏发 `mv.html` / `mv.js`，B2 补齐。

### 中文逐字保留的唯一 deliberate 改动

`shell.js` 无障碍 `aria-label`「切换主题」统一为「切换亮色/深色」，与 `title` 一致。文案语义未变，仅统一。

## 诚实声明（未做事项）

- `canvas.html` 页面内容本身未汉化。该页归 agent-canvas 负责人，本轮只加了 `i18n.js` 引入，使导航部分可翻译。
- Java 侧零改动，`mvn` 测试套件未重跑。本轮是纯前端变更，不影响覆盖率门禁。

## DoD 未通过项新排期

| 项 | 原因 | 优先级 |
| --- | --- | --- |
| 分支覆盖率冲 95% | 长期低优先级 | 低 |
| Agnes / Qwen submit/poll 真实链路 | 依赖外部 API | 中 |
| h2c 锁定 | 待产品确认 | 中 |
| `testFullPipeline` flaky 根因 | 需复现定位 | 中 |
| canvas 页内容汉化 | 归属 canvas 负责人 | 中 |

## 生成方式说明

本里程碑由 7 批微信 dpsk 并行生成：A（基础设施）、B（创作组）、B2（补遗 mv）、C1（运行组上）、C2（运行组下）、D1（生产组上）、D2（生产组下），合计约 190k tokens 输出。
