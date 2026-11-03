# 生产对照报告 v2.17.32

## 范围
本轮仅在 `get_settings` 增加 `LEDGER_HOST` 取值后校验（空串/纯空白抛 `ValueError`），其余配置项与服务行为不变。

## 对照表

| # | 对照项 | 实测结果 | 结论 |
| --- | --- | --- | --- |
| 1 | 版本一致性 | `src/ledger/__init__.py`、`pyproject.toml`、`tests/test_version_consistency_v21715.py` 的 `EXPECTED_VERSION`、`CHANGELOG.md` 顶条四处均为 2.17.32 | 通过 |
| 2 | LEDGER_HOST 校验 | 空串/纯空白抛 `ValueError`，文案 `LEDGER_HOST 非法: '<原始值>'，不能为空` | 通过 |
| 3 | 默认值 | 未设置 `LEDGER_HOST` 时默认 `127.0.0.1` | 通过 |
| 4 | 透传行为 | `0.0.0.0`、`localhost`、带空白填充的 `127.0.0.1` 原样透传不 trim | 通过 |
| 5 | 格式校验 | 不做 IP/域名格式校验 | 通过 |
| 6 | 既有配置项 | `db_path`、`port`、`log_level`、`base_currency` 一字不动；无迁移、无新依赖、无新端点、无 UI 改动 | 通过 |
| 7 | 冒烟清理 | 服务已停、18571 端口复查已关、冒烟库已删 | 通过 |

## 测试与冒烟证据
- 新测 `tests/test_config_host_invalid.py` 7 例全绿：空串/三空格/Tab 参数化 3 例抛错且文案含 `LEDGER_HOST` 与原值 repr；缺省 `127.0.0.1`；`0.0.0.0` 与 `localhost` 透传；带空白填充原样透传。
- 靶向合跑：新测 7 + port 旧测 + config 深测 14 = 27 项全绿。
- `ruff check` 与 `ruff format` 在 `config.py` 与新测试文件上全洁（import 分组经 `ruff --fix` 修正）。
- 真实服务冒烟（18571 端口、隔离库）：`LEDGER_HOST` 空串与三空格启动均 exit 1，终行文案逐字相符；合法 host 起服后 `/api/health` 返回 `status ok` 且 `version 2.17.31`（冒烟在升版前做，属预期）、`/api/ready` 返回 `ready true`。

## 已知限制
- 全量 pytest 未跑。
- 冒烟在升版前做，`/api/health` 报 `version 2.17.31` 属预期。
- 仅判空不 trim：带空白填充的值原样透传。
- 不做 IP/域名格式校验。
- 负数端口等既有边界本轮不动。
- 结论：可发版。
