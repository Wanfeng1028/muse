# AI MV 模式 · 作曲渠道调研结论（2026-10-14 晚）

背景：用户 2026-10-14 19:13 批准 AI MV 模式（对标抖音"南瓜造梦局"），作曲是管线关键腿。
调研人：小白（主 agent），搜索走 browser.search（Keenable 本轮被环境 egress 拒绝，403）。

## 结论（一句话）

**Suno 没有官方自助 API（2026 年中仍无），第三方包装可用但属灰色地带；
MiniMax 付费音乐 API 已于 2026-08-20 停止接受新用户；
当前唯一"官方、有文档、带声乐"的作曲 API 是 ElevenLabs Music（$0.15/生成分钟）。**

## 分项核验

### 1. MiniMax Music —— 助理此前说法属实 ✅
- 付费 Music Generation / Lyrics Generation API **2026-08-20 起不再接受新用户**（platform.minimax.io 公告）。
- 已付费老用户不受影响，endpoint 仍可用 → BYOK 里保留"老用户自带 key"通道。
- 替代路线：MiniMax-Music3 开源权重可自部署（需 CUDA GPU），对 BYOK SaaS 用户不现实。

### 2. Suno —— 无官方 API ❌（官方自助）
- 截至 2026 年 7 月：无自助官方 API、无官方 key 流程、无公开 API 定价（多家独立指南一致结论）。
- Suno CPO Jack Brody 2026-07-01 在 LinkedIn 宣布"正在探索开发者 API，先做小范围合作伙伴"，官网有意向登记表；**无上线日期、无定价、无限流条款**。背景：环球/索尼版权诉讼仍在进行（61,000+ 录音追加索赔），华纳 2025-11 已和解授权。
- 第三方包装（非官方）：CometAPI、APIMODELS（`suno-v5`，$0.26/首·含 2 个版本）、TTAPI（约 $0.06/任务）。均属 Suno 条款灰色地带，可能随时被掐 —— **只能做实验渠道，不能当默认**。
- 建议：去 suno.com 意向表登记（免费），作为长期赌注。

### 3. ElevenLabs Music —— 唯一干净的官方带声乐渠道 ✅
- 官方定价页：Music API **$0.15 / 生成分钟**，有 SDK/文档/API 参考。
- 支持声乐（vocal songs），免费档 10,000 credits 可测（非商用、需署名）。
- 代价：高频试错时成本偏高（有用户报告一首歌烧掉 7000+ credits）→ 做"先试听低成本小样、确认再出完整版"的两段式调用。

### 4. 其他（备选，不建议默认）
- Stable Audio：官方 API 真实存在，但偏器乐。
- Google Lyria RealTime：官方，但文档明确器乐向 + 输出带水印，不适合 MV。

## 给 AI MV 模式的 BYOK 建议

1. **默认渠道：ElevenLabs Music**（官方、合规、带声乐、定价透明）→ 写进设置中心"作曲"默认项。
2. **实验渠道：Suno 第三方包装**（CometAPI/APIMODELS/TTAPI 任选其一）→ UI 上标注"非官方，随时可能失效"，满足用户对"南瓜造梦局那味"的质量诉求。
3. **兼容渠道：MiniMax music-3.0** → 仅已有付费 key 的老用户可见。
4. **长期**：登记 Suno 官方合作伙伴意向，API 开放后第一时间切回官方。

成本锚点（供 Run 成本统计用）：ElevenLabs $0.15/分钟；Suno 包装约 $0.06–0.26/首；MiniMax 老用户按原价目。

## 来源
- Suno API 现状：https://gptproto.com/blog/suno-api（2026-07 更新）、https://josephbenois.medium.com/suno-ai-api-guide-2026-generate-music-programmatically-3a381aa58fa0、https://sunnoai.com/music-generation-api/
- Suno 第三方价格：https://apimodels.app/models/suno-v5（2026-10-01 更新）、https://www.toolify.ai/tool/suno-api
- MiniMax 8-20 关闭：https://github.com/spora-ai/spora-plugin-minimax/blob/HEAD/skills/minimax-music-legacy/SKILL.md、https://github.com/calamitousfelicitousness/ai-prompting-guides/blob/HEAD/docs/minimax-music.md、https://github.com/dkackman/diffusers-workflow/blob/HEAD/docs/proposals/audits/2026-09-08-minimax-music3-audit.md
- ElevenLabs 定价：https://aireiter.com/blog/music-generation-api-comparison（2026-09-26 更新）
