# 构建阶段
FROM golang:1.27-bookworm AS builder

WORKDIR /src

# 先复制 go.mod / go.sum，最大化利用缓存
COPY go.mod go.sum ./
RUN go mod download

# 复制源码并编译
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/linkshort ./cmd/linkshort

# 运行阶段
FROM debian:bookworm-slim

# 非 root 用户
RUN useradd --system --create-home --uid 10001 linkshort

ENV LINKSHORT_DB=/data/linkshort.db
VOLUME ["/data"]
WORKDIR /home/linkshort

COPY --from=builder /out/linkshort /usr/local/bin/linkshort

USER linkshort

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/linkshort"]
