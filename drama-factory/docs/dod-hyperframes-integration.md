# Drama-Factory 发版前 Definition of Done 对照报告

## 标题

**HyperFrames 渲染集成（commit `468ad37`）生产级 Definition of Done 对照报告**

## 背景

本次集成将 HyperFrames 渲染引擎接入 drama-factory 的 HTML 降级路线：

- 新增 `HyperFramesVideoProvider`：通过 `hyperframes` CLI 将 `composition.html` 逐帧渲染为 MP4，CLI 不可用时（`--version` 探活失败）抛出清晰错误。
- 与既有 `painted-animation` provider 并存，由 `VideoProviderRouter` 选择；`DEFAULT_ORDER` 在 `doubao` 之后插入 `hyperframes`。
- 引入 11 个场景模板（`hyperframes-blocks`）与 21 个 HyperFrames skills（`skills-bundled`，来源 heygen-com/hyperframes，Apache-2.0）。
- 超时/资源上限经 `CommandRunner` 可注入 fake，单测不启动真实进程。

按 muse 仓库统一 `PRODUCTION_CHECKLIST.md`（2026-10-13 Grok 建议，用户亲定"不裁剪，全量按大厂标准执行"），本次发版前需逐条对照。本报告仅依据 commit `468ad37` 的变更事实判定；无证据的条目一律标注"未验证"，不虚构测试数据。

## 变更清单

**Java 代码（2 个文件）**
- `drama-factory/src/main/java/com/dramafactory/service/video/HyperFramesVideoProvider.java`（新增）
- `drama-factory/src/main/java/com/dramafactory/service/video/VideoProviderRouter.java`（修改：DEFAULT_ORDER 在 doubao 后加 hyperframes）

**场景模板资源（11 个场景，共 24 个文件）**
- `hyperframes-blocks/_index.json`
- canopy-part-title（SKILL.md / .html / registry-item.json）
- hw-title（demo.html / hw-title.html / registry-item.json）
- hw-write-title（.html / registry-item.json）
- lower-third-bild（.html / registry-item.json）
- lt-clean-bar（.html / registry-item.json）
- lt-dark-card（.html / registry-item.json）
- lt-mask-reveal（.html / registry-item.json）
- lt-soft-pill（.html / registry-item.json）
- transitions-dissolve（.html / registry-item.json）
- whip-pan（.html / registry-item.json）
- yt-lower-third（.html / registry-item.json）

**Skills 资源（21 个 HyperFrames skills，共 40+ 文件）**
- `skills-bundled/_index.json`
- `hyperframes-animation/SKILL.md`
- `adapters/`：animate-text、animejs、css-animations、gsap、gsap-easing-and-stagger、gsap-timeline-and-labels、gsap-transforms-and-perf、html-in-canvas-patterns、lottie、three、typegpu、waapi（12 个）
- `blueprints-index.md`
- `blueprints/`：agent-progress-theater、camera-journey、comparison-split、constellation-hub、cta-morph-press、cursor-ui-demo、dataviz-countup、device-surface-showcase、fixed-anchor-cycle、grid-card-assemble、kinetic-type-beats、logo-assemble-lockup、overwhelm-surround、panel-edit-live-sync、prompt-type-submit-generate、spatial-pan-stations、ticker-takeover、titlecard-reveal（18 个）

**未包含在本次 commit 的产物**：无新增测试文件、无 CHANGELOG 条目、无运维/迁移/配置文档、无 CI/Compose/告警配置、无备份恢复脚本。这些缺失直接影响下方多个条目的判定。

---

## 逐条对照（8 节）

### 1. 可靠性

**1.1 测试金字塔（单元 + 集成 + 端到端全量，关键路径有失败注入测试）**
- 判定：**未通过**
- 依据：commit message 声明"单测零真实进程"、`CommandRunner` 可注入 fake，说明单元层面有测试意图；但本次 commit **未包含任何测试文件**（`git show --name-only` 无 `src/test/` 路径）。集成测试、端到端测试、失败注入测试均无证据。
- 备注：单测可能位于其他 commit，但本次发版前无任何测试文件随变更合入，视为本次 DoD 未达成。
- 排期建议：下一迭代 P0，补齐 `HyperFramesVideoProviderTest`（CLI 探活失败、超时、非零退出、正常渲染路径）、`VideoProviderRouter` 顺序选择测试、至少一条基于 `CommandRunner` fake 的集成路径。

