# 平台路由

网站和登录策略会变化；验收以 docs/validation.md 的样本、日期和阶段为准。
yt-dlp 的官方支持列表也说明列出的站点不保证一直可用。

## 抖音

默认 `--backend auto` 使用 Chrome/OpenCLI 后台命令桥，不导出 Cookie。
播放器必须加载当前作品；读取匹配作品的公开文案/作者和合并 MP4。
限制：至少 720p、静态合并 MP4、最多 50 MiB、douyinvod.com；不覆盖直播、图文、分离音视频。
需本人已登录 Chrome、OpenCLI Browser Bridge 已连接；不是无浏览器运行。
分享链接先解析并核对作品 ID。失败不自动转前台 FetchV。
匿名 yt-dlp 可显式 `--backend yt-dlp` 试验，但不把官方 extractor 的存在当成功。

## B站

默认 yt-dlp，支持 BV/av 与 ?p= 分P定位、b23.tv 分享解析。
下载 ≤720p 视频并合并音轨，限制单视频、不下载整合集。
访问受限时报告，浏览器 Cookie 读取需由用户明确选择，不自动尝试账号或付费路径。

## 小红书

接受 explore/discovery/item/search_result 与 xhslink 分享链接。
默认 yt-dlp；完整分享 URL 中的 xsec_token 仅用于请求，存储剥离后的来源。
匿名网页可能没有完整状态，失败时可显式 `--backend browser` 使用已登录页面的
__INITIAL_STATE__ 中目标 note，读取可用的合并媒体流，浏览器内传输 ≤50 MiB。
图文笔记返回 image_only_post；没有视频就不生成视频字幕。
临时 token、媒体签名、账户状态、Cookie 不写入知识卡/公开回执。

## YouTube

默认 yt-dlp，支持 watch、youtu.be、shorts、embed 单视频链接。
使用 Node.js JavaScript runtime；当前版本可能还要求 yt-dlp EJS组件或其他runtime，
依赖变化时参照官方文档。默认不使用账号 Cookie，不下载列表或直播。

官方参考：

- https://github.com/yt-dlp/yt-dlp
- https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
- https://github.com/yt-dlp/yt-dlp/wiki/EJS
- https://github.com/jackwener/opencli

没有稳定凭据/页面状态时，仍可用用户已经取得的本地文件完成后续解析。
本地文件成功不等于原站 URL 下载成功，必须分别报告。
