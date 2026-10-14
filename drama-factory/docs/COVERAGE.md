# 覆盖率目标与门禁（drama-factory）

## ① 目标

- **当前门禁：行覆盖（LINE）≥ 65%、分支覆盖（BRANCH）≥ 45%**，由 JaCoCo `check` 在 `verify` 阶段强制执行，未达标即构建失败。棘轮值按实测锁定（v2.8 实测行 71.0%/分支 52.7%），只升不降。
- **下一里程碑：v2.9 分支覆盖冲 55%**。


## ② 口径

- 命令：`mvn -o test`（离线执行单测），随后由 `jacoco-maven-plugin` 生成报告并做门禁校验。
- 报告产物：`drama-factory/target/site/jacoco/index.html`（行/分支/方法维度）。
- 已知稀释项：`dto`、`model`、`config` 等样板代码（纯 setter/getter、注解配置类）会被计入分母，天然拉低整体百分比。这是既定口径，不通过排除规则规避，避免掩盖真实缺口。

## ③ 基线表

| 指标 | 基线值 | 说明 |
| --- | --- | --- |
| 行覆盖（LINE） | 71.0%（v2.8 实测） | 全量 4766 行（3384/4766） |
| 分支覆盖（BRANCH） | 52.7%（v2.8 实测，目标 45% 超额达成） | 全量 1880 分支（991/1880） |
| 门禁阈值 | 行 0.65 / 分支 0.45 | JaCoCo check，`verify` 阶段 |


## ④ 缺口表

| 类 | 当前覆盖 | 缺口原因 | 排期 |
| --- | --- | --- | --- |
| `LlmTransport` | 已补：纯函数 + HttpExecutor 契约测试 17 例 | 剩余缺口：真实代理链路（沙箱无外网） | 沙箱外验证 |
| `RunExecutor` | 已补：全 mock 编排测试 10 例 + advanceRun/各 step 异常分支 13 例 + QC 自动门/checkVideoStep/finalize 13 例 | 剩余：@Scheduled tick 真实调度 | v2.9 |
| `LlmScriptService` | 已补：validate 9 例 + parseScenes 12 例 + buildUserContent 5 例 | 剩余：callModel 私有 HTTP/CLI 路径（需真实网络） | 沙箱外验证 |
| video providers | 已补：MockVideoProvider 6 例 + 录制回放契约测试（commit 37149e3） | 剩余：Agnes/Qwen 真实 provider（需外部 API） | 待定 |
| E2E | 已补：RunLifecycleE2eTest（commit 37149e3） | 剩余：跨服务长链路 | v2.9 |
| `AuthProxyController` | 无（分支缺口 110） | proxy() 内 HttpClient 构造器新建，无法注入 mock | v2.9（可测性重构：构造器注入 HttpClient） |


## ⑤ v2.7 新增测试清单（40 例）


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

## ⑤-2 v2.8 新增测试清单（104 例）

- `LlmScriptServiceTest` +26（`com.dramafactory.service`）
  - validate() 9 例：禁用/空模型/非法数值/非法 CLI 路径/可执行 CLI/自动探测
  - parseScenes() 12 例：null 内容/围栏变体/数组根/缺字段/非法值/可选字段默认值
  - buildUserContent() 5 例：捕获 body 断言 user 文本（无 project/空标题/空大纲/null 与空白角色表/project 懒加载抛异常防御）
- `RunServiceTest` +18
  - planPreview() 12 例：null goal/集数溢出/空对象/非法 JSON/超量截断/空标题回退/缺集号/围栏无换行/空白返回/非数组/长目标截断/0 集
  - createRun/pause/resume 6 例：正常建 run（5 种 AgentType + RUNNING）/空 goal/plan 拒绝/run 不存在/resume 正常与拒绝
- `ScriptSplitterServiceTest` +20
  - parse/strip 6 例：围栏无换行/字符串镜号回退序号/字符串时长回 5/缺 cameraMove 得 null/缺 shotSize 抛非法/数字 description 转文本
  - replaceShots()/splitFromScript() 14 例：episode 不存在/items null/空/超 30/正常替换旧分镜/缺镜号/非法景别/非法运镜/null 运镜/null 时长回 5/非法时长/splitFromScript 两处守卫
- `RunExecutorTest` +26
  - advanceRun 与各 step 异常分支 13 例：run 不存在/状态已变/无 step/无 PENDING 只有 RUNNING QC/type 缺失/各服务返回 null/缺 episodeId/BOARD 缺前置/EDIT 正常与 null
  - QC 自动门/checkVideoStep/finalize 13 例：真实临时文件 QC 通过/缺文件/无 filePath/缺 EDIT/空输出/空任务抛异常/失败任务 null 错误信息/非 mock provider 成本未知/无时间戳/未知成本致 totalCostCents null/空白审批配置仍等待/超长错误信息截断/空信息用类名
- `ProviderServiceProbeTest` 新建 14 例（`com.dramafactory.service`）
  - testConnection() 10 例：provider 不存在/非 VIDEO 模块/未知名称/null 名称/agnes 匹配探测/dashscope 匹配 qwen/mock 匹配/鉴权失败透传/checkedAt ISO 格式/null provider map 不抛 NPE
  - maskKey() 4 例：null/空/短 key/长 key 掩码

