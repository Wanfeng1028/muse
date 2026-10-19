# HtmlRender 双引擎发版前 DoD 对照报告（2026-10-20）

## 1. 变更清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| HtmlRenderVideoProvider.java | 重写 | 新增 engine 配置与 hyperframes 分支、测试缝、降级逻辑 |
| HtmlRenderEngineSelectionTest.java | 新增 | 7 例纯 JUnit 引擎选择测试 |
| docs/DEGRADATION.md | 修改（只增） | 新增"htmlrender 双引擎"小节 |
| application.yml | 修改（只增） | 新增 drama.video.htmlrender.* 与 drama.video.hyperframes.cli |
| .env.example | 修改（只增） | 新增说明 |
| scripts/hyperframes_probe.sh | 新增 | 引擎探活脚本 |

未变更：VideoProviderRouter 链位置、独立 HyperFramesVideoProvider、无 DB 迁移。

---

## 2. 六节逐条对照

### 2.1 可靠性

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| 主链路失败可降级 | 通过 | hyperframes 渲染失败时 warn 并降级走原 chromium 管道（事实 3）。 |
| 降级路径本身可用 | 通过 | chromium 分支保持原截图+ffmpeg 管道不变，且实测 scripts/hyperframes_probe.sh CLI 缺失时输出 engine=chromium（事实 5）。 |
| 非法配置回退安全 | 通过 | 非法值 -> warn + CHROMIUM（事实 2）；大小写不敏感与非法值回退均有测试覆盖（事实 4）。 |
| 探活超时可控 | 通过 | `hyperframes --version` 探活 15 秒（事实 2）。 |
| 双路全失败可观测 | 通过 | 两路都失败才写 FAILED 标记（事实 3）。 |
| 真实渲染端到端验证 | 通过 | 2 秒 1080p composition 渲染出 out/video.mp4（16.2KB），ffprobe 确认时长 2.000000 秒（事实 5）。 |
| 引擎选择无副作用（默认路径零探活） | 通过 | chromium/空 -> CHROMIUM 零探活（事实 2），测试验证默认零探活（事实 4）。 |
| 并发/资源回收/重试策略 | 未验证 | 变更事实未涉及并发、资源回收或重试语义，无法从事实推断。 |
| poll()/TASK_PREFIX 语义保持 | 通过 | 事实 3 明确 poll()/TASK_PREFIX 语义不变。 |

### 2.2 可观测性

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| 降级有日志 | 通过 | 探活非零/异常与非法值均 warn（事实 2）；渲染失败 warn（事实 3）。 |
| 探活脚本可输出引擎态 | 通过 | scripts/hyperframes_probe.sh 实测输出 engine=chromium / engine=hyperframes（事实 5）。 |
| 指标/追踪（metrics/trace）埋点 | 未验证 | 变更事实未提及任何指标或 trace 埋点。 |
| 失败原因可区分（探活失败 vs 渲染失败） | 未验证 | 事实仅说明均有 warn，未说明日志可区分两类失败。 |
| 结构化日志/字段 | 未验证 | 事实未涉及日志结构。 |

### 2.3 数据

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| DB 迁移 | 不适用 | 事实 7 明确无 DB 迁移。 |
| 配置项新增（application.yml） | 通过 | 新增 drama.video.htmlrender.* 与 drama.video.hyperframes.cli，只增不改（事实 6）。 |
| 配置默认值兼容 | 通过 | engine 默认 chromium、cli 默认 hyperframes，与既有独立 HyperFramesVideoProvider 同 key（事实 1）。 |
| 数据持久化/产物一致性 | 未验证 | 事实仅给出单次渲染产物（out/video.mp4），未涉及跨路径产物一致性校验。 |
| 输出产物规格一致性（resolution/fps） | 通过 | 命令含 --resolution 1080p 与 --fps，实测 1080p/24 渲染 2.000000 秒产物（事实 5）。 |

### 2.4 部署运维

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| 配置文档化 | 通过 | docs/DEGRADATION.md 新增小节、application.yml 与 .env.example 只增（事实 6）。 |
| 依赖版本可核验 | 通过 | npm 装 hyperframes@0.8.176，`--version` 返回 0.8.176（事实 5）。 |
| CLI 参数拼装合法 | 通过 | `render --help` 核验 --resolution/--no-browser-gpu/-c/-o/--fps 全部真实存在（事实 5）。 |
| 灰度/回滚开关 | 通过 | engine 配置默认 chromium，可切回；探活失败自动降级（事实 1、2）。 |
| 生产环境联调 | 未验证 | 联调为本机实测（事实 5），非生产/预发环境。 |
| 部署脚本/镜像依赖（hyperframes 安装） | 未验证 | 事实未说明生产镜像或部署脚本是否包含 hyperframes 安装。 |
| 容量/性能基线 | 未验证 | 事实未提供吞吐、延迟或资源占用基线。 |

