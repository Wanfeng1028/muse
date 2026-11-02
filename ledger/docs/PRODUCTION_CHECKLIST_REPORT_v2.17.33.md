# 生产对照报告 v2.17.33

## 范围
本轮仅在 get_settings 增加 LEDGER_DB 取值后校验（空串/纯空白抛 ValueError），其余配置项与服务行为不变。

## 对照表

| # | 对照项 | 实测结果 | 结论 |
| --- | --- | --- | --- |
| 1 | 版本一致性 | src/ledger/__init__.py、pyproject.toml、tests/test_version_consistency_v21715.py 的 EXPECTED_VERSION、CHANGELOG.md 顶条四处均为 2.17.33 | 通过 |
| 2 | LEDGER_DB 校验 | 空串/纯空白抛 ValueError，文案 LEDGER_DB 非法: '<原始值>'，不能为空 | 通过 |
| 3 | 默认值 | 未设置 LEDGER_DB 时默认 data/ledger.db 并拼到项目根目录 | 通过 |
| 4 | 透传行为 | 相对路径拼项目根目录、绝对路径原样透传；带空白填充的值原样透传不 trim | 通过 |
| 5 | 既有配置项 | host、port、log_level、base_currency 一字不动；无迁移、无新依赖、无新端点、无 UI 改动 | 通过 |
| 6 | 入口 fail-fast | create_app 与 lifespan 均在 init_db 之前调用 get_settings，空库配置下服务启动即失败 | 通过 |
| 7 | 冒烟清理 | 服务已停、18581 端口复查已关、冒烟库已删 | 通过 |

## 测试与冒烟证据
- 新测 tests/test_config_db_invalid.py 6 例全绿：空串/三空格/Tab 参数化 3 例抛错且文案含 LEDGER_DB 与原值 repr；缺省 data/ledger.db 拼项目根目录；相对路径锚定项目根目录；绝对路径原样透传。
- 靶向合跑：config 深测 + 新测 + host 旧测 + port 旧测 = 33 项全绿。
- ruff check 在 config.py 与新测试文件上全洁；新测试文件经 ruff format 一次格式化后复测仍 6/6 全绿。
- 真实服务冒烟（18581 端口、隔离库已删）：LEDGER_DB 空串与三空格启动均 exit 1，终行文案逐字相符；合法库起服后 /api/health 返回 status ok 且 version 2.17.33、/api/ready 返回 ready true。
- 全量 pytest 在文档同步前：1546 通过、1 失败（仅版本一致性测试，系 CHANGELOG 未同步所致）、1 跳过；文档同步后靶向复测：版本一致性 + 新测 + config 深测 = 21 项全绿。

## 已知限制
- 全量 pytest 在文档同步后未重跑，只跑了靶向 21 项。
- database.py 的 _resolve_db_path 未收紧：直接调 init_db/get_engine 仍把空串拼到项目根目录；FastAPI 入口会先经 get_settings 失败，但不经 get_settings 的直接数据库调用不受保护，留待后续轮次。
- 仅判空不 trim：带空白填充的 LEDGER_DB 原样透传，与 HOST 同款。
- 不做路径可写性与目录存在性校验。
- 无 UI 改动，视觉验收不适用。
- 结论：可发版。
