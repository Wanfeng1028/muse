# 发版对照报告：v2.22 第 21 轮「分支覆盖冲 91%」

- 日期：2026-10-15
- 基线：分支 90.36% / 行 91.51%（v2.21 终值，3299 分支）
- 本轮：分支 **91.91%** / 行 **92.33%**（3032/3299 覆盖）
- 目标：分支 91% —— **达成**（+1.55pp，余量 0.91pp）
- 测试总数：1673 → **1725**（+52，全绿，2 skipped 为既有）
- 生产代码：零逻辑修改（仅 pom JaCoCo 门禁棘轮）
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash，分 6 批生成（A/B1/B2/C/E1/E2），编排验收修 8 处

## 各批交付

| 批 | 新测试文件 | 测试数 | 目标分支命中 |
|---|---|---|---|
| A | LlmTransportV222ATest | 11 | LlmTransport：L110/L178/L182/L183/L215/L230/L273 部分臂；parseProxy/resolveProxy 纯函数臂 |
| B1 | ScriptServiceV222BTest | 6 | ScriptService L104/L105/L185/L189/L194/L196/L201（L201 剩 blank-desc 臂，E1 补） |
| B2 | FfmpegServiceV222BTest | 11 | FfmpegService L113/L125/L127/L142/L174/L179/L240/L330/L325短臂/L421（反射调 private run + "false"/"true" 假命令，零污染秒级） |
| C | AgnesVideoProviderV222CTest | 14 | AgnesVideoProvider L116部分/L144/L203/L205/L213/L266/L282部分/L299/L303部分/L312（mock VideoHttpGateway 零真实网络） |
| E1 | LlmTransportV222ETest | 4 | LlmTransport L70-host-null/L100-env-null（L80 的 userInfo==null 臂既有测试已覆盖，剩余为 blank-userinfo 臂，排期 v2.23）；ScriptService L201 blank-desc 臂 |
| E2 | AgnesVideoProviderV222ETest | 6 | AgnesVideoProvider L116-199/L216-isNull/L284双臂/L290-url-null/L303-error-null |

终态：AgnesVideoProvider 分支 **100%**、ScriptService 分支 **100%**、FfmpegService 剩 2（诚实跳过）、LlmTransport 剩 7（含 4 个诚实跳过）。

## 门禁棘轮（只升不降）

- pom JaCoCo：LINE 0.91→**0.92**（实测 92.33%）、BRANCH 0.90→**0.91**（实测 91.91%）；全量 `mvn -o verify` 已验证新门禁通过

## 本轮修 dpsk 输出 8 处

1. A 批 `org.apache.hc.core5.testing.classic.ClassicResponseBuilder` —— httpcore5-testing 不在依赖里，改 `org.apache.hc.core5.http.io.support.ClassicResponseBuilder`（与既有 LlmTransportTest 一致）。
2. C 批 `"Bearer <redacted>"` —— 展示层脱敏占位符又被当字面量照抄（v2.19/v2.20 教训重犯），改为 `"Bearer test-key"`。
3. E2 批 `"Bearer <redacted>"` —— 同一毛病第二次，同样改为 `"Bearer test-key"`。教训：prompt 里点名警告仍防不住，验收时必须 grep 全文扫 `<redacted>`。
4. C 批 Shot/ShotSize/CameraMove 包写错 —— prompt 里我误写"与 AgnesVideoProvider 同包"，实际在 `com.dramafactory.model`（以既有 SubmitRecordingTest 的 import 为准），补三个 import。
5. E1 批 `getSource()` —— GenerateScriptResponse 是 record，访问器为 `source()`，已改。
6. E2 批 6 个测试方法漏 `throws Exception` —— gateway.exchange 声明受检异常，mock stub 要求方法签名声明，编排统一补上。
7. **编排 prompt 失误**：E 批 prompt 里 LlmTransport 的 L70/L80/L100 行号映射错位约 10 行（把 `host==null` 误标为 parseProxy 入口行等）。dpsk 按错误映射写的 A 批测试依然有效（命中了别的臂），E 批用源码原文重新锚定后补齐。教训：prompt 里的行号必须 `awk 'NR==n'` 实地核验，不能凭读文件时的印象写。
8. E1 批 probe：`new HttpPost((String) null)` 抛 NPE 已用本地 httpclient5 实测确认（`NullPointerException: Cannot invoke "String.length()"`），4 参 postJson 的 NPE 透传用例有效。

## 诚实跳过清单（经源码级论证不可达，本轮不写测试）

- **LlmTransport L250**（4 参 postJson 的 `catch (Exception e)` 通用包装臂）：try 块内所有调用（resolveProxy/toHttpHost/buildRequestConfig/HttpClients.build/5参调用）均不声明受检异常，5 参内部已包装——该臂不可达。
- **LlmTransport L273 剩余 1 分支**：`client` 在 5 参调用前已真实构建，恒非空；`client.close()` 抛异常无注入点——client==null 跳过臂与 close 抛异常 catch 臂均不可达。
- **LlmTransport L70 host.isBlank() 臂**：`URI.getHost()` 返回 null 或非空 host，blank host 恒不出现。
- **FfmpegService L313**（probeDurationSeconds 超时臂）：`waitFor(60, SECONDS)` 写死 60 秒，测试内无法确定性秒级触发。
- **FfmpegService L325 长输出臂**：ffprobe 失败且输出 >500 字符依赖真实 ffprobe 的 stderr 协议输出，单 token 假命令无法复现。

## DoD 未通过项新排期

- v2.23 分支覆盖冲 92%（候选：UsageService 14、ByokGenerateService 13、ScriptSplitterService 13、MvService 13；LlmTransport 剩余 L80-blank-userinfo 1 个 + L215/L230 各 1 个待源码级分析；需约 33 个分支）
- Agnes/Qwen submit/poll 真实链路（需外部 API）
- h2c 锁定待产品确认
- testFullPipeline flaky 根因（本轮一次通过，根因未消）
