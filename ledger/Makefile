# ledger 项目 Makefile
# 约定：所有 Python 命令均通过项目内 .venv 执行，避免污染全局环境

.PHONY: install dev run test lint fmt clean backup restore deps-scan

# 创建虚拟环境并以可编辑模式安装项目及开发依赖
install:
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 启动开发服务器（热重载，监听 127.0.0.1:8100）
dev:
	.venv/bin/uvicorn ledger.main:app --reload --host 127.0.0.1 --port 8100

# 以模块方式直接运行应用（生产/本地运行入口）
run:
	.venv/bin/python -m ledger

# 运行测试套件
test:
	.venv/bin/pytest

# 静态代码检查
lint:
	.venv/bin/ruff check src tests

# 代码格式化
fmt:
	.venv/bin/ruff format src tests

# 清理虚拟环境、数据库文件与缓存
clean:
	rm -rf .venv data/*.db __pycache__

# 备份数据库（保留最近 7 个，可用 KEEP= 覆盖）
backup:
	.venv/bin/python -m ledger backup --keep $(or $(KEEP),7)

# 从备份恢复（必须指定 FILE= 路径）
restore:
	.venv/bin/python -m ledger restore $(FILE)

# 依赖扫描：过期依赖 + OSV 已知漏洞（每周 workflow 也会跑）
deps-scan:
	.venv/bin/python scripts/deps_scan.py

# 真实负载验证：仿真账单走真实 HTTP 全链路压测（默认 24 个月）
load-test:
	.venv/bin/python scripts/load_test.py

# 真实负载验证快速版（6 个月）
load-test-quick:
	.venv/bin/python scripts/load_test.py --quick

