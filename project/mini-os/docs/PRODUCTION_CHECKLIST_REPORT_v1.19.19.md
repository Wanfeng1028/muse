# Production Checklist Report — mini-os v1.19.19

## 改动摘要

- `src/config.rs`：新增 `pub` 纯解析函数 `parse_database_path_raw` 与 `parse_static_dir_raw`；`from_env` 里 `DATABASE_PATH` / `STATIC_DIR` 由 `unwrap_or_else` 缺省改为 fail-fast（非法时 `eprintln` 配置错误 + `exit(2)`，与 `PORT` 等分支同款）；`from_env` 文档注释同步。
- 语义：缺失仍用默认值（`data/mini-os.db` / `static`）；空串或纯空白非法，文案含变量名与“不能为空”；合法值 trim 后生效。
- `Cargo.toml` 与 `Cargo.lock` 版本由 1.19.18 升为 1.19.19。
- 新增测试：`tests/config_path_strict_test.rs`，4 个测试函数（两变量各一组合法与默认值、一组空值拒绝），用纯解析函数断言，不碰 `from_env`。

## 逐条对照表

| 条目 | 判定 | 理由 / 证据 |
| --- | --- | --- |
| 可靠性 | 通过 | 靶向测试合计 21/21：`config_path_strict_test` 4/4、`config_env_strict_test` 4/4、`config_deep` 10/10、lib 内 config 单元测试 3/3。真实冒烟：`DATABASE_PATH` 空串启动 exit 2、`STATIC_DIR` 纯空白启动 exit 2，合法配置起服后 health/readyz/register 行为符合预期；冒烟后服务已按 PID kill、端口复查已关、冒烟库已删。 |
| 可观测性 | 通过 | fail-fast 配置错误经 stderr 输出，文案含变量名与“不能为空”，冒烟末行实测可见；`GET /api/health` 返回 `{"status":"ok","version":"1.19.19"}`、`GET /api/readyz` 返回 `{"status":"ready"}`，均可观测。 |
| 数据 | 通过 | 无数据库迁移；冒烟使用 18573 端口隔离库，路径配置非法时 fail-fast 阻止带病启动；冒烟后冒烟库已删，无残留。 |
| 部署 | 通过 | 缺失变量仍回落默认值，合法部署路径行为向后兼容；非法配置 fail-fast（exit 2）语义明确、与 `PORT` 等分支一致；冒烟验证了合法配置起服与空串/纯空白两类非法场景。 |
| 安全 | 通过 | 无新增依赖、无新增端点；fail-fast 避免服务带空路径启动的运行期风险；冒烟库已清理。 |
| 可维护性 | 通过 | `cargo fmt --all --check` 干净（新测试文件经 rustfmt 一次格式化后复测仍 4/4）；`cargo clippy --lib` 8 个告警均不在本轮改动文件、无 `src/config.rs` 归属告警；新增纯解析函数与独立测试文件，可测性提升。 |
| 全量测试 | 不适用 | 本轮未跑全量 `cargo test`，只跑靶向测试 21/21；故不判“通过”，留待后续轮次补跑后再判定。 |

## 已知限制

- 全量 `cargo test` 本轮未跑（只跑靶向测试）。
- 无数据库迁移、无新增端点、无新增依赖、无 UI 改动，视觉验收不适用。
- `from_env` 里 `compute_data_dir` 仍在数据库路径解析之前计算（空 `DATABASE_PATH` 时它先回落到 `data`，但随后解析分支即 `exit(2)`，服务不会带着空路径启动）。
