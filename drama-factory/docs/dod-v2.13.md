# DoD v2.13 — 分支覆盖冲 70%（第 12 轮）

- 里程碑：v2.13 第 12 轮「分支覆盖冲 70%」
- 时间：2026-10-14
- 编排：cron muse-dpsk-daily-build
- 结论：70% 目标达成、超额 3pp；744 全过；门禁棘轮上调并锁定

## 本轮交付（6 批 dpsk 生成 + 1 批回喂 + 编排验收）

| 批 | 内容 | 结果 |
| --- | --- | --- |
| A | ProviderServiceCoverageTest | 21 例（dpsk 原出 25 例，4 例与 ProviderServiceProbeTest 重复，编排侧已去重）；ProviderService 未覆盖分支 56 → 30（76.6%） |
| B | DashScopeImageProviderBranchTest | 25 例；DashScopeImageProvider 未覆盖分支 37 → 10（86.3%） |
| C | ByokControllerBranchTest | 21 例；ByokController 未覆盖分支 30 → 3（94.1%） |
| D | DidAvatarProviderBranchTest | 21 例；DidAvatarProvider 未覆盖分支 26 → 6（89.7%） |
| E | MiniMaxMusicProviderBranchTest | 20 例；MiniMaxMusicProvider 未覆盖分支 24 → 9（85.0%） |
| F | resolveExtension "bin" 不可达分支删除 | 两轮 PATCH 的 OLD 块与原文对不上，延期至 v2.14，本轮未动生产代码 |
| G | 回喂修 4 个断言 | 全过 |

- 全量数字：Tests run 744, Failures 0, Errors 0；行覆盖 82.4%（4536/5508）；分支覆盖 73.0%（1709/2340）；BUILD SUCCESS；All coverage checks have been met
- 门禁棘轮：pom JaCoCo LINE 0.80→0.82、BRANCH 0.68→0.70（只升不降）

## 对照（生产级 checklist 相关条）

- [通过] 测试金字塔补强（108 例；五类分支 173→58）
- [通过] 门禁棘轮（行 0.82/分支 0.70）
- [未通过→排期] resolveExtension "bin" 删除（F 两轮 PATCH 锚定失败，延期 v2.14）
- [未通过→排期] Agnes/Qwen submit/poll 录制回放（需外部 API）、h2c 锁定待产品确认（v2.9 遗留）
- [如实记录] 并发编辑事故与隔离验证做法（见事实来源）

## 本轮教训（已沉淀）

1. Jackson 2.17 readTree("") 返回 MissingNode 不抛异常——空 body 测试不许想当然写"解析异常"断言，先实测
2. 注意源码里 catch (RuntimeException e) { throw e;} 这类 rethrow——它会让底层 IAE 原样逃出，断言要对着真实行为
3. dpsk PATCH 的 OLD 锚定两轮失败就按"最多 2 轮"缩减里程碑，不许第三轮（本轮 F 批）
4. 并发编辑协议：WORKING.lock 不被遵守时，用树快照 + 排除对方坏文件做隔离验证；对方文件零改动、事后归还；提交只含自己的文件

## v2.14 排期

- 删 resolveExtension 不可达 "bin" 分支（F 延期）
- Agnes/Qwen submit/poll 录制回放（需外部 API）
- h2c 锁定待产品确认
- 分支覆盖冲 75%（候选待新报告）

## 覆盖率数字说明

本机 `mvn -o verify` 实测（快照隔离）；CI 环境跑全量后以 CI 为准。
=== END FILE ===
=== PATCH: ../PROJECTS.md ===
--- OLD ---
- DoD 未通过项新排期（见 docs/dod-v2.12.md：v2.13 分支覆盖冲 70%（差 30 分支；候选 ProviderService 56、DashScopeImageProvider 37、ByokController 30、DidAvatarProvider 26、MiniMaxMusicProvider 24）；删 resolveExtension 不可达 "bin" 分支；Agnes/Qwen submit/poll 录制回放（需外部 API）；h2c 锁定待产品确认）
--- NEW ---
- DoD 未通过项新排期（见 docs/dod-v2.12.md：v2.13 分支覆盖冲 70%（差 30 分支；候选 ProviderService 56、DashScopeImageProvider 37、ByokController 30、DidAvatarProvider 26、MiniMaxMusicProvider 24）；删 resolveExtension 不可达 "bin" 分支；Agnes/Qwen submit/poll 录制回放（需外部 API）；h2c 锁定待产品确认）
- 生产级补强 **v2.13 第 12 轮「分支覆盖冲 70%」**（2026-10-14）：5 个目标类全覆盖——新建 ProviderServiceCoverageTest 21 例（dpsk 原出 25，4 个与 ProviderServiceProbeTest 重复已去重）、DashScopeImageProviderBranchTest 25 例、ByokControllerBranchTest 21 例、DidAvatarProviderBranchTest 21 例、MiniMaxMusicProviderBranchTest 20 例；共 108 例全绿，测试总数 636→**744**；分支 **68.7%→73.0%**（70% 目标达成，超额 3pp）、行 80.5%→**82.4%**；五类剩余未覆盖分支 173→58（ProviderService 56→30、DashScopeImageProvider 37→10、ByokController 30→3、DidAvatarProvider 26→6、MiniMaxMusicProvider 24→9）；pom JaCoCo 门禁棘轮 LINE 0.80→0.82、BRANCH 0.68→0.70；发版对照报告 `docs/dod-v2.13.md`。本轮教训：Jackson 2.17 `readTree("")` 返回 MissingNode 不抛异常（断言错位已回喂修好）；DidAvatar `catch (RuntimeException e) { throw e;}` 会把 readTree 的 IAE 原样 rethrow；resolveExtension "bin" 删除两轮 PATCH 锚定失败、按流程缩减里程碑延期 v2.14；遭遇另一智能体并发改同一仓库（linkshort v1.2 + drama-factory 前端/GlobalExceptionHandler 在途未提交），本轮用树快照隔离验证、全量 744 绿，对方文件原样未动。
- DoD 未通过项新排期（见 docs/dod-v2.13.md：v2.14 删 resolveExtension 不可达 "bin" 分支；Agnes/Qwen submit/poll 录制回放（需外部 API）；h2c 锁定待产品确认；分支覆盖冲 75%）
=== END PATCH ===