### 2.5 安全

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| 无敏感信息泄露 | 通过 | 变更文件为代码/配置/文档/脚本，事实未涉及密钥；配置项为 engine 与 cli 路径。 |
| 外部命令注入防护 | 未验证 | 事实未说明 cli 路径与参数的注入校验（cli 来自配置）。 |
| CLI 来源可信性/供应链 | 未验证 | 仅说明 npm 装 hyperframes@0.8.176，未涉及签名/来源校验或依赖审计。 |
| 沙箱/权限（--no-browser-gpu 影响） | 未验证 | 事实未涉及运行沙箱或权限收敛。 |

### 2.6 可维护性

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| 测试覆盖引擎选择 | 通过 | HtmlRenderEngineSelectionTest 7 例全绿，~1.2 秒（事实 4）。 |
| 测试独立于 Spring 上下文 | 通过 | 纯 JUnit，无 Spring 上下文（事实 4）。 |
| 可测试性设计（测试缝） | 通过 | RenderEngine 枚举、CommandRunner 接口、resolveEngine()、setEngineConfig/setHyperframesCli/setWorkDirBase（事实 1）。 |
| 关键路径有断言 | 通过 | submit 发出 render 命令且 composition.html 含镜头描述（事实 4）。 |
| 测试自身缺陷已修 | 通过 | 发现并修复 2 处测试 bug（FakeRunner latch 与搜索循环命令索引不一致）（事实 4）。 |
| 定向测试范围说明 | 通过 | 本轮只跑定向测试类（报告说明节）。 |
| 全量门禁 | 未通过 | JaCoCo 全量门禁现状：他人在途代码变红，本轮只跑定向测试类，全量门禁未通过（见第 4 节）。 |
| 文档同步 | 通过 | docs/DEGRADATION.md 新增小节（事实 6）。 |
| 与既有 Provider 的兼容 | 通过 | 独立 HyperFramesVideoProvider 不动、Router 链位置不变、同 key 复用（事实 1、7）。 |
| 代码规范/静态检查 | 未验证 | 事实未涉及 lint/静态检查结果。 |

---

## 3. 未通过项

| 条目 | 判定 | 说明 |
| --- | --- | --- |
| JaCoCo 全量门禁 | 未通过 | 他人在途代码导致全量变红，本轮仅跑定向测试类。 |

---

## 4. JaCoCo 全量门禁现状

- 本轮**未**执行全量门禁；仅执行定向测试类 HtmlRenderEngineSelectionTest（7 例全绿，~1.2 秒，纯 JUnit，无 Spring 上下文）。
- 全量门禁当前为**红**，原因为**他人在途代码变更**，与本批次改动无因果确认关系（事实未提供归属结论）。
- 结论：全量门禁判定为**未通过**，本批次不以其作为放行依据；放行依据为定向测试与真实联调结果。

---

## 5. 未通过项排期

| 项 | 判定 | 排期 |
| --- | --- | --- |
| JaCoCo 全量门禁转绿 | 未通过 | 待他人在途代码合并/修复后，由发版负责人重跑全量门禁并回填结论。 |
| 生产/预发环境联调 | 未验证 | 待部署镜像包含 hyperframes 依赖后，在预发执行一次 1080p 端到端渲染与降级演练。 |
| 外部命令注入与 CLI 来源校验 | 未验证 | 下一批次补充 cli 路径白名单/来源校验与安全评审。 |
| 指标与 trace 埋点 | 未验证 | 下一批次补充探活/降级/双路失败的指标与 trace。 |
| 并发与资源回收验证 | 未验证 | 下一批次补充并发提交与资源回收测试。 |
| 性能基线 | 未验证 | 待预发环境建立渲染延迟与资源占用基线。 |
| 静态检查/lint | 未验证 | 待纳入本轮或下轮 CI 记录。 |

---

## 6. 结论

- 本批次核心功能（双引擎接入、探活、降级、配置、文档）在**定向测试**与**本机真实联调**范围内**通过**。
- **未通过**项：JaCoCo 全量门禁（他人在途代码变红）。
- **未验证**项：生产/预发联调、并发与资源回收、指标/trace、注入与供应链安全、性能基线、静态检查。
- 上述未通过/未验证项不得视为通过，需按第 5 节排期闭环后再评估发版。
