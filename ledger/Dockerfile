# syntax=docker/dockerfile:1

# ---------- 构建阶段 ----------
FROM python:3.14-slim AS build

WORKDIR /src

# 先复制依赖描述文件以利用缓存
COPY pyproject.toml README.md ./

# 复制源码
COPY src/ src/

# 安装项目及依赖到系统 Python 环境
RUN pip install --no-cache-dir .

# ---------- 运行阶段 ----------
FROM python:3.14-slim

WORKDIR /app

# 从构建阶段复用已安装的 Python 包
COPY --from=build /usr/local /usr/local

# 运行时配置
ENV LEDGER_DB=/app/data/ledger.db \
    LEDGER_HOST=0.0.0.0 \
    LEDGER_PORT=8100

# 数据持久化目录
VOLUME ["/app/data"]

# 服务端口
EXPOSE 8100

# 启动入口
CMD ["python", "-m", "ledger"]
