# syntax=docker/dockerfile:1

# 构建阶段：编译 Go 二进制文件
FROM golang:1.27-bookworm AS build
WORKDIR /src

# 先复制依赖清单，利用缓存下载模块
COPY go.mod go.sum ./
RUN go mod download

# 复制源码并静态编译
COPY . .
RUN CGO_ENABLED=0 go build -o /sentinel .

# 运行阶段：使用精简镜像，仅包含二进制与运行所需环境
FROM gcr.io/distroless/static-debian12
WORKDIR /app
COPY --from=build /sentinel /app/sentinel

# 默认配置：数据库路径、监听地址与端口
ENV SENTINEL_DB=/app/data/sentinel.db \
    SENTINEL_HOST=0.0.0.0 \
    SENTINEL_PORT=8200

# 持久化数据目录并暴露服务端口
VOLUME ["/app/data"]
EXPOSE 8200

# 以非 shell 形式启动
ENTRYPOINT ["/app/sentinel"]
