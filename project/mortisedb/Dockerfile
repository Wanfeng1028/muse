# 构建阶段：编译 Go 二进制
FROM golang:1.23-alpine AS build

WORKDIR /src

# 先复制依赖文件，利用缓存加速构建
COPY go.mod go.sum ./
RUN go mod download

# 再复制源码并静态编译
COPY . .
RUN CGO_ENABLED=0 go build -o /out/mortisedb ./cmd/mortisedb

# 运行阶段：仅包含运行时所需内容
FROM alpine:3.20

# 安装 CA 证书与时区数据
RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# 复制二进制与示例配置
COPY --from=build /out/mortisedb /app/mortisedb
COPY mortise.yaml.example /app/mortise.yaml.example

# 默认监听地址与数据库路径
ENV MORTISE_ADDR=:8421 \
    MORTISE_DB=/app/data/mortise.db

# 持久化数据与源码目录
VOLUME ["/app/data", "/app/sources"]

EXPOSE 8421

CMD ["/app/mortisedb", "serve"]
