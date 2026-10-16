# 幕间 Interlude — 生产级对照报告（v1.4，2026-10-16）

> 对照标准：`~/workspace/muse-build/PRODUCTION_CHECKLIST.md`（用户亲定：不裁剪、全量大厂标准）。
> 每条结论：通过 / 未通过 / 不适用+理由。未通过项给出排期或明确声明为已知限制。
> 结论口径：凡本轮实测覆盖到的项，以本轮证据为准；v1 已通过且本轮未变动的项，标注"v1 结论延续"。

## v1.4 新增验证通过的事实

- 测试：104 total / 101 通过 / 0 失败 / 3 中止。3 个中止是 FaultInjectionTest 里 assumeTrue/assumeFalse 的 OS 相关假设，本沙箱不满足其中止，非失败。新增 47 例：SessionLogTest 16、ReplayAnalyzerTest 16、ReplayMarkdownTest 9、ReplayCliTest 6。
- CLI 真实冒烟：`replay sample-session.json --script sample.interlude --out` 退出码 0；报告含 10 个时间线事件、3 个抉择点（prologue 第 4 行 / hall 第 9 行 / stranger 第 20 行，行号已与剧本原文逐行核对一致，场景原文引用正确）；无投票对局下"投票与出局/MVP 评选"章节诚实降级为"本局无投票记录"；不带 --script 时退出码 0 且无富化；日志文件不存在/JSON 非法时退出码 2。
- 新增文件：4 个主文件（SessionEvent.kt、SessionLog.kt、ReplayReport.kt、ReplayMarkdown.kt）+ 4 个测试文件（SessionLogTest、ReplayAnalyzerTest、ReplayMarkdownTest、ReplayCliTest）+ 1 个示例对局日志（src/main/resources/replays/sample-session.json）+ LintCli 改动（新增 `replay` 子命令）。
- 本轮修 1 个真 bug：ReplayAnalyzer 的 warnings 原先按"类型"分两轮产生（抉择点警告先于 SceneEnter 警告），与测试期望的时间线顺序不符；已改为单遍按事件顺序产生，测试全绿。

## 1. 可靠性

- 测试金字塔：通过。单元测试 + 集成测试本轮跑通；端到端以 CLI 真实冒烟覆盖（退出码 0，报告全文经编排者亲眼看过）。
- 失败注入测试：v1.3 已有结论延续。
- 错误处理：通过。JSON 解析错误定位到 events[i]；CLI 退出码 0/2 实测通过。
- DB 迁移：不适用。本项目无数据库。
- 健康检查：不适用。CLI 工具无长期运行进程。

## 2. 可观测性

- 结构化日志：延续。replay 子命令记 Log.info，含 session/events。
- 关键指标：事件数 / 抉择点数，报告头实测有值。
- 报错定位：通过。warnings 含事件序号 + 场景名。

## 3. 数据与状态

- 备份：延续 v1.3 的 .bak 备份/恢复结论。
- 敏感数据：通过。对局日志只含玩家自愿记录的事件，无额外采集。
- 配置密钥分离：通过。零配置、无密钥。
- 多用户：不适用。本地 CLI 工具，无多租户。

## 4. 部署与运维

- 一键部署：未通过 — 环境限制。Gradle daemon 本沙箱不可用，沿用 kotlinc 直编验证。
- 运维手册：OPS.md 本轮未更新，但 replay 用法已进 README。
- 桌面 UI 截图验收：未通过 — 已知限制。复盘模式无 Web UI，是 CLI + Markdown，无截图债。

## 5. 安全与健壮性

- 输入校验：通过。手写 JSON 解析器对非法 type / 缺字段 / 类型错误 / 语法错误全部抛定位异常，16 例测试覆盖。
- 依赖更新：延续。零新增依赖。
- 限流：不适用。本地 CLI 工具。

## 6. 可维护性

- 模块边界：通过。新增 replay 包只依赖 dsl 包的 Story/Scene/Text，无环。
- CHANGELOG：通过。
- 技术债：手写 JSON 解析器未来若格式扩展考虑换成熟库（记为技术债）。
- 文档代码同步：通过。README 示例命令已实测可跑。

## 7. 发版前对照报告

通过（本报告）。
