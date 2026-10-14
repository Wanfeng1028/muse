# 发版对照报告：drama-factory v2.9（生产级补强第 8 轮）

日期：2026-10-14。里程碑 v2.9，对应 docs/dod-v2.8.md 的 v2.9 排期两项：① AuthProxyController 可测性重构 + 代理分支测试（目标该类分支覆盖 ≥60%）；② 分支覆盖冲 55%。两项均达成且超额。

## 交付清单

| # | 项 | 交付物 | 验证 |
|---|---|---|---|
| 1 | AuthProxyController 可测性重构 | 构造器内写死的 `HttpClient` 改为构造器注入：新增包可见重载 `AuthProxyController(String authServiceUrl, HttpClient httpClient)` 供测试；原 public 构造器委托调用，默认客户端构建抽成 `private static defaultHttpClient()`（connectTimeout 5s、Redirect.NEVER 原样保留）；因双构造器导致 Spring 报 `No default constructor found`（40 个 Spring 上下文测试全挂），补 `@Autowired` 显式标记注入入口 | `mvn -o verify` 全绿：Tests run 356, Failures 0, Errors 0, Skipped 0；BUILD SUCCESS |
| 2 | AuthProxyControllerTest 新建 20 例 | T1~T10（透传基本链路/query 拼 URL/hop-by-hop 过滤/df_at cookie 补 Authorization/头优先于 cookie/refresh 无 cookie 401/refresh body 替换/GET noBody/上游 500 透传/尾斜杠处理）+ T11~T20（login token 剥离写 cookie/expiresIn 缺失默认 3600/非 JSON 转 502/400 原样透传/oauth 回调剥离/logout 清 cookie/logout 500 透传/send 抛 IOException/InterruptedException/读 body 抛 IOException）；上游用 JDK `com.sun.net.httpserver.HttpServer` 绑 `::1` 随机端口（IPv6 回环直通，见下） | 20/20 通过 |
| 3 | 分支覆盖冲 55% | 全量分支 52.7%→**57.3%**（1078/1880），行 71.0%→**73.6%**（3505/4764）；AuthProxyController 单类分支 0%→**79.5%**（89/112）、行 97.8%、方法 100% | JaCoCo check 通过 |
| 4 | 门禁棘轮 | pom.xml：LINE 0.65→0.70，BRANCH 0.45→0.55（只升不降）；`mvn -o verify -DskipTests` 复核新门禁通过 | All coverage checks have been met |

## 本轮攻坚记录

1. **dpsk 第 3 批整批作废**：输出凭空发明了不存在的 API（`stubUpstream()` 方法、双参数 `proxy(req, resp)`、单参数构造器、`MockHttpServletResponse`），与真实签名 `ResponseEntity<byte[]> proxy(HttpServletRequest)` 完全对不上。按打回规矩重发 prompt（把当前测试文件全文贴进去当事实来源），第二版一次可用。
2. **第 2 批 OLD 锚点缩进被 dpsk 抹掉**：编排者手工按原文缩进应用；另人工修正生成测试 4 处断言错误（T1 误断响应体为请求体、T3 未考虑 HttpClient 自动补 Host/Content-Length、T10 尾部一句无意义断言）。
3. **T3 失败定位出真知识**：`HttpClient.newHttpClient()` 默认尝试 h2c 升级，明文 HTTP 会带 `Connection: Upgrade, HTTP2-Settings` + `Upgrade: h2c`（`HdrProbe` 实测确认）。测试改为断言"伪造值不许透传"（assertNotEquals）而非"头不存在"。生产代码 `defaultHttpClient()` 同样未指定 version，行为一致，非测试假象。
4. **双构造器 Spring 坑**：重构后 40 个 Spring 上下文测试报 `No default constructor found`——单构造器时 Spring 隐式选用，多构造器必须显式 `@Autowired`。已补注解，全量恢复。

## DoD 对照（本轮相关项）

- [通过] 测试金字塔补强（新增 20 例；AuthProxyController 分支 79.5% ≥ 60% 目标）
- [通过] 门禁棘轮（行 0.70/分支 0.55，verify 阶段强制）
- [通过] 技术债有记录（COVERAGE.md 缺口表更新，见下）
- [不适用] 数据库迁移版本化（本轮无表结构变更）
- [不适用] 视觉验收（本轮无 UI 变更）
- [未通过→排期] Agnes/Qwen 真实 provider 分支（需外部 API）、LlmTransport 真实代理链路（沙箱无外网）——与 v2.8 相同，口径不变

## 已知限制

- 覆盖率数字为本机 `mvn -o verify` 实测；CI 环境跑全量后以 CI 为准。
- 测试里上游 HttpServer 绑 `::1`：依赖"沙箱 IPv6 回环直通"的前提（沿用构造器注释里的既有结论）；若换环境 IPv6 不可用，T1~T17 需改绑 127.0.0.1。

## v2.10 排期

- 分支覆盖冲 60%（剩余缺口：ChatService、FinalCutService、VideoTaskService 的异常/边界分支）。
- Agnes/Qwen 真实 provider 录制回放扩到 probe 之外的 submit/poll 分支（需外部 API 时）。
- AuthProxyController 的 h2c 默认行为：评估是否在 `defaultHttpClient()` 显式 `.version(HTTP_1_1)` 锁定，避免升级头噪音（行为变更，需产品确认，暂不做）。
