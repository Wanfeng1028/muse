# second-brain 布尔环境变量非法值启动即报错：发版对照报告（靶向范围）

变更事实：
- internal/config/config.go: getBoolEnv now returns (bool, bool); Load() fatals at startup with log.Fatalf "SB_XXX 非法: %q" for illegal SB_PUSH_ENABLED, SB_SMTP_TLS, SB_METRICS_ENABLED, SB_RATE_LIMIT_ENABLED, mirroring the existing int/float env pattern. Defaults unchanged (false / true / true / true); TrimSpace and case-insensitivity unchanged; valid tokens unchanged (1/true/yes/on, 0/false/no/off). New test file internal/config/config_bool_env_test.go with 18 subcases; CHANGELOG [Unreleased] entry added. No version bump, no schema change, no new env vars, no UI change, no API change.

测试与验证：
- go test ./internal/config/ passes (TestGetBoolEnv 18/18, TestGetIntEnv 8/8); go vet clean; gofmt clean for both changed files.
- Real-service smoke: built ./cmd/server; SB_PUSH_ENABLED=maybe, SB_SMTP_TLS=banana, SB_METRICS_ENABLED=xx, SB_RATE_LIMIT_ENABLED=2 each exit 1 with the exact fatal line; with all four valid, the server starts, GET /api/health returns {"status":"ok"}, GET /api/notes returns []; server killed by PID afterwards and the port is confirmed closed; smoke binary and database deleted.

已知限制：
- full go test ./... all packages ok (api 106.5s, store 97.1s, rest under 10s); the Load() fatal path itself is not unit-tested (log.Fatalf exits the process, same as the existing int/float pattern); SB_ATTACH_MAX_MB and SB_PUSH_MAX_RETRIES / SB_PUSH_RETRY_BASE_MS still silently fall back and are out of scope; parseIntDefault now has no production callers and is left in place for a later cleanup round.

发版对照清单：
- 可靠性-输入校验（通过，本范围）
- 可观测性（不适用，无日志指标改动）
- 数据与状态（不适用，无 schema 改动）
- 部署运维-启动校验（通过，非法配置启动即死）
- 安全-防静默误配置（通过，本范围四个变量）
- 可维护性-文档同步（通过，CHANGELOG 已记）
- 全量测试（通过，各包均 ok，api 106.5s、store 97.1s）
- 视觉验收（不适用，无 UI 改动）

结论：靶向范围可发版；已知限制如上。