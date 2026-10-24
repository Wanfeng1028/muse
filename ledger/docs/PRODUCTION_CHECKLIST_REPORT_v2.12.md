# 生产检查对照报告 v2.12.0
（版本 v2.12.0，日期 2026-10-24，范围一句话：关闭 v2.11.1 遗留「真实负载验证：待执行」，交付可复现的负载压测工具链）

## 可靠性
- 真实负载验证：通过。24 个月 2664 笔仿真账单走真实 HTTP 全链路（上传→确认→自动匹配→去重→并发），阈值（确认 30s/300条、零 5xx、去重精确）全通过。详见 docs/LOAD_TEST_REPORT.md。
- 失败注入：不适用（本轮未新增；v2.1 既有 4 例仍全过）。

## 可观测性
- 不适用（本轮未动指标；load_test.py 自带分阶段计时与 JSON 报告）。

## 数据
- 压测库隔离：通过。harness 用独立 LEDGER_DB（data/loadtest-tmp/），不污染开发/演示库。

## 部署运维
- 生产环境部署验证：仍待执行（v2.11.1 遗留；本机无生产环境，诚实保留）。
- 新增 make load-test / make load-test-quick 快捷目标；docs/LOAD_TEST.md 方法论文档。

## 安全
- 不适用。

## 可维护性
- 测试覆盖率：通过。tests/test_load_statement.py 4 例（上传确认/重传去重/自动匹配率/命中抽查/确认耗时）全过；全量 1393 通过、1 跳过（2 失败为干净树既存 wlfl_t14/t15，非本轮引入）。
- 文档一致性：通过。CHANGELOG v2.12.0、docs/LOAD_TEST.md、docs/LOAD_TEST_REPORT.md、Makefile 目标齐备。
- ruff check + format 全洁。

## 诚实声明
- loadgen.py 由 s193 以 assembly 式 prompt 一次生成（智谱同文件两连败：首版散文+截断、次版纯分析）；load_test.py 拆 4 个微批（A2a1/A2a2/A2b + 1 个手工锚定修复）完成；智谱 272s 传输墙共触发 4 次（A/B/A2/A2a 整批）。
- 压测跑通前修 harness 侧真 bug 4 个（双重 BOM / PIPE 死锁 / httpx NO_PROXY 解析 InvalidURL / 去重探针断言错位），产品代码零改动。
- 测试侧 3 处机械修复（merch["counterparty"]→["name"]、auto_count 改从 confirm 响应读、BOM 编码），已披露。
