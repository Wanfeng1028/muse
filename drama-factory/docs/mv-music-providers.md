# AI MV 作曲渠道调研（2026-10-14，Keenable 已核验）

## 结论（按接入优先级）

| 排序 | 渠道 | 状态 | 说明 |
|---|---|---|---|
| 1 | MiniMax music-3.0 | **已接入**（BYOK） | 仅存量付费用户可用；官方 2026-08 起不对新用户开放。新用户走下面两条。 |
| 2 | ACE-Step（开源） | **推荐给新用户** | 阶跃星辰 + ACE Studio 联合开发，Apache-2.0，可免费商用。支持歌词生成歌曲。接入路径二选一：① StepFun 官方 API 若上架 step-music 系模型直接调（用户已有 step150api/step193plan）；② kie.ai / sunoapi.org 等聚合 API 亦有 ACE-Step（与 Suno 同一 Key 体系）。 |
| 3 | Suno 第三方封装 | 可用但有条件 | Suno 官方**无公开 API**（无开发者控制台、无自助 Key，只有受限 beta 合作）。第三方转售 $0.014–$0.111/首（2026 年中价，kie.ai 与 sunoapi.org 为同一家，仍在运营；GoAPI/PiAPI 已下线 Suno）。大陆直连不稳定，通常需代理；转售合规风险用户自担。 |

## 不推荐

- Udio / 网易天音 / 腾讯启明星：均无官方公开自助 HTTP API，仅网页版，无法 BYOK 服务端调用。
- ACE Studio 本体：偏 MIDI→人声合成工具，需要曲谱输入，不是 lyrics-to-song 一句话出歌，不符合 MV 模式"一句话主题"的交互。

## BYOK 接入策略

- Composer Provider 接口抽象：`compose(lyrics, style, apiKey) → (audioUrl, durationMs)`，MiniMax / ACE-Step / Suno-封装三实现。
- 供应商卡片制：沿用现有 provider 卡片（可配 Key、可点"测试连接"、不可用时诚实标注状态，不伪造成功）。
- 作曲失败不阻断：Run 步骤可重试/切换渠道；无可用 Key 时步骤诚实标记 BLOCKED，不输出假音频。

## 核验记录

- Keenable 2026-10-14：Suno 无官方 API（多源一致）；第三方价格 $0.014–$0.111/首；kie.ai=sunoapi.org 同一家仍在运营；ACE-Step 开源 Apache-2.0（ComfyUI 官方文档 2026-08-26）。
- 价格与可用性会变，接入前以各提供方实时页面为准。
