# 生产对照报告 v2.17.31

范围一句话：本轮仅收紧 src/ledger/config.py 的 get_settings 对 LEDGER_PORT 非整数时抛 ValueError 替代静默回退默认端口 8100，并同步升版 2.17.31 与相关测试，其余逻辑一字未动。

## 对照表

- 可靠性：通过。非整数端口启动即失败，避免静默用错端口导致的连不上却难定位；合法整数透传不变，负数与超大整数仍透传。
- 可观测性：通过。抛错文案逐字为“LEDGER_PORT 非法: '<原始值>'，必须为整数”，含原始值便于定位；真实服务冒烟已逐字核对终行文案。
- 数据与状态：不适用。本轮不触碰 db_path、账户与迁移，数据路径零改动。
- 部署运维：通过。代码与 docs/OPERATIONS.md 第 64 行“非整数时启动失败”既有表述对齐，口径一致；冒烟验证非法端口启动 exit 1。
- 安全与健壮性：通过。输入校验收紧，非法值不再静默通过；负数与超大整数本轮不收紧，属已知边界。
- 可维护性：通过。与同文件日志级别、币种非法即抛错口径一致；ruff check 与 ruff format 在 src/ledger/config.py 与新测试文件上全洁，深测文件既存漂移未动。
- 发版前对照：通过。四处版本号统一为 2.17.31，CHANGELOG 顶条更新，冒烟通过。

## 测试与冒烟证据

- 新文件 tests/test_config_port_invalid.py：6 例全绿（非数字参数化 4 例：not-a-number、8100x、空串、8100.5 均抛错且文案含 LEDGER_PORT 与原始值；8200 透传；带空白 8200 透传）。
- tests/test_config_deep.py 旧用例第三段由回退断言改为抛错断言；新测 6 + 深测 14 = 20 项全绿；再加 test_logging 与 test_currencies 相关用例合计 48 项全绿。
- 静态检查：ruff check 与 ruff format 在 src/ledger/config.py 与新测试文件上全洁；test_config_deep.py 既存问题（httpx 未用导入、导入排序、约 271 行处格式漂移）均非本轮改动行，为保持 diff 最小不扩范围修复。
- 真实服务冒烟（18555 端口、隔离库）：LEDGER_PORT=not-a-number 启动 exit 1，终行文案逐字为 LEDGER_PORT 非法: 'not-a-number'，必须为整数；合法端口服务 health 返回 2.17.30（冒烟在升版前做，属预期）、建账户成功。冒烟后服务已停、端口复查已关、冒烟库已删。收尾注意：nohup 包装进程 PID 与实际监听进程 PID 不同，须按端口查到的监听 PID 定向 kill（已处理）。

## 已知限制

- 全量 pytest 本轮未跑，仅覆盖上述新测与深测、test_logging、test_currencies 相关用例。
- 生产环境部署验证无本地生产环境，沿用此前诚实保留。

## 结论

可发版。