**1.2 错误处理策略明确（重试带退避、降级、幂等，写进文档）**
- 判定：**未通过**
- 依据：`HyperFramesVideoProvider` 描述中"CLI 不可用抛清晰错误（--version 探活）"属错误检测，不是完整错误处理策略。无重试/退避、无降级到 painted-animation 的显式说明、无幂等语义、无相关文档。
- 排期建议：P1，明确 provider 失败后的 Router 降级链（hyperframes → painted-animation）并写入文档；重试策略按 CLI 语义评估后决定是否实现。

**1.3 数据库迁移版本化（即使 SQLite，支持升级路径说明）**
- 判定：**不适用**
- 理由：本次变更不涉及持久化 schema（provider、router、静态 HTML/skill 资源），无 DB 迁移。

**1.4 健康检查端点 + 就绪探针 + 优雅关闭**
- 判定：**未通过**
- 依据：本次 commit 无 health endpoint、probe、shutdown hook 相关变更；仓库层面是否存在未在本次变更中体现，**未验证**。
- 排期建议：若仓库已有统一健康检查，需在发版文档中登记 HyperFrames CLI 依赖作为就绪条件；若无，P1 补齐。

### 2. 可观测性

**2.1 结构化日志，全链路带 request_id**
- 判定：**未通过（本次变更范围内未验证）**
- 依据：commit message 未提及日志埋点或 request_id 关联；变更文件清单无日志相关类。HyperFrames CLI 调用属于长耗时外部进程，尤其需要关联 ID，但本次无证据。
- 排期建议：P1，在 `HyperFramesVideoProvider` 调用 CLI 前后补结构化日志（含 request_id、composition 路径、超时配置、退出码）。

**2.2 关键指标暴露（请求量、延迟、错误率、队列积压）**
- 判定：**未通过**
- 依据：无 metrics 相关代码或配置变更。渲染时长、CLI 失败率、逐帧进度为本次集成最需要暴露的指标，未实现。
- 排期建议：P1，至少暴露渲染请求量、耗时分布、失败率。

**2.3 报错能快速定位到具体请求和代码位置**
- 判定：**未通过（依赖 2.1）**
- 依据：有"清晰错误"的意图，但无 request_id / 上下文日志支撑，无法从错误快速回溯具体请求与代码位置。

**2.4 基础告警规则**
- 判定：**未通过**
- 依据：本次 commit 无告警配置。日志告警亦可接受，但需"写清楚"，未提供。
- 排期建议：P2，配合 2.2 指标落地。

### 3. 数据与状态

**3.1 自动备份 + 一键恢复流程（写进运维手册，实测过）**
- 判定：**不适用**
- 理由：本次变更不引入新的持久化状态；HTML/skill 资源为只读随包资源，无需备份。运维手册是否覆盖既有状态属于仓库层面，**未验证**。

**3.2 敏感数据处理策略明确**
- 判定：**不适用**
- 理由：本次变更为渲染引擎与静态资源，未引入用户敏感数据字段。

**3.3 配置与密钥完全分离，环境变量化，启动时校验必填项**
- 判定：**未通过**
- 依据：`HyperFramesVideoProvider` 涉及 CLI 路径、超时、资源上限等配置项，但 commit 未体现环境变量化与启动校验。这些是可配置的外部依赖，应环境变量化并在启动时校验（如 CLI 路径可执行、超时为正数）。
- 排期建议：P1，新增配置项走环境变量，启动时校验。

**3.4 单用户项目也按多用户、长期运行设计（tenant/user 概念落地）**
- 判定：**不适用**
- 理由：渲染 provider 属无状态转换层，不涉及 tenant/user 数据边界。若 Router 选择需按用户区分，属未来需求，本次未触及。

### 4. 部署与运维

**4.1 Docker Compose（或等价物）一键部署，带完整示例配置**
- 判定：**未通过**
- 依据：本次 commit 无 Compose/镜像/示例配置变更。HyperFrames CLI 是新增外部依赖（含 Node/浏览器渲染栈等潜在依赖），部署镜像是否已包含 CLI 未验证。
- 排期建议：P0，明确部署镜像是否内置 hyperframes CLI；若不内置，需在 Compose 中显式声明依赖与版本。

