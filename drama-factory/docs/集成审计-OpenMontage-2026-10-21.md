# OpenMontage 集成审计（2026-10-21）

来源：calesthio/OpenMontage（AGPL-3.0，本地克隆 ~/workspace/openmontage）。原则：借功能与信息架构，按剧坊 Java/Spring 架构落地，不整仓移植 Python。

## 第一批（2026-10-19，已完成）
pipeline 模板机制 + 3 模板（cinematic/documentary-montage/clip-factory）、CostLedger 计费台账、ProviderScoringService、ShotContinuityChecker R6/R7、vocabulary.json + buildShotPrompt、157 个 skill 入官方库（后于 2026-10-20 全部恢复上游原版）。

## 本批新集成（2026-10-21）
1. **pipeline 模板 +6**：animation、avatar-spokesperson、character-animation、hybrid、localization-dub、podcast-repurpose，按剧坊 stage schema 改编自 pipeline_defs/（阶段名与 produces 逐字对齐源文件）；模板总数 7 → 13。framework-smoke 为冒烟夹具，未收。
2. **SlideshowRiskScorer**（service/SlideshowRiskScorer.java）：移植 lib/slideshow_risk.py 的六维"幻灯片风险"评分（重复度/装饰性画面/弱运镜/弱意图/文字依赖/电影感声明），公式与阈值逐项对齐；Shot 适配层以 videoPrompt 是否陈述作为"目的"判据（剧坊无独立 role 字段，已在 javadoc 注明）。端点：GET /api/projects/{pid}/episodes/{eid}/review/slideshow-risk（与 continuity 并列，只报告不拦截）。
3. **风格手册 StylePlaybook**（playbook/ 包）：styles/ 5 本手册（anime-ghibli、clean-professional、flat-motion-graphics、minimalist-diagram、premium-minimalist）原样入 resources/style-playbooks/，新增 Loader/Service/Controller（GET /api/style-playbooks、GET /api/style-playbooks/{name}）；核心字段（identity/调色板/taste_profile）类型化，其余章节以原始映射透传。
4. **媒体预设 MediaProfile**（media/ 包）：移植 lib/media_profiles.py 的 9 个平台预设（YouTube 横屏/4K/Shorts、Instagram Reels/Feed、TikTok、LinkedIn、Cinematic、Generic HD）与 ffmpeg 输出参数生成；端点 GET /api/media-profiles（可按 platform 前缀过滤）、GET /api/media-profiles/{name}。本次未改 FinalCut/VideoNormalization 的既有渲染行为，后续可按项目平台选用预设接线。

## 判定不集成（逐项理由）
- lib/variation_checker.py：核心检查（景别单一、运镜重复、连续同景别）已被 ShotContinuityChecker R7 覆盖，其余信号并入 SlideshowRisk 的 repetition 维度。
- lib/verify_scene_pacing.py：TerminalScene（HyperFrames 合成 UI）专用；成片节奏已有 CutRhythmChecker + R6 规则覆盖。
- lib/checkpoint.py（文件型检查点）：剧坊 Run/RunExecutor + JPA 状态机已有等价的阶段状态与恢复机制，文件型方案与 DB 架构冲突。
- lib/source_media_review.py：探针规范化已由 VideoNormalizationService 的 ffprobe SourceInfo + 质量门承担。
- lib/delivery_promise.py：交付承诺分类依赖 OM 的 EP 编排与提案工件模型，剧坊暂无可"锁定"承诺的工件载体；单独移植分类器会成为无消费方的死代码，待提案阶段工件化后再议。
- lib/asset_cache.py、corpus.py、clip_embedder.py：依赖向量嵌入/语义检索基础设施，剧坊无此底座，不适用。
- lib/events.py、config_model.py、env_loader.py：SSE 与 Spring 配置体系已有等价。
- lib/playbook_generator.py：从参考生成手册的 LLM 编排，剧坊已有 PromptRecipe/PromptTemplate 路线承担。
- lib/hyperframes_style_bridge.py：playbook → HyperFrames CSS 的桥接，HyperFramesVideoProvider 尚不消费 style tokens，无消费方，待接线时再做。
- tools/ 全部 Python 工具（TTS/视频/分析/增强各 provider 实现）：剧坊已有 Java provider + 描述符体系，工具注册/选择模式已在第一批借走；逐个 Python 实现与 Java 栈冲突。其中 silence_cutter、auto_reframe 等 ffmpeg 概念已由 FfmpegService/VideoNormalizationService 覆盖常用操作。
- backlot/（Python 审片看板）：剧坊已有三级审片流 + review UI，只借信息架构，不移植实现。
- remotion-composer/、ink-theater/：Node 渲染运行时；剧坊 HTML 渲染路线为 HyperFrames + painted-animation，不引入第三套。
- schemas/：JSON Schema 工件定义由 Java DTO + 校验承担。

## 附带修复
- ResourceNotFoundException 新增 withKey(String, String) 静态工厂（字符串键资源的 404），两个新 Controller 的"未找到"改走本仓 GlobalExceptionHandler 的 404 映射（原 ResponseStatusException 会被兜底处理器吞成 500）。
