# Native Cook 静态镜像站

来源：`https://nativecook.dev/`（移动端 UI block 库：766 个 block，每个 block 三个平台提示词）。
性质：原站公开内容的静态镜像归档。页面、文字、提示词、描述、FAQ、布局、组件、导航、交互均按原站原样保留；唯一改动是为单机静态运行所必需的 URL 改写，逐条见 `REWRITES.md`。分析结论见 `ANALYSIS.md`。

## 归档分包（必读：git 版缺视频不是内容差异）

原站取材总计 3865 个文件、986,564,490 字节（约 940.9 MB），超过 git 实际承载（约 500 MB），因此分两包：

- git 版（本目录）：完整站点代码与页面，共 3109 个文件、78,545,428 字节（约 74.9 MiB / 78.5 MB）= 镜像 3106 个 + 仓内文档 3 个：
  - 页面 HTML 775 个（9 个非 block 页 + 766 个 block 页）
  - 提示词 JSON 2298 个（`prompts/<slug>.rn|swift|kotlin.json`）
  - Next.js 静态资源 27 个（`_next/static/`：16 个 JS、2 个 CSS、9 个 woff2 字体；2026-11-04 验收时从原站补取了取材缺失的 7 个 woff2，见 `ANALYSIS.md`）
  - 图片 3 个（`og.png`、`icon.svg`、`apple-icon.png`）
  - `catalog.json` 1 个、`robots.txt`、`sitemap.xml` 各 1 个
  - 本 README、`ANALYSIS.md`、`REWRITES.md` 3 个仓内文档（元数据，不属于镜像页面本身）
- Drive 完整包（另行组装，不在本目录）：git 版全部文件 + `videos/` 目录（766 个 mp4，共 907,721,224 字节，约 865.7 MB）。

页面里的视频地址统一指向 `/videos/<slug>-<8位hex>.iphone-18-pro.mp4`。从 Drive 包取视频的方法：把 Drive 包里的 `videos/` 目录整个放到本镜像根目录（与 `index.html` 同一级），即完整；不要改名、不要放进子目录。不许用占位视频冒充；git 版里视频链接解析不到是预期缺失，见下文链接检查结果。

## 本地起服

必须从镜像根目录起服（站内路径均为根绝对路径，如 `/_next/`、`/videos/`、`/catalog.json`、`/prompts/`），例如：

```
cd <本目录>
python3 -m http.server 8000
```

然后访问 `http://localhost:8000/`。不要用 `file://` 直接打开（JS chunk 的 fetch 在 file 协议下不可用），也不要把本站挂在子路径下起服（根绝对路径会断）。

## 静态版里继续工作的行为

原 JS chunk 原则上原样保留（只改写 fetch/资源地址，见 `REWRITES.md`），以下行为在静态版里继续工作：

- 三栈切换（React Native / Swift / Kotlin）：选中白色胶囊、切换约 1 秒变灰禁用后恢复、选中态跨页保持（localStorage 键 `native-cook-v1`）
- Copy 提示词（文案随选中栈同步变；提示词来自本地 `prompts/`，无需登录）
- FAQ 手风琴（一次一项）、hero 样机轮播、分类跑马灯、卡片更多菜单
- 明暗切换（浅色米白底与深色近黑底，黄色点缀不变）
- ⌘K 命令面板（数据走本地 `catalog.json`）
- 播放器控制条（播放/暂停、进度、时间、倍速、静音、全屏）、Previous/Next、More in 分类
- 分类筛选：`/blocks/?cat=<id>` 与 `/credits/?block=<slug>#request` 是同一页的客户端筛选/入口，不是独立路由

## 已知动态 / 后端局限（静态版无法完成的部分）

- 登录与账号：登录页 `/signin/` 本身在（GitHub / Google / 邮箱入口均在），但认证走原站 `api.nativecook.dev`（`/auth/*`、`/me/*`、`/billing/*`），静态版里这些请求会同源 404，登录无法完成。这是预期局限，不是缺页。
- Save（收藏）、个人资料、账单/订阅、credit 申请：同上，需原站后端，静态版里不可用。区块页点 Save（未登录）按原站行为跳 `/signin/`。
- `/saved/` 与 `/account/`：原站未登录时仅为空壳标题；本次取材未拉取到这两个页面的 HTML（需登录项），故镜像里没有这两个静态页，页眉/页脚指向它们的链接（共 2328 处）在静态版里解析不到对应文件。这是有意不建（没有原稿可抄，不编造占位页），不是漏建。
- `/sign-in/`、`/login/`、`/search/`、`/categories/`、`/about/`、`/blog/`：原站本身就是 Next 404 壳，故不建（与取材结论一致）。
- 字体缺口已闭合（2026-11-04 验收补取）：CSS 引用的 9 个 woff2 文件现已齐全（取材时 raw 里只有 2 个，验收时从原站 `/_next/static/media/` 补取 7 个，均为 HTTP 200 且 wOFF 魔数校验通过，共 78,520 字节）；补取前对应字重回退备用字体的状态已消除。补取清单见 `ANALYSIS.md`。
- `sitemap.xml` 与 `robots.txt`：原样保留原站绝对地址（爬虫文档，改写会破坏其格式要求），见 `REWRITES.md`。
- 视觉零差异不宣称：本地 Playwright 渲染原站已知失败；渲染实测与 live browser 比对是后续步骤，本目录只做源码与结构自查（结果见下）。

## 自查结果（建站时实测）

- 数量对账：775 页、2298 提示词 JSON、27 静态（补取 7 个 woff2 后）、3 图片、1 catalog、robots/sitemap 各 1，镜像 3106 个 + 仓内文档 3 个 = git 版 3109 个；766 视频在 raw 里齐全（只核对，不进 git）。
- 提示词一字不改：2298 个提示词 JSON 与 raw 的 sha256 全部一致（0 不符）；catalog 除视频地址前缀改写外，反向还原后与 raw 字节完全一致。
- 链接检查（2026-11-04 验收复核，可见属性口径、原始出现次数、去查询串/片段、目录按 index.html 计）：页面 href/src 共 30,819 处解析到本地文件；视频引用 3853 处（可见属性；含 RSC 载荷内重复引用共 8467 处，与 `REWRITES.md` R1 一致；去重 766 个文件）全部对应 raw 视频文件，在 git 版里为预期缺失、Drive 包里补齐；本地缺失（除视频与 `/saved/`、`/account/` 后端链接外）为 0；站内引用 slug 全部在 766 slug 表内（未知 slug 为 0）；第三方外链（社交、Design 来源、Author 外链等）6650 处一律未动。注：建站自查曾写 30,816 处，验收复核为 30,819 处（差 3 处为计数口径差异，缺失数仍为 0），以验收复核为准。
- 五页结构抽查（主页、faq、monster-age-picker、expressive-orb、ribbon-road-onboarding）：按 live 渲染参考逐项核对全部通过（页眉、hero、Featured、跑马灯 + 18 胶囊、How it works、Recently added、CTA、页脚；FAQ 手风琴；区块页面包屑、Previous/Next、播放器、信息卡、提示条、More in）。细节见 `ANALYSIS.md`。
- RSC 残留：Next.js block 页 RSC 载荷里固定含一段 notFound 兜底模板（含 “Page not found” 字样），属模板残留而非 404，已原样保留，未擅自剥离；766 页已用标题与视频 URL 双重核验全部为正文。