**4.2 滚动更新 / 零停机：支持则写明，不支持则明确说明限制**
- 判定：**未通过**
- 依据：无相关说明。长耗时渲染任务与滚动更新的兼容性（进行中任务的迁移/中断策略）需明确声明。
- 排期建议：P2，在运维文档中声明"不支持零停机"或给出任务排空策略。

**4.3 资源限制、日志轮转、数据卷管理写清楚**
- 判定：**未通过**
- 依据：commit message 提及"超时/资源上限经 CommandRunner 可注入"，说明 provider 层已考虑资源上限，但**部署层**的资源限制（容器 CPU/内存）、日志轮转、渲染产物数据卷管理均无证据。
- 排期建议：P1，容器资源限制与产物卷管理写入运维文档与 Compose。

**4.4 《运维手册》：备份、恢复、升级、常见故障排查**
- 判定：**未通过**
- 依据：本次 commit 未包含或更新运维手册。新增外部依赖 CLI 的故障排查（CLI 缺失、版本不匹配、渲染卡死）无文档。
- 排期建议：P0，发版前补充运维手册章节。

### 5. 安全与健壮性

**5.1 输入校验全面、防注入、基础鉴权**
- 判定：**未通过（部分未验证）**
- 依据：`HyperFramesVideoProvider` 将 `composition.html` 交给 CLI 渲染。若 `composition.html` 来自用户/模板拼接，存在路径注入、命令参数注入、HTML/JS 内容注入风险。本次 commit 无输入校验相关变更。鉴权属仓库层面，**未验证**。
- 排期建议：P0，明确 composition 输入来源与净化策略；CLI 调用参数使用数组形式而非 shell 拼接，避免命令注入。

**5.2 依赖更新机制（Dependabot 或等价说明 + 定期检查）**
- 判定：**未通过**
- 依据：本次引入外部 CLI 依赖（hyperframes）与大量第三方资源（heygen-com/hyperframes，Apache-2.0）。无版本固定说明、无更新机制、无许可证合规记录。
- 排期建议：P1，固定 CLI 版本并在文档中登记；登记 Apache-2.0 归属与 NOTICE；接入依赖更新检查。

**5.3 限流、超时、熔断等必要保护**
- 判定：**部分通过 → 整体判为未通过**
- 依据：commit message 明确"超时/资源上限经 CommandRunner 可注入"，超时与资源上限**已实现**；但限流与熔断无证据。按清单要求（"限流、超时、熔断等必要保护"）整体未满足。
- 排期建议：P1，渲染为高成本操作，需在 Router 或 provider 层加并发限流，防止批量请求压垮宿主。

### 6. 可维护性

**6.1 模块边界清晰，API 契约明确**
- 判定：**通过**
- 依据：Provider 接口（`VideoProvider`）+ Router 选择模式，新增 provider 与既有 painted-animation 并存，边界清晰；`CommandRunner` 可注入是明确的可测试契约。`registry-item.json` 为模板资源提供了结构化元数据契约。
- 备注：契约的**文档化**程度未验证，但代码结构层面满足。

**6.2 CHANGELOG + 升级指南随版本更新**
- 判定：**未通过**
- 依据：本次 commit 未包含 CHANGELOG 或升级指南更新。新增外部依赖 CLI 属破坏性/环境敏感变更，升级指南必要。
- 排期建议：P0，发版前补 CHANGELOG 条目与升级指南（含 CLI 安装要求）。

**6.3 技术债有记录（位置/影响/偿还计划）**
- 判定：**未通过**
- 依据：本报告列出的多项未通过条目即技术债，但 commit 本身未记录技术债条目。
- 排期建议：P1，将本报告未通过项录入技术债台账。

**6.4 代码与文档同步（行为变更必须同步更新文档）**
- 判定：**未通过**
- 依据：Router 的 `DEFAULT_ORDER` 行为发生变更（在 doubao 后插入 hyperframes），属行为变更，需同步文档；本次 commit 无文档更新。
- 排期建议：P0，更新 provider 选择顺序文档。

### 7. 发版前对照报告（强制）

- 判定：**通过（本报告即为履行）**
- 依据：本报告即为按此条要求产出的对照报告，将存于 `drama-factory/docs/` 并记入 `PROJECTS.md`（见结论）。

### 8. 周期机制

**8.1 技术债清理轮**
- 判定：**不适用（机制层面，非本次集成判定项）**
- 理由：属周期性流程要求，本次不评估单次集成。本报告未通过项已进入排期，可供后续清理轮使用。

