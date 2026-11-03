# AI MV：导入已有音频

作词作曲是非必需步骤。有现成好听的歌曲时，可直接导入音频，跳过作词作曲。

## 流程

1. **导入**：`POST /api/mv/import`（multipart：file/title/lyrics/mood/style）
   - 仅 mp3 / wav / m4a，≤100MB；文件自动进入资产库（标签 `mv-audio`）
   - 歌词可选：填写则按文本建时间轴、渲染烧录字幕；不填则走纯音乐分镜（按 10 秒切段，无字幕）
2. **Run 步骤**：作词、作曲标记为 `SKIPPED`（时间线注明"已跳过作词作曲（用户导入音频）"），分镜→视频生成→剪辑→质检正常执行
3. **限制**：导入模式下调 `/lyrics`、`/compose` 会被拒绝（已有用户音频）

## 前端

`mv.html` 步骤一有两个选项卡：**AI 创作歌曲**（原流程）/ **导入已有音频**（上传进度条 + 音频试听）。导入成功后步骤 1、2 显示为"已跳过"态，直接进入分镜。

## 相关

- 迁移：`V14__mv_import_source.sql`（`mv_songs.source`：AI / IMPORT）
- 缺参返回 400（`GlobalExceptionHandler` 处理 `MissingServletRequestParameterException`）
