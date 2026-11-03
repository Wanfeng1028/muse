# 发版对照报告 int 环境变量非法启动即报错（second-brain，2026-10-29 深耕轮）

可靠性：`internal/config/config.go` 的 `getIntEnv` 改为返回 `(int, bool)`，非法值返回 `(0, false)`，`Load` 对 `SB_SMTP_PORT`、`SB_RATE_LIMIT_BURST`、`SB_RATE_LIMIT_WRITE_BURST` 三个环境变量的非法值调用 `log.Fatalf` 报错退出，文案分别为对应变量非法。此前非法 int 环境变量会静默回退默认值，本轮改为启动即快速失败，使配置错误在启动阶段暴露，避免带错误配置运行。未设置环境变量时仍使用默认值 587 / 40 / 10，前后空白仍按 `TrimSpace` 解析，行为与之前一致。

可观测性：三个环境变量的非法值会通过 `log.Fatalf` 输出明确文案并以退出码 1 终止，便于在部署或启动阶段通过日志和退出码识别配置错误。未新增独立可观测端点或指标，但启动失败时的错误信息更明确，降低了排查成本。

数据与状态：本轮改动仅涉及启动时配置校验逻辑，不涉及持久化数据、状态存储或运行时数据流变更。非法配置会在启动阶段终止进程，不产生任何数据写入或状态变更，回滚仅需还原 `getIntEnv` 与 `Load` 调用即可。

部署运维：此为有意的启动契约变更，此前非法 int 环境变量会静默使用默认值，现启动即失败，部署前须检查环境变量配置。非法值导致启动退出码 1，合法值服务正常启动，冒烟测试中三值非法分别触发对应报错退出，合法时服务正常并通过 `GET /api/health` 返回 200 与 `{"status":"ok"}`。冒烟后服务已停止、端口已关闭，回滚方式为将 `getIntEnv` 恢复为返回默认值版本并还原 `Load` 三处调用。

安全与健壮性：启动时对非法 int 环境变量快速失败，减少了错误配置进入运行态的风险。未新增端口范围校验，`SB_SMTP_PORT=0` 或负数仍按既有路径处理，不在本轮范围；`getBoolEnv`、`getFloatEnv`、`RateLimitConfig.Validate`、`Push.Validate` 及所有默认值均未改动。

可维护性：`getIntEnv` 改为返回 `(int, bool)` 后，配置解析失败的信号更明确，`Load` 中三个校验点逻辑一致，便于后续维护和扩展。新增 `internal/config/config_int_env_test.go` 的 `TestGetIntEnv` 覆盖未设置、合法、前后空白、非法字符串、非整数、带非数字后缀、负数、空串 8 个子用例并全部通过，`go test ./...` 各包均 ok，`go vet` 全洁，`gofmt` 本轮两文件全洁。

结论：本轮改动已实现并经全量测试与真服务冒烟验证。新增 `TestGetIntEnv` 8 个子用例 8/8 通过，`go test ./...` 中 api、config、log、markdown、metrics、notify、push、ratelimit、review、search、store 各包均 ok，`go vet` 全洁，`gofmt` 两文件全洁。真服务冒烟中 `SB_RATE_LIMIT_BURST=abc`、`SB_SMTP_PORT=1x`、`SB_RATE_LIMIT_WRITE_BURST=1.5` 均启动退出码 1 且日志含对应非法文案，三值合法（40 / 10 / 587）时服务正常启动，`GET /api/health` 返回 200 与 `{"status":"ok"}`，冒烟后服务已停、端口已关。本轮为有意的启动契约变更，部署前须检查环境变量。

编排修正：模型首版把 `smtpPort` 校验插进了 `Config` 复合字面量内部导致编译失败，编排将其移至字面量之前后通过；测试文件经 `gofmt` 格式化后才全洁。
