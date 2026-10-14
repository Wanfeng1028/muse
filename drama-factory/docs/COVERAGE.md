# 覆盖率目标与门禁（drama-factory）

## ① 目标

- **当前门禁：行覆盖（LINE）≥ 55%**，由 JaCoCo `check` 在 `verify` 阶段强制执行，未达标即构建失败。棘轮值按实测锁定（v2.7 实测 58.5%，v2.6 基线 51.3%），只升不降。
- **下一里程碑：v2.8 分支覆盖冲 45%**。

## ② 口径

- 命令：`mvn -o test`（离线执行单测），随后由 `jacoco-maven-plugin` 生成报告并做门禁校验。
- 报告产物：`drama-factory/target/site/jacoco/index.html`（行/分支/方法维度）。
- 已知稀释项：`dto`、`model`、`config` 等样板代码（纯 setter/getter、注解配置类）会被计入分母，天然拉低整体百分比。这是既定口径，不通过排除规则规避，避免掩盖真实缺口。

## ③ 基线表

| 指标 | 基线值 | 说明 |
| --- | --- | --- |
| 行覆盖（LINE） | 58.5%（v2.7 实测；v2.6 基线 51.3%） | 全量 4564 行（2669/4564） |
| 分支覆盖（BRANCH） | 37.5%（v2.7 实测；v2.6 基线 31.0%） | 全量 1706 分支（640/1706） |
| 门禁阈值 | 0.55 | JaCoCo check，`verify` 阶段 |

## ④ 缺口表

| 类 | 当前覆盖 | 缺口原因 | 排期 |
| --- | --- | --- | --- |
| `LlmTransport` | 已补：纯函数 + HttpExecutor 契约测试 17 例 | 剩余缺口：真实代理链路（沙箱无外网） | 沙箱外验证 |
| `RunExecutor` | 已补：全 mock 编排测试 10 例 | 剩余：@Scheduled tick 真实调度 | v2.8 |
| video providers | 已补：MockVideoProvider 6 例 | 剩余：Agnes/Qwen 真实 provider（需外部 API） | v2.8 契约测试（录制回放） |
| E2E | 无 | Run 全链路端到端测试缺失 | v2.8 |

## ⑤ 本轮新增测试清单

- `ScriptSplitterServiceTest`（`com.dramafactory.service`）
  - 正常 2 镜全字段解析
  - 带 ``` 围栏输入解析
  - 空数组抛 `大模型未拆出任何分镜`
  - 根非数组抛 `大模型返回的不是 JSON 数组`
  - 非法 JSON 抛 `解析大模型返回内容失败: …`
  - 第 2 镜 `shotSize` 非法抛异常且 message 含“第 2 个分镜”
  - 非法 `cameraMove` → 抛 RuntimeException（第 N 个分镜的字段 cameraMove 非法）
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
- `LlmTransportTest`（17 例，`com.dramafactory.service`）
  - 代理纯函数：`parseProxy` / `resolveProxy` / `toHttpHost` 各合法与非法输入
  - `buildRequestConfig` / `buildPost` 请求构建
  - 注入 `HttpExecutor` 执行体：状态码与异常契约
  - 密码不泄露：凭证绝不进日志/异常
- `MockVideoProviderTest`（6 例，`com.dramafactory.service.video`）
  - 提交/轮询状态流转、失败路径、未知任务抛异常
- `RunExecutorTest`（10 例，Mockito 编排）
  - tick 空跑 / SCRIPT happy path / BOARD 读前置输出 / QC 审批门挂起 / step 异常→FAILED / VIDEO 跨 tick 等待 / VIDEO 全 DONE / VIDEO 有 FAILED / 全 SUCCEEDED 汇总 finalize / tick 吞 DB 异常
- `StatsIsolationTest`（2 例，MockMvc）
  - 项目统计隔离 / run 统计隔离
- `CameraMoveTest`（5 例）
  - null→null、空白→null、非法非空标签抛 IAE 等
