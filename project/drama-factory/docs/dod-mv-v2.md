# DoD 里程碑对照报告：AI MV v2「时间轴对齐」

里程碑：drama-factory AI MV v2「时间轴对齐」，对应灵魂一页纸 docs/SOUL-mv.md 技术点 #1。
日期：2026-10-14

## 对照 PRODUCTION_CHECKLIST.md

| 检查项 | 结论 | 理由 |
| --- | --- | --- |
| 测试金字塔 | 通过 | 单元测试 15 个（MvTimelineService）+ 多批集成测试 + 端到端冒烟全链路 SUCCEEDED。 |
| 失败注入 | 未通过 | 本轮未做失败注入测试，编排器已确认为缺口。 |
| 重试降级 | 部分通过 | LLM 作词有 HTTP→CLI 回退；作曲环节无重试。 |
| DB 迁移版本化 | 通过 | Flyway V12 新增 mv_song.timeline_json（TEXT）；空库启动 12 个 migration 一次通过。 |
| 健康检查 | 通过 | actuator 沿用 v1，本轮未改动。 |
| 结构化日志 request_id | 通过 | 沿用 v1，本轮未改动。 |
| 指标告警 | 未通过 | 沿用现状，本轮未新增。 |
| 备份恢复 | 不适用 | H2 文件库，运维手册有说明。 |
| 敏感数据 | 通过 | API key 掩码存储。 |
| 配置密钥分离 | 通过 | 环境变量注入。 |
| Docker | 通过 | 沿用 v1 Dockerfile。 |
| 运维手册 | 部分通过 | 沿用 v1，本轮新增 docs 说明时间轴字段。 |
| 输入校验 | 通过 | 客户端顺序错误从 500 改为 400。 |
| 限流熔断 | 未通过 | 沿用现状，本轮未改动。 |
| CHANGELOG | 未通过 | 本轮未更新。 |
| 技术债 | 通过 | 本报告即记录，见「已知缺口与下轮」。 |

## 本轮修复的生产 bug

ByokGenerateService 的 matchImage / matchMusic / matchAvatar 返回的供应商 key 与 Spring bean 名对不上，例如返回 "dashscope-image" 而实际 bean 名为 "dashscopeimageprovider"。影响面：全部 BYOK 图片、音乐、数字人生成永远报「暂未接入」，功能整体不可用。已修正并补 11 个路由测试。另外 matchMusic 之前完全没有 ace-step 分支，一并补上。

## 已知缺口与下轮

1. mv.html 作曲按钮 POST body 为空，UI 上没有供应商选择器（v1 遗留缺口）。后端要求 providerId / modelId，否则返回 400「请选择供应商」。
2. DeepSeek CLI 回退偶发返回「?」乱码歌词（观测概率约 1/8），属模型侧输出质量问题，非本轮范围。
3. MvService @Transactional 回滚会撤销 FAILED 标记（测试注释里已记录，v1 遗留）。

覆盖率说明：AI MV v1 加了约 1200 行代码只有 13 个测试，把 JaCoCo 门禁（行 0.82 / 分支 0.70）拉红；本轮补了 63 个测试（15+4+30+12+4+6+11+1 调整），门禁已恢复：2026-10-14 末轮 verify，874 测试全绿，行覆盖 0.8233（门禁 0.82）、分支覆盖 0.7273（门禁 0.70），jacoco:check 通过。

## 视觉验收

截图位于 docs/screenshots/，5 张已亲眼看过：

- docs/screenshots/mv-v2-lyrics.png：作词步骤，真实 DeepSeek 歌词。
- docs/screenshots/mv-v2-timeline.png：时间轴展示区，逐段/逐行等宽时间码。
- docs/screenshots/mv-v2-storyboard.png：分镜步骤，逐行分镜卡。
- docs/screenshots/mv-v2-storyboard-dark.png：深色主题分镜。

结论：无 JS 报错。截图过程中发现并修了 2 个截图环境问题：setContent 下相对 URL 不解析；Playwright route 注册逆序。

冒烟结论：作词→作曲（stub 返回 8 秒 mp3）→分镜→渲染全链路 SUCCEEDED；final.mp4 时长 8.0s == 音频时长；subs.srt 26 条逐行字幕，时间戳与 timeline 一致。