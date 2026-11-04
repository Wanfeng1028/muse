# URL 改写规则（静态镜像专用）

原则：只改写本站自有三域名（`nativecook.dev`、`api.nativecook.dev`、`media.nativecook.dev`）的资源地址，且只改到单机静态运行所必需的程度；内容（文字、提示词、图片、视频本身）一字不改。以下规则按字节替换执行，替换数均为建站实测。

## 已执行的改写

### R1：视频地址 → 本地根路径

- 原：`https://media.nativecook.dev/videos/<文件>`
- 改：`/videos/<文件>`（文件本身不变，如 `monster-age-picker-2648fa0a.iphone-18-pro.mp4`）
- 替换数：9240 处（页面 HTML 8467 处 + `catalog.json` 773 处；含渲染标签与 RSC 载荷内的重复引用，以及 `#t=0.001` 首帧片段——片段原样保留在改写后的地址后）
- 适用文件：全部 `*.html`、`catalog.json`
- 说明：静态服务器从镜像根起服即通；git 版里 `/videos/` 对应文件在 Drive 完整包里补齐（见 README 分包说明），本目录不含视频。

### R2：本站绝对地址 → 本地根路径

- 原：`https://nativecook.dev/<路径>`（含查询串，如 `/og.png?v=2`）
- 改：`/<路径>`（路径与查询串不变）
- 替换数：6202 处（页面 HTML 6201 处 + JS chunk 占位示例 1 处）
- 适用文件：全部 `*.html`、1 个 JS chunk
- 覆盖项：canonical、og:url、og:image、twitter 对应地址及其 RSC 载荷内的重复引用；credits 表单输入框的占位示例地址 `https://nativecook.dev/blocks/…` → `/blocks/…`
- 说明：站内导航、`/_next/`、图标等本来就是根相对路径，未动；本规则只剥掉原站 origin，不改路径本身。

### R3：API 基址 → 同源空地址

- 原（仅 `_next/static/chunks/3kr0_zt5zs96m.js` 1 处）：`url:"https://api.nativecook.dev"`
- 改：`url:""`
- 说明：该 chunk 的请求 helper 为 `(e.fetch ?? fetch)(e.url.replace(/\/+$/, "") + path, …)`，基址改空后全部 API 请求变为同源相对路径；配合 R4、R5 使目录与提示词走本地文件。其余 `/auth/*`、`/me/*`、`/billing/*`、`/credit-requests` 请求在静态版里同源 404，属已知后端局限（见 README），未伪造任何后端响应。

### R4：目录接口 → 本地 catalog 文件

- 原（仅上述 chunk 1 处）：`fetchCatalog` 调 `a(e,"/catalog")`
- 改：`a(e,"/catalog.json")`
- 说明：与本镜像根目录的 `catalog.json`（原 `api.nativecook.dev/catalog` 副本，仅视频地址按 R1 改写）对应；⌘K 命令面板的数据走此文件。

### R5：提示词接口 → 本地提示词文件

- 原（仅上述 chunk 1 处）：`` `/blocks/${encodeURIComponent(t)}/prompt?platform=${r}` ``
- 改：`` `/prompts/${encodeURIComponent(t)}.${r}.json` ``
- 说明：与本镜像 `prompts/<slug>.rn|swift|kotlin.json`（原 `api.nativecook.dev/blocks/<slug>/prompt-<platform>.json` 原样改名）对应；平台取值 rn / swift / kotlin 不变；提示词文件内容经 sha256 核验与原稿完全一致。

### R6：文件落点改名（非内容改写）

- `api.nativecook.dev/catalog.json` → `/catalog.json`
- `api.nativecook.dev/blocks/<slug>/prompt-<platform>.json` → `/prompts/<slug>.<platform>.json`
- `nativecook.dev/` 整树 → 镜像根（路径结构不变：`/` → `index.html`，`/faq` → `faq/index.html`，`/blocks/<slug>/` → `blocks/<slug>/index.html`，其余 6 个非 block 页同理；`_next/static/...` 路径不变；图片根路径不变）
- 视频不落 git 版：`media.nativecook.dev/videos/*` → Drive 完整包的 `/videos/*`（与 R1 地址对应）

## 有意未改写项（不是遗漏）

- 第三方外链一律不动：社交（x、Instagram、Threads、TikTok、YouTube、Facebook、LinkedIn）、Design 来源（Pinterest、Dribbble、Behance、Mobbin 等）、Author 外链、提示词正文内的 GitHub / raw.githubusercontent 源码引用。页面 href/src 统计中第三方外链 6650 处全部原样保留。
- 邮箱地址不动：`mailto:support@nativecook.dev`（联系地址，不是可 fetch 的资源地址）；JS 里的 `supportEmail` 字符串同理。
- 域名文字提及不动：JS 文案里的 “Its address on nativecook.dev”、“Paste the block's address from nativecook.dev” 等 prose，只是文字提及原站名，不是链接或资源地址。
- `sitemap.xml` 与 `robots.txt` 原文保留原站绝对地址：sitemap 的 `<loc>` 按规范必须是绝对 URL，改写为相对路径会破坏其格式；robots 内的 `Sitemap:` 行同理。这两个文件是爬虫文档，不是页面加载的资源。
- `/saved/`、`/account/` 链接不动：它们指向需登录的原站应用壳，镜像里无对应静态页（无原稿可抄，不编造）；链接本身保持原样，属已知局限。
- RSC notFound 兜底模板不动：block 页 RSC 载荷里固定含 “Page not found” 模板残留，原样保留。
- CSS 字体相对引用不动：`../media/*.woff2` 本来就是相对路径；取材时未到位的 7 个 woff2 文件已于 2026-11-04 验收时从原站补取（9/9 齐全），见 `ANALYSIS.md` 取材缺口与闭合（缺失是取材问题，不是改写造成）。
- 提示词 JSON 内容零改写：除 R6 改名外，2298 个文件与原稿 sha256 全部一致；catalog 除 R1 视频前缀外，反向还原后与原稿字节完全一致。

## 改写后残留检查

- 改写后 `*.html` / `*.js` / `*.css` / `*.json` 里 `https://media.nativecook.dev`、`https://api.nativecook.dev`、`https://nativecook.dev` 的剩余数为 0。
- 残留的 `nativecook.dev` 裸字符串仅见于上述有意未改写项（mailto、prose、sitemap/robots），无任何可 fetch 的原站资源地址残留。
