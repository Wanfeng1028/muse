# 覆盖率目标与门禁（drama-factory）

## ① 目标

- **当前门禁：行覆盖（LINE）≥ 51%**，由 JaCoCo `check` 在 `verify` 阶段强制执行，未达标即构建失败。棘轮值按实测锁定（v2.6 实测 51.3%，基线 49.6%），只升不降。
- **下一里程碑：v2.7 提升至 55%**，届时同步收紧 JaCoCo `minimum` 至 `0.55`。

## ② 口径

- 命令：`mvn -o test`（离线执行单测），随后由 `jacoco-maven-plugin` 生成报告并做门禁校验。
- 报告产物：`drama-factory/target/site/jacoco/index.html`（行/分支/方法维度）。
- 已知稀释项：`dto`、`model`、`config` 等样板代码（纯 setter/getter、注解配置类）会被计入分母，天然拉低整体百分比。这是既定口径，不通过排除规则规避，避免掩盖真实缺口。

## ③ 基线表

| 指标 | 基线值 | 说明 |
| --- | --- | --- |
| 行覆盖（LINE） | 51.3%（v2.6 实测；v2.5 基线 49.6%） | 全量 4600+ 行 |
| 分支覆盖（BRANCH） | 31.0%（v2.6 实测；v2.5 基线 29.1%） | 全量 |
| 门禁阈值 | 0.51 | JaCoCo check，`verify` 阶段 |

## ④ 缺口表

| 类 | 当前覆盖 | 缺口原因 | 排期 |
| --- | --- | --- | --- |
| `LlmTransport` | 低 | 真实 HTTP 调用，单测需 mock 网络层成本高 | 集成测试（Testcontainers / WireMock） |
| `RunExecutor` | 低 | 372 行编排逻辑，依赖 Spring 上下文与多服务协作 | Spring 集成测试 |
| video providers | 低 | 依赖外部视频生成 API，响应不可控 | 契约测试（contract test） |

## ⑤ 本轮新增测试清单

- `ScriptSplitterServiceTest`（`com.dramafactory.service`）
  - 正常 2 镜全字段解析
  - 带 ``` 围栏输入解析
  - 空数组抛 `大模型未拆出任何分镜`
  - 根非数组抛 `大模型返回的不是 JSON 数组`
  - 非法 JSON 抛 `解析大模型返回内容失败: …`
  - 第 2 镜 `shotSize` 非法抛异常且 message 含“第 2 个分镜”
  - 非法 `cameraMove` → `getCameraMove() == null`（不抛异常）
  - 缺 `shotNo` → 用数组序号（从 1 起）
  - 缺 `durationSeconds` → 默认 5
  - `text(node, field)` 字段缺失 / 为 null → 返回 null
  - `stripCodeFence`：无围栏 / 仅前围栏 / 前后围栏
- `EpisodeStatusFlowServiceTest`（`com.dramafactory.service`）
  - 无分镜不推进且不 save
  - 有未 DONE 任务不推进且不 save
  - 全 DONE + DRAFT → GENERATED
  - 全 DONE + SCRIPTED → GENERATED
  - 已是 GENERATED 不 save
  - `markQcApproved` → REVIEWED
  - `markQcRejected` → SCRIPTED
