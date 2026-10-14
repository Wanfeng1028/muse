# 覆盖率目标与门禁（drama-factory）

## ① 目标

- **当前门禁：行覆盖（LINE）≥ 80%、分支覆盖（BRANCH）≥ 68%**，由 JaCoCo `check` 在 `verify` 阶段强制执行，未达标即构建失败。棘轮值按实测锁定（v2.12 实测行 80.5%/分支 68.7%），只升不降。
- **下一里程碑：v2.13 分支覆盖冲 70%**（差 30 个分支）。


## ② 口径

- 命令：`mvn -o test`（离线执行单测），随后由 `jacoco-maven-plugin` 生成报告并做门禁校验。
- 报告产物：`drama-factory/target/site/jacoco/index.html`（行/分支/方法维度）。
- 已知稀释项：`dto`、`model`、`config` 等样板代码（纯 setter/getter、注解配置类）会被计入分母，天然拉低整体百分比。这是既定口径，不通过排除规则规避，避免掩盖真实缺口。

## ③ 基线表

| 指标 | 基线值 | 说明 |
| --- | --- | --- |
| 行覆盖（LINE） | 80.5%（v2.12 实测） | 全量 5499 行（4429/5499） |
| 分支覆盖（BRANCH） | 68.7%（v2.12 实测；70% 目标未达成，差 30 分支） | 全量 2328 分支（1599/2328） |
| 门禁阈值 | 行 0.80 / 分支 0.68 | JaCoCo check，`verify` 阶段 |


## ④ 缺口表

| 类 | 当前覆盖 | 缺口原因 | 排期 |
| --- | --- | --- | --- |
| `LlmTransport` | 已补：纯函数 + HttpExecutor 契约测试 17 例 | 剩余缺口：真实代理链路（沙箱无外网） | 沙箱外验证 |
| `RunService` | 已补：v2.12 追加 21 例（markSucceededIfAllDone/cancel/rerun/approve/retryStep/requireRun/toXxx/stats/sanitizeJson）；单类分支 89.1%（164/184） | 剩余 20：BYOK 相关与防御性分支 | v2.13 |
| `RunExecutor` | 已补：v2.12 追加 12 例（tick 异常吞没/审批门默认/ QC 空文件/EDIT 空 filePath/recordToolCall 合并与重建/finalize）；单类分支 87.3%（138/158） | 剩余：@Scheduled tick 真实调度、不可达防御分支 | — |
| `LlmScriptService` | 已补：v2.12 追加 12 例（validate null/blank cliPath、parseScenes 截断 JSON/5 场/sceneNo 越界/null 字段/纯数组、buildUserContent null outline、doGenerate 重试）；单类分支 73.2%（101/138） | 剩余：callModel 真实 HTTP/CLI 路径（需真实网络） | 沙箱外验证 |
| `ByokGenerateService` | 已补：v2.12 新增 DownloadSender 接缝 + 28 例；单类分支 71.3%（97/136）、行 87.0% | 剩余 39：超时 deadline 分支（150s/240s 不可测）、"bin" 回退分支不可达（建议删除） | v2.13 |
| `SurrogateAuthClient` | 已补：v2.12 新增 SocketExchange 接缝 + 19 例；单类分支 80.4%（37/46） | 剩余：真实 Unix socket 链路 | 沙箱外验证 |
| `ProviderService` | 缺口：56 分支（BYOK probe 相关新增） | 待补 | v2.13 |
| `DashScopeImageProvider` | 缺口：37 分支 | 待补（真实网络链路需录制回放） | v2.13 |
| `ByokController` | 缺口：30 分支 | 待补 | v2.13 |
| video providers | 已补：MockVideoProvider 6 例 + 录制回放契约测试（commit 37149e3） | 剩余：Agnes/Qwen 真实 provider（需外部 API） | 待定 |
| E2E | 已补：RunLifecycleE2eTest（commit 37149e3） | 剩余：跨服务长链路 | v2.9 |
| `AuthProxyController` | 已补：可测性重构（HttpClient 构造器注入）+ 20 例代理分支测试；单类行 97.8%/分支 79.5%/方法 100% | 剩余：无 | — |
| `ChatService` | 已补：可测性接缝（Function 接缝 + 包可见构造器）+ 10 例；单类分支 100%（20/20） | 剩余：真实网络链路（沙箱无外网） | 沙箱外验证 |
| `FinalCutService` | 已补：19+1 例；单类分支 100%（28/28）、行 100% | 剩余：无 | — |
| `VideoTaskService` | 已补：37+6 例；单类分支 92.9%（39/42） | 剩余 3：awaitPollCompletion 超时 warn 路径 2、doPoll switch 隐式分支 1 | v2.12 评估 |
| `UsageService` | 已补：27 例；三参 summary/requests/byDay/byRun/filters/byModel 边界收敛 | 剩余：byDay/byRun 的防御性分支 | v2.12 |
| `AgnesVideoProvider` | 已补：poll 边界 20 例（录制回放，零真实网络） | 剩余：submit 真实链路分支（需外部 API） | 待定 |
| `ScriptSplitterService` | 已补：HttpExchange 可测性接缝 + callModel 16 例；附带修 JSON null content 真 bug | 剩余：真实网络链路 | 沙箱外验证 |
| `EgressProxyConfig` | 已补：configureFromEnv(Map) 接缝 + 11 例（含 JVM 全局状态隔离） | 剩余：无 | — |
| `RunLogService` | 已补：12 例；单类分支 81.8%（18/22） | 剩余 4：startsWith 防御分支（不可达）、read<=0、append/read IOException catch | —（防御性分支，接受未覆盖） |


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