**8.2 真实负载验证（接近真实数据量/并发，不只 demo 数据）**
- 判定：**未通过**
- 依据：commit message 明确"单测零真实进程"，即**测试不启动真实 hyperframes CLI**，也未描述真实负载验证。渲染性能与稳定性在真实数据量/并发下**未验证**。
- 排期建议：P0，发版前用真实 composition + 真实 CLI 跑通至少一条端到端渲染；记录耗时与资源占用。

**8.3 故障演练抽查（杀进程、断网、磁盘满）**
- 判定：**未通过**
- 依据：无故障演练记录。渲染进程被杀、CLI 中途断网、渲染产物磁盘写满等场景未验证恢复能力。
- 排期建议：P1，针对渲染 provider 做一次故障演练抽查。

---

## 未通过项排期

**P0（发版前必须完成，否则不得发版）**
1. 部署与运维 4.1：明确 hyperframes CLI 在部署镜像/Compose 中的依赖与版本。
2. 部署与运维 4.4：补《运维手册》HyperFrames 章节（安装、故障排查）。
3. 安全 5.1：明确 composition 输入净化策略；CLI 参数以数组形式传递防注入。
4. 可维护性 6.2：补 CHANGELOG 与升级指南。
5. 可维护性 6.4：更新 Router `DEFAULT_ORDER` 文档。
6. 周期机制 8.2：真实 CLI 端到端渲染跑通至少一次并记录。

**P1（下一迭代内完成）**
7. 可靠性 1.1：补齐单元/集成测试（含失败注入）。
8. 可靠性 1.2：明确失败降级与重试策略并文档化。
9. 可靠性 1.4：健康检查/就绪条件登记。
10. 可观测性 2.1–2.3：结构化日志 + request_id + 关键指标。
11. 数据与状态 3.3：配置环境变量化 + 启动校验。
12. 部署与运维 4.3：容器资源限制与产物卷管理。
13. 安全 5.2：CLI 版本固定、许可证登记、依赖更新机制。
14. 安全 5.3：渲染并发限流。
15. 可维护性 6.3：技术债台账登记。
16. 周期机制 8.3：故障演练抽查。

**P2（后续迭代）**
17. 可观测性 2.4：告警规则。
18. 部署与运维 4.2：零停机限制声明或排空策略。

**已知限制（明确声明，不排期但需登记）**
- 单测刻意不启动真实 hyperframes CLI（设计取舍，换取测试速度与稳定性）；真实进程行为仅由 P0 项 6 的端到端验证覆盖，测试金字塔在 CLI 层面存在覆盖缺口。
- 本次引入的 21 skills / 11 模板均为上游 Apache-2.0 资源，未做本地行为验证。

---

## 结论

**判定：不满足生产级 Definition of Done，不建议按当前 commit 直接发版。**

本次集成在**代码结构与契约**层面表现良好（6.1 通过），provider/router 边界清晰、`CommandRunner` 可注入设计利于测试与演进。但按仓库统一标准"不裁剪、全量执行"的口径，**8 节中仅第 7 节（本报告）通过，1.3 / 3.1 / 3.2 / 3.4 / 8.1 因不适用而豁免，其余条目均未通过或未验证**。核心缺口集中在：

1. **无任何测试文件随本次变更合入**（1.1、8.2）——与"单测零真实进程"的意图形成对照，说明测试可能未随集成提交。
2. **新增外部 CLI 依赖的部署、配置、安全、运维全链路空白**（4.1、4.4、5.1、5.2、3.3）。
3. **行为变更未同步文档**（6.2、6.4）。
4. **可观测性完全缺失**（第 2 节）。

**发版建议**：先完成 P0 六项（预计可在本迭代内闭合），再重新执行本对照报告；P1 项可随下一迭代偿还，但需在技术债台账中显式登记。本报告应存入 `drama-factory/docs/`，并在 `PROJECTS.md` 中记入"HyperFrames 集成 DoD 对照报告（未通过，P0 待闭）"。

**诚实声明**：本报告所有判定仅基于 commit `468ad37` 的 `--name-only` 清单与 commit message 描述。仓库层面既有的测试框架、CI、Compose、健康检查等若存在于本次 commit 之外，本报告未做核验，相关条目以"未验证"标注，未据此判定为通过。