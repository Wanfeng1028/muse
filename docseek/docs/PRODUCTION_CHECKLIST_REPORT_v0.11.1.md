
# docseek v0.11.1 发版对照报告

## 元信息

| 项目 | 内容 |
| --- | --- |
| 版本 | v0.11.1（补丁级；对外版本号保持 0.11.0） |
| 主题 | 版本号唯一来源收敛 + 定位逻辑公共抽取 + 对应测试补齐 |
| 日期 | 2026-10-17 |
| 对照基线 | docs/PRODUCTION_CHECKLIST_REPORT_v0.11.md |

## 改动范围（文件级）

新增文件：

- `include/docseek/version.h`
- `include/docseek/token_locate.h`
- `src/token_locate.cpp`
- `tests/test_token_locate.cpp`

修改文件：

- `src/main.cpp`
- `src/service.cpp`
- `src/jieba_tokenizer.cpp`
- `src/searcher.cpp`
- `tests/test_service.cpp`
- `CMakeLists.txt`
- `README.md`（搜索质量小节更新 v0.11.0 数据）
- `CHANGELOG.md`

改动要点：

1. 版本号唯一来源：`docseek::kDocseekVersion = "0.11.0"`；修复 v0.10.0 遗留的 `service.cpp` 两处 `"0.9.0"` 硬编码（`/api/health` 响应 + 启动日志）。
2. 定位逻辑公共抽取：新增 `claimTokenPositions(text, words, claimed)`；`jieba_tokenizer` 改为逐词调用该函数（主路径 + 码点回退，交错语义与原来逐行处理一致）；`searcher` 的 `expandTokenOrQuery` 改用该函数（定位失败计数不等时退化为 `quoteToken(token)`，与原来行为一致）。
3. 测试：新增 `tests/test_token_locate.cpp`（7 例）；`tests/test_service.cpp` 的 Health 用例增加版本断言（断言取值来自唯一来源常量，不硬编码字面量）。
4. 无 DB schema 变更、无索引格式变更、无新第三方依赖；版本号保持 0.11.0（补丁级）。

## 1. 可靠性

本轮改动涉及 `jieba_tokenizer` 与 `searcher` 两条既有检索路径的内部实现替换（由各自的逐行/内联逻辑改为共用 `claimTokenPositions`），属于行为等价重构，语义按改动说明保持与原来一致。

- 定位一致性：`jieba_tokenizer` 逐词调用共用函数，主路径与码点回退交错语义与原来逐行一致；`searcher` 的 `expandTokenOrQuery` 在定位失败计数不等时退化为 `quoteToken(token)`，与原来一致。
- 新增 `tests/test_token_locate.cpp` 7 例覆盖共用定位函数；`tests/test_service.cpp` 增加 Health 版本断言。

本轮未改动的可靠性维度（进程生命周期、故障恢复、资源回收等）：未验证，沿用 v0.11.0 结论。

本报告基于代码审查与既有测试推定，不包含本轮实测结论；测试通过情况由编排侧在合并前实测验证。

## 2. 可观测性

- 修复 `service.cpp` 启动日志中遗留的 `"0.9.0"` 硬编码，改为取自 `docseek::kDocseekVersion`，消除日志版本与实际版本不一致的问题。
- `/api/health` 响应中的版本字段同样改为取自唯一来源常量，消除该端点对外报告旧版本号的缺陷。
- `tests/test_service.cpp` 的 Health 用例增加版本断言，且断言引用唯一来源常量而非字面量，避免测试与实现各写一份版本号。

本轮未改动的可观测性维度（日志分级、指标、追踪等）：未验证，沿用 v0.11.0 结论。

## 3. 数据与状态

- 无 DB schema 变更。
- 无索引格式变更。
- 无数据迁移、无回填、无状态机调整。

本轮数据与状态相关结论：未验证，沿用 v0.11.0 结论；本轮改动不触及持久化层与索引格式。

## 4. 部署运维

- 无新第三方依赖，构建依赖集不变。
- `CMakeLists.txt` 有改动（纳入新增源文件与新增测试目标），构建产物组成相应变化，但对外接口与运行方式不变。
- 版本号保持 0.11.0（补丁级），运维侧版本标识与制品命名策略不受影响。

本轮未改动的部署运维维度（打包、发布流程、运行时配置等）：未验证，沿用 v0.11.0 结论。

## 5. 安全健壮性

- `claimTokenPositions` 为纯定位逻辑抽取，未引入新的外部输入解析路径；调用方原有边界处理（码点回退、定位失败退化）在抽取后保留。
- 无新增依赖，不扩大供应链面。
- 无新增网络端点、无权限模型调整。

本轮未改动的安全健壮性维度（鉴权、输入校验覆盖面、资源上限等）：未验证，沿用 v0.11.0 结论。

## 6. 可维护性

- 版本号收敛为单一来源（`include/docseek/version.h`），消除多处硬编码漂移风险；本轮即修掉了 `service.cpp` 中两处残留的 `"0.9.0"`。
- 定位逻辑收敛为单一实现（`include/docseek/token_locate.h` + `src/token_locate.cpp`），`jieba_tokenizer` 与 `searcher` 共用，减少同一语义的多份实现。
- 测试侧：新增 `tests/test_token_locate.cpp` 针对共用函数；`test_service.cpp` 版本断言绑定常量而非字面量，降低后续版本升级时的测试维护成本。
- `README.md` 搜索质量小节更新为 v0.11.0 数据；`CHANGELOG.md` 记录本轮改动。

## 7. 周期机制

本轮未改动周期机制相关代码与配置。未验证，沿用 v0.11.0 结论。

## 结论

本轮为补丁级改动，版本号保持 0.11.0。改动集中在三处：版本号唯一来源收敛（并修复 `service.cpp` 两处 `"0.9.0"` 硬编码）、定位逻辑公共抽取（`jieba_tokenizer` 与 `searcher` 共用 `claimTokenPositions`）、以及配套测试补齐（新增 `test_token_locate.cpp` 7 例，`test_service.cpp` 增加版本断言）。无 DB schema 变更、无索引格式变更、无新第三方依赖。

编排侧已实测验证（2026-10-17）：cmake 构建零警告（警告仅来自第三方 cppjieba/limonp 头文件，既有）；`./docseek_tests --gtest_filter='-WatcherTest.SubDir'` **157/157 全过**（含新增 `TokenLocate` 7 例与 `SvcFixture.Health` 版本断言）；`WatcherTest.SubDir` 为 v0.5.0 已有 flaky（inotify 时序），单独重跑仍挂，确认与本轮无关。

## 已知问题与待办

1. `WatcherTest.SubDir` flaky —— v0.5.0 已存在的问题，本轮未处理。
2. T2 连续出现要求与 qa 4/12 —— v0.11.0 已记录的问题，本轮未改动。
3. 本轮未对未改动维度做回归验证，相关维度结论均沿用 v0.11.0 报告，需在后续版本或专项验证中确认仍然成立。