## ⑤-3 v2.10 新增测试清单（85 例）

- `ChatServiceTest` 新建 10 例（`com.dramafactory.service`）
  - 消息校验 3 例：null/空白/超 4000 字
  - 成功路径 7 例：body 形态（model/max_tokens/temperature）/历史截断取最后 12 条/null 与空白条目跳过/role 归一化/stub 异常透传/空历史/恰好 4000 字
  - 附带生产代码改动：`Function<ObjectNode, String>` 可测性接缝 + 包可见 5 参构造器；public 构造器补 `@Autowired`（双构造器 Spring 坑，v2.9 AuthProxyController 同款）
- `FinalCutServiceTest` 新建 20 例（`com.dramafactory.service`）
  - buildFinalCut 8 例：剧集不存在/无分镜/分镜无 DONE 视频三变体/成功全链路/拼接失败/存储目录被占（checked 异常包装分支）
  - qc 6 例：通过（verdict 归一化）/打回/未完成/非法 verdict/空 verdict/不存在
  - get/listByShot/toResponse 6 例：不存在/空映射/fileName 提取与空路径
- `VideoTaskServiceTest` +43（新建 37 + 追 6）
  - computeBackoffMs 7 例：0/1/2/5/6/7/100（封顶 600000）
  - submit 3 例：幂等命中/镜头不存在/新建；submitAllForEpisode 2 例；retry 3 例；get/listByShot 4 例
  - processDueTasks 17 例：空/PENDING 提交（null 时长默认 5 秒）/8 秒/限流 45 秒与 5 秒取 max 30/失败重试/达上限 FAILED/轮询 COMPLETED 四种 URL 形态（正常秒数/非法秒数回退/无参数/& 截断）/refresh 异常吞掉/FAILED/QUEUED/HTTP 下载失败/URL 为 null
  - 追 6 例：provider agnes/qwen 分支/doPoll PROCESSING 结果/toResponse 本地文件缺失/awaitPollCompletion 在途完成与被中断（反射改 pollInFlight + 线程）
- `RunLogServiceTest` 新建 12 例（`com.dramafactory.service`）
  - append 6 例：时间戳行/null 行/空 runId/空 seqNo/负 id/两次追加
  - read 6 例：缺文件/负偏移/全量 eof/大文件分段（64KB 截断）/超界偏移/空 id

## ⑤-4 v2.11 新增测试清单（74 例）

- `UsageServiceTest` +27（`com.dramafactory.service`）
  - summary 三参 10 例：全空/空字符串快速路径、days 正/非正过滤路径、video 行 provider-model 过滤与空 token、step 行 provider 跳过/label 为 null/model 不匹配
  - requests 6 例：modelUsed 为 null 跳过、step label 为 null、step model 不匹配、video status 为 null、null 时间排序三态、limit 截断与非正
  - byDay 5 例：video model 过滤、step provider 跳过、空 token 按 0 合并、负天数默认、step label 为 null
  - byRun 3 例：limit<=0 默认 20（ArgumentCaptor）、Run 自带总量直用（verify never）、goal 为 null
  - byModel 2 例 + filters 1 例：null model/label/类型跳过
- `AgnesVideoProviderPollBranchTest` 新建 20 例（`com.dramafactory.service.video`，录制回放零真实网络）
  - 鉴权缺失/网关异常/429/500 三形态/非法 JSON/无 status 与 status:null/completed 三取 URL/failed 三取错误信息/processing 进度三形态/taskId URL 编码
- `ScriptSplitterCallModelTest` 新建 16 例（`com.dramafactory.service`）
  - HttpExchange 可测性接缝（包可见 8 参构造器；public 构造器 @Autowired 委托）；鉴权头有/无、发送异常、500 三形态、非法 JSON、choices 缺失/非数组/空/message 为 null/content 为 null（真 bug 锁定）/空白、请求体形态、episode 状态推进
- `EgressProxyConfigTest` 新建 11 例（`com.dramafactory.config`）
  - configureFromEnv(Map) 接缝；无变量零副作用/大小写优先级/非法 URI/无 host/属性设置/默认端口/ProxySelector 本地与远端/userInfo 鉴权器/connectFailed；JVM 全局状态保存恢复
