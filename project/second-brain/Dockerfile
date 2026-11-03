# 构建阶段：编译 Go 二进制
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/second-brain ./cmd/server

# 运行阶段：最小化镜像
FROM alpine:3.20
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=build /out/second-brain /app/second-brain
ENV SB_ADDR=:8080 SB_DB=/app/data/second-brain.db
VOLUME ["/app/data"]
EXPOSE 8080
CMD ["/app/second-brain"]
