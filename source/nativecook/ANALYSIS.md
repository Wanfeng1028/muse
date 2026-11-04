# Native Cook 镜像分析结论

来源：`https://nativecook.dev/`，取材时间 2026-11-04（北京时间）。本文件是仓内元数据，不属于镜像页面本身。

## 站点身份

Native Cook：移动端 UI block 库。首页宣称 766 个 block，每个 block 三个提示词；实测 766 与宣称一致。
三栈：React Native（Expo、Reanimated）、Swift（SwiftUI、iOS 17+）、Kotlin（Jetpack Compose、M3）。
使用流程（原站文案）：看 block 视频、选栈、复制提示词给 coding agent、按视频纠偏。
定价口径（原站文案）：现阶段全部免费；实测全部 block 的 `pro` 均为 false。

## 技术栈（从 HTML 与 JS chunk 实测，非猜测）

- 框架：Next.js + Turbopack（`_next/static/chunks/*`，RSC `self.__next_f` 载荷；含 `turbopack-*.js` runtime）。
- 路由：App Router 式尾斜杠路径（`/`、`/blocks/`、`/blocks/<slug>/`、`/faq/` 等，全部带尾斜杠规范 URL）。
- `/blocks/?cat=<id>` 与 `/credits/?block=<slug>#request` 是同一页的客户端筛选/入口，不是独立路由。
- `/sign-in/`、`/login/`、`/search/`、`/categories/`、`/about/`、`/blog/` 均为 Next 404 壳（不建）；搜索是站内 ⌘K 命令面板，无独立路由。
- 登录走 `api.nativecook.dev`（`/auth/*`、`/me/*`、`/billing/*`）；`/saved/`、`/account/` 未登录仅为空壳标题。
- 主题与三栈选中态存 localStorage 键 `native-cook-v1`（含 theme、platform 持久化；三栈选中态跨页保持与此一致）。

## 页面与 block 数

- 页面 HTML 775 个 = 9 个非 block 页（首页、`/blocks/`、faq、support、terms、privacy、credits、pricing、signin）+ 766 个 block 页。
- block 页 766 个，slug 与首页宣称一致，三源交叉 0 差异（见“枚举方法”）。
- 提示词 JSON 2298 个（766 × rn / swift / kotlin），原站客户端按需调 `GET /blocks/<slug>/prompt?platform=rn|swift|kotlin` 返回 `{"prompt": ...}`；提示词不在 HTML 里。
- 视频 766 个 mp4（36KB–16.8MB，实测最小 37,180 字节、最大 17,232,390 字节），统一形如 `https://media.nativecook.dev/videos/<slug>-<8位hex>.iphone-18-pro.mp4`，页内以 `#t=0.001` 作首帧；无海报图文件。
- 静态资源 27 个（`_next/static/`：16 个 JS、2 个 CSS、9 个 woff2 字体；7 个为 2026-11-04 验收补取，见“取材缺口与闭合”）+ 图片 3 个（`og.png`、`icon.svg`、`apple-icon.png`）+ `robots.txt` + `sitemap.xml`。
- 目录数据：公开 API `https://api.nativecook.dev/catalog`（字段 id、name、cat、catName、pro、added、video、spec、design、designAuthor），另有 `catalog.json` 副本（本镜像根目录的 `catalog.json` 即由此来）。
- 设计来源 `design` 664/766 有值，`designAuthor` 662/766 有值。

## 媒体托管方式

- 视频：`media.nativecook.dev`（见上）；页面视频标签与 RSC 载荷均引用同一地址。
- 图片：站内根路径（`/og.png`、`/icon.svg`、`/apple-icon.png`，og 图带 `?v=2` 查询串）。
- 字体：`/_next/static/media/*.woff2`（CSS 内相对引用 `../media/*.woff2`）。
- 提示词内含 GitHub 外链（`github.com/Native-Cook/native-cook` 及 `raw.githubusercontent.com` 的源码引用），属提示词正文，全部原样保留，未改写。

## 枚举方法

1. `robots.txt` 指明 `Sitemap: https://nativecook.dev/sitemap.xml`；sitemap 含 773 条 URL：7 页 + 766 条 block URL。
2. 交叉核验：`/blocks/` 页 RSC 载荷内嵌的 766 条视频 URL slug 集合与 sitemap slug 集合完全相等（0 差）；catalog 的 766 条 `id` 集合亦完全相等（0 差）。三源一致，766 可信，无缺口。
3. 首页宣称“766 blocks · three prompts each”与实测一致。
4. 建站时复核：manifest slug 表、catalog id 表、block 页目录、提示词 slug 表四者再次全等；每 block 页均含自身视频 URL（0 缺失）；catalog 视频文件名与 raw 视频文件全等。

