# 发版对照报告：v2.17 分支覆盖冲 85%（第 16 轮）

- 日期：2026-10-15
- 目标：DoD v2.16 排期首项——分支覆盖 82.45% → 85%
- 实际：分支 **82.45% → 85.33%**（+2.88pp），行 88.30% → **89.86%**（+1.56pp）
- 结论：**85% 目标达成**。纯测试增量轮，生产代码零逻辑修改（仅 pom JaCoCo 门禁棘轮）。`mvn -o verify` 全绿。
- 测试总数：1295 → **1460**（+165），未覆盖分支 2895 → 2484（-411）。

## 本轮工作（11 个新测试文件，微信 ChatAPI DeepSeek-V4-Flash 生成 + 编排验收修 14 处）

| 批次 | 新测试文件 | 测试数 | 目标类分支变化 |
| --- | --- | --- | --- |
| 遗留-A | `service/RunExecutorBranch2Test.java` | 24 | RunExecutor 收尾 |
| 遗留-B | `service/video/QwenVideoProviderBranch2Test.java` | 27 | QwenVideoProvider 收尾 |
| 遗留-C | `service/LlmScriptServiceBranch4Test.java` | 16 | LlmScriptService 收尾 |
| 遗留-D | `service/byok/ByokGenerateServiceBranch2Test.java` | 20 | ByokGenerateService 收尾 |
| E1-1 | `service/RunExecutorBranch3Test.java` | 16 | RunExecutor → **96.0%** |
| E1-2 | `controller/AuthProxyControllerBranch2Test.java` | 13 | AuthProxyController → **93.8%** |
| E2-1 | `service/video/QwenVideoProviderBranch3Test.java` | 11 | QwenVideoProvider → **93.8%** |
| E2-2 | `service/byok/ByokGenerateServiceBranch3Test.java` | 9 | ByokGenerateService → **91.7%** |
| E2-3 | `service/LlmScriptServiceBranch5Test.java` | 7 | LlmScriptService → **93.5%** |
| E3-1 | `controller/MediaControllerBranchTest.java` | 12 | MediaController 77.8%（此前 5 个端点零覆盖） |
| E3-2 | `config/CookieAuthFilterTest.java` | 10 | CookieAuthFilter → **100%** |

- pom JaCoCo 门禁棘轮：LINE 0.88→**0.89**、BRANCH 0.82→**0.85**。
- 另收录调研文档 `docs/CODE_ANIMATION_BACKEND_RESEARCH.md`（主 agent 记的用户转发抖音 AI 视频动效路线笔记）。

## 验收过程（修的真问题，共 14 处；生产代码零修改）

1. **遗留-D `T16 urlWithoutSlash`**：dpsk 用裸 `"file.png"` 测 resolveExtension 无斜杠臂，JDK `HttpRequest.uri()` 抛 `IllegalArgumentException: URI with undefined scheme`；改 `"https:file.png"` 仍被拒（`unsupported URI`）。写 UriProbe 实测确认：JDK 要求 scheme://authority 缺一不可，能到达 resolveExtension 的 URL 必含 '/'，该臂防御性不可达——删测试、记入诚实跳过清单第 6 条并注释。
2. **E1-2 `HttpHeaders` 歧义**：dpsk 混用 Spring 的 `HttpHeaders` 与 `java.net.http.HttpHeaders`（`HttpResponse.headers()` 返回后者）。修 3 处：helper 参数改全限定名、加双参重载、11 处调用点去 Spring 空构造。
3. **E1-2 缺 `throws Exception`**：`httpClient.send` 声明受检异常，`stubSend` 改 throws 后 8 个测试方法补 `throws Exception`。
4. **E1-2 `HttpHeaders.of` 对 null key 抛 NPE**：JDK 自身 `requireNonNull(key)`，改 mock `java.net.http.HttpHeaders` + stub `map()` 返回含 null key 的 HashMap。
5. **E1-2 null authServiceUrl**：相对 URI 同样被 JDK 拒绝（非预期），改断言退化行为：构造不抛、proxy 抛 IllegalArgumentException（生产 @Value 恒有默认值，走不到）。
6. **E2-1 编造枚举**：`CameraMove.PUSH_IN`→`TUI`（推镜头）、`ShotSize.MEDIUM`→`ZHONG_JING`（中景）。
7. **E2-1 缺 import**：`VideoProvider.ConnectivityStatus` / `ConnectivityResult` 为接口嵌套类型，补显式 import。
8. **E2-1 poll 空 body 断言错误**：dpsk 断言抛 RuntimeException，实测 `readTree("")` 得 MissingNode 不抛错（v2.13 教训复用），改断言返回 PROCESSING。
9. **E2-2 嵌套 `when()`**：`pollSucceeded()`/`okResponse()` 内含 `when()` 却被包在 `.thenReturn(...)` 里，6 处全部 hoist 到变量（prompt 明令禁止仍犯，验收时 grep `thenReturn(\w+\(` 扫一遍最快）。
10. **E2-3 测试输入污染**：前缀 `"前缀 {ignore} 主体 "` 中的花括号污染"第一个 `{`"定位，抽取拼出非法 JSON；改纯文本前缀并注释原因。
11. **E2-3 注释 `/**` 漏写**：编排改注释时吞掉 opener 致编译失败，补回。
12. **删 3 个 0 字节测试垃圾**：`drama-factory/unused/byok/` 下 2 png + 1 mp4（上一轮测试残留，空文件），目录一并删除。

## 本轮教训

1. **"防御性"分支先实测可达性再决定测/跳过**：JDK HttpRequest 的 URI 校验（scheme://authority）比直觉严，resolveExtension 的无斜杠臂、trimTrailingSlash 的 null 臂（AuthProxyController 262 行倒是可达：构造器可传 null）都要先写 10 行 probe 验证，不凭感觉。
2. **嵌套 `when()` 是 dpsk 高频犯规**：prompt 里写了也不长记性；验收固定动作——`grep -n "thenReturn([a-zA-Z]*("` 扫一遍。
3. **枚举值必须贴进 prompt**：只写"先 grep 确认"等于没写，dpsk 照编不误（PUSH_IN/MEDIUM）。以后 prompt 直接贴枚举定义原文。
4. **`readTree("")` → MissingNode**（v2.13 教训）第二次救场：空 body 不抛错，断言要按实际行为写。

## DoD 未通过项新排期（v2.18）

- Agnes/Qwen submit/poll 录制回放扩到真实链路（需外部 API，v2.9 起遗留）
- h2c 锁定待产品确认（v2.9 遗留）
- `DramaV2ApiIntegrationTest.testFullPipeline` flaky 根因（ffmpeg 环境抖动；考虑 mock 化视频轮询）
- 分支覆盖 85.33% → 87%：候选 AssetService（19 未覆盖分支）、SettingsService（18）、RunService（18）、MediaController（剩余 4）
