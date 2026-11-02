# linkshort v1.37.1 发版对照报告

## 改动

`internal/handler/handler.go` 的 `shortBaseURL` 函数：

- 改动前：`cfg.BaseURL` 非空即 `TrimRight` 去末尾斜杠返回。
- 改动后：先 `TrimSpace` 去除首尾空白，再 `TrimRight` 去末尾斜杠；空白-only 的 `BaseURL` 视为空，走 `"http://" + r.Host` 回退；正常值行为不变；配置值本身不改写，只在拼接时处理。
- 其他文件、函数、注释、导入一字未动。

## 测试

- 新增 `internal/handler/shortbaseurl_test.go`，`TestShortBaseURLTrimsSpaces` 6 例（正常值、末尾斜杠、前后空白、斜杠加尾空白、空白-only、空串）全绿。
- 先红验证：临时回退生产改动后，新测恰好空白相关的 3 例失败、其余 3 例通过；恢复后复绿。
- `go vet` 全洁。
- 全量 `go test ./...` 14 包全部 ok。

## 冒烟

真实服务冒烟（18593 端口、`:memory:` 隔离库、已停服、端口已复查关闭、冒烟二进制已删）：

- `LINKSHORT_BASE_URL` 入参为前后带空白的值时：
  - `/api/meta` 的 `base_url` 返回不带空白的 `https://smoke.example.com`。
  - `POST /api/links` 的 `short_url` 为 `https://smoke.example.com/smoke1`（无空格）。
  - 短链访问 302 跳转到目标。
- 带 key 的 `/api/health` 与 `/api/readyz` 均返回 `{"ok":true}`。
- 无 key 的 `/api/health` 返回 `unauthorized`，属 `/api` 分组统一鉴权的既有行为。

## 对照结论

- **可靠性**：通过。核心逻辑改动经单测与真实冒烟双重验证，异常输入回退路径明确。
- **可观测性**：通过。冒烟覆盖 `/api/meta` 与短链访问，可确认最终拼接 URL 的正确性。
- **数据与状态**：通过。改动仅发生在请求时拼接阶段，不涉及数据库读写或状态变更。
- **部署运维**：通过。无新配置项、无新端点、无 schema 变更，运维侧仅需注意 `LINKSHORT_BASE_URL` 首尾空白将被忽略。
- **安全与健壮性**：通过。空白-only 输入安全回退到基于 Host 的默认值，不引入空 URL 或畸形 URL 风险。
- **可维护性**：通过。改动范围限定在一个函数内，逻辑清晰，测试覆盖充分。

## 已知限制

- 无 UI 改动，视觉验收不适用。
- `FromEnv` 未动，配置值本身保留原样，仅拼接时去除首尾空白。
- 无 schema 变更、无新依赖、无新端点。