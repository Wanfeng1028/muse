# 视频多源调度策略（VIDEO_SCHEDULING）

> 目标：一条分镜可以走不同的视频源，管线统一调度、失败自动换源。
> 流程：分镜（shot list）→ 按镜头分段生成 → ffmpeg 拼接成片。

## 1. 可用资源一览（2026-10-16 实测）

| # | Provider 名 | 通道 | 规格 | 费用/水印 | 出片速度 | 备注 |
|---|---|---|---|---|---|---|
| 1 | `agnes` | Agnes 视频 API（agnes-video-2.5-flash） | — | 免费（待确认） | — | **优先通道**；2026-10-16 起持续 503 `video_queue_full`，恢复后自动切回 |
| 2 | `doubao` | 邮件异步通道（wanfeng6324@agent.qq.com） | 5s、720p、mp4 | 免费、无水印无字幕 | 约 1 小时一轮 | 提示词一次写完整；适合批量后台跑；状态机：派出→等待→收回 |
| 3 | `novai` | NovAI cogvideox-flash（aiapi-pro.com） | 6s、720p | 免费、**带水印** | 约 100 秒 | 双账号可轮换；**⛔ 2026-10-16 每日 5 次免费额度已用完，午夜（UTC+8）重置** |
| 4 | `qwen` | 通义万相 wan2.5-t2v-preview（DashScope） | 5s、832×480 | **⛔ 2026-10-16 免费额度耗尽，已从轮换摘除** | — | 中文 prompt 理解好；**额度恢复前禁止调用**（防按量扣费），`submit()` 已加硬拒单 guard |
| 5 | `painted` | 自有 painted-animation（p5.js + Chromium + ffmpeg） | 可配 | 免费、无水印 | 慢（软件渲染，单帧分钟级） | 风格化水彩镜头；通用场景模板，手工场景质量更高 |
| 6 | `kling` | Kling 可灵 | — | 待用户注册拿额度 | — | 额度到了再接 |
| 0 | `mock` | 本地 ffmpeg 测试片段 | 可配 | 免费 | 秒级 | 仅开发联调，不进正式成片 |

## 2. 优先级与降级链

全局默认链（`drama.video.provider` 未指定时）：

```
agnes → novai → doubao → painted
```

- `agnes` 永远排第一：用户亲定 Agnes 优先。503/限流时自动降级，恢复后自动回切（由 `ResilientVideoProvider` 熔断 + `VideoProviderRouter` 链式降级实现）。
- `qwen`（wan2.5-t2v-preview）：2026-10-16 免费额度耗尽，已摘除；`QwenVideoProvider.submit()` 有硬拒单 guard，额度恢复后删 guard 即可恢复。
- `mock` 永不进正式链，只在 `drama.video.provider=mock` 时单独使用。

## 3. 按镜头类型分流（ShotVideoRouter 规则）

分镜可设 `preferredProvider`（显式指定，最高优先级）。未指定时按提示词关键词自动分流：

| 镜头特征（videoPrompt/description 关键词） | 走 | 理由 |
|---|---|---|
| 卡通 / cartoon / 皮克斯 / 动画 / 可爱 | `doubao` | 无水印，卡通质量已验证 |
| 写实 / 真人 / realistic / 电影感 | `novai` | 出片快，写实尚可（接受水印） |
| 中文文字 / 水墨 / 国风 | `painted` | 自有水彩管线，风格可控（原走 qwen，额度耗尽已切换） |
| 水彩 / 手绘 / watercolor / 风格化 | `painted` | 自有管线，风格可控 |
| 无匹配 | 走全局默认链 | — |

分流命中后仍走降级链：首选失败 → 按第 2 节链条顺延（跳过已试过的）。

## 4. 豆包异步通道状态机

邮件一小时一轮，不适合同步等待。`DoubaoEmailVideoProvider` 把异步映射到现有 `submit`/`poll` 契约：

```
submit(shot) → 发邮件（主题含 [剧坊分镜#<shotId>]，正文一次写完整规格）
             → 返回 taskId = "doubao:<gmail-thread-id>"
poll(taskId) → 查 Gmail 线程新回复
             → 无回复：PROCESSING（继续等）
             → 有回复：解析正文 "视频链接：URL" 或附件 → COMPLETED(videoUrl)
             → 回复明确说失败：FAILED
```

- 去重：同一 shot 重复 submit 先查是否已有进行中的 doubao 任务（按主题标签查线程），避免一小时一轮里重复派活。
- 超时：派出 6 小时无回复 → FAILED，转降级链。

## 5. 资源调配原则

- 一次只跑一个重型任务（VM 只有 2 核）：分镜**串行**派发，不并发烧所有源。
- 免费额度优先烧快过期的；豆包邮件通道适合夜间批量（一次写 N 封，醒来收）。
- 成片拼接前统一规格：`FfmpegService.concatClips` 要求同分辨率/编码，必要时先转码对齐到 1280×720。
- 水印说明：novai 免费档带水印，正式成片尽量用 doubao/qwen/agnes 的镜头；novai 镜头仅作占位或用户接受水印时使用。

## 6. 待接入

- `kling`：用户注册拿到额度后接 `KlingVideoProvider`，定位高质量主力。