## 分类 18 / 19 口径

- API 分类表 19 项（含 overlays，0 个 block），按 sort 排序：navigation、lists、onboarding、sheets、modals、gestures、forms、charts、animations、media、buttons、progress、cards、inputs、pickers、text、overlays、playground、splash。
- UI 可见分类 18 项（overlays 未出现在筛选条/跑马灯）；筛选条与跑马灯按 18 项做。
- 各分类 block 数：cards 84、onboarding 75、gestures 55、progress 53、media 52、buttons 49、pickers 43、lists 43、forms 41、charts 38、inputs 37、navigation 36、modals 33、text 32、playground 26、sheets 24、animations 24、splash 21、overlays 0。

## 提示词 API 模式（原站）与静态映射

- 原站：`GET https://api.nativecook.dev/blocks/<slug>/prompt?platform=rn|swift|kotlin`，返回 `{"prompt": "..."}`；JS chunk 里 `fetchPrompt(api(), id, platform)` 按需加载（这就是三栈切换时按钮约 1 秒变灰禁用的原因）。
- 静态版：见 `REWRITES.md` R3–R5；API 基址改为空（同源），提示词路径改为 `/prompts/<slug>.<platform>.json`，目录改为 `/catalog.json`；其余 `/auth/*`、`/me/*`、`/billing/*`、`/credit-requests` 请求在静态版里同源 404，属已知后端局限。

## 渲染参考对照（与 live browser 实测 5 页的对照）

- 主页 11 个 block 链接：源码 href 与渲染参考列出的 11 条完全一致（hero 3、Featured 4、Recently added 4）。
- 三例视频 hash 一致：monster-age-picker-2648fa0a、expressive-orb-93332059、ribbon-road-onboarding-64e87ac6。
- FAQ：源码含 4 个手风琴条目，与渲染参考“4 个条目”一致。
- block 页结构：源码含面包屑、Previous/Next、视频、Save/Copy link、描述、Category/Added/Stacks/Design/Author、credits 纠错入口、三栈提示词切换、More in 分类 4 卡片，与渲染参考一致。
- 唯一口径差异：API 分类表有 19 项（含 overlays），但 UI 可见分类为 18 项（overlays 0 block，未在筛选条/跑马灯出现）。以渲染为准：筛选条按 18 项做，overlays 不出。
- 源码与渲染的出入：除上述 18/19 分类口径外，本轮建站未发现源码与渲染参考的其他出入；RSC notFound 兜底模板属模板残留（见 README），已原样保留。

## 取材缺口与闭合

- 字体（2026-11-04 验收时已闭合，不再是缺口）：CSS 引用 9 个 woff2 文件，取材时 raw 里只有 2 个（即页面 preload 的 2 个：`051742360c26797e-s.p.1bkzbscqrt8rl.woff2`、`2aa781f449db21e3-s.p.1pg2nifvadz06.woff2`）。验收时按 CSS 期望的相对路径 `/_next/static/media/<文件>` 从原站直接拉取缺失的 7 个，全部 HTTP 200、首 4 字节均为 `wOF2` 魔数、一次成功（无需重试），已放进镜像 `_next/static/media/`，CSS 引用现 9/9 解析：
  - `04c5164763c40239-s.1kd-r_s9smv5m.woff2`（1,664 字节，JetBrains Mono 400/500/600 非拉丁子集）
  - `26f284dcc38c84c0-s.3hlisc-pwq13z.woff2`（8,892 字节）
  - `6260001f568fa40d-s.0c4siir8-ephk.woff2`（30,636 字节，Bricolage Grotesque 扩展拉丁子集）
  - `6a5386fd6038edbe-s.3_z45zcoc-xoz.woff2`（11,596 字节）
  - `7e7f32a39836f228-s.0-oo9_1x_xmvg.woff2`（6,800 字节）
  - `caa77eaf0c6cae2c-s.31vfkycla13v0.woff2`（13,060 字节，Bricolage Grotesque 越南文子集）
  - `fa39153a3fc630ba-s.36fqqi66-3tjb.woff2`（5,872 字节）
  - 补取合计 78,520 字节；git 版由 3102 个文件、78,466,908 字节变为 3109 个文件、78,545,428 字节；静态资源由 20 个变为 27 个。
- `/saved/`、`/account/` 无 HTML 原稿（需登录项），未建页；见 README 局限清单。
