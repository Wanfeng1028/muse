# feedflow 项目 Makefile

# 虚拟环境路径
VENV := .venv
# 虚拟环境中的 Python 解释器
PY := $(VENV)/bin/python
# 虚拟环境中的 pip
PIP := $(VENV)/bin/pip

.PHONY: install test lint run fetch clean

# 创建虚拟环境并安装依赖
install:
	python3 -m venv $(VENV) && $(PIP) install -r requirements.txt

# 运行测试
test:
	$(PY) -m pytest -q

# 运行代码检查
lint:
	$(VENV)/bin/ruff check .

# 启动 feedflow 服务
run:
	$(PY) -m feedflow serve

# 抓取订阅内容
fetch:
	$(PY) -m feedflow fetch

# 清理虚拟环境与缓存文件
clean:
	rm -rf $(VENV) __pycache__ data/*.db* .pytest_cache .ruff_cache
