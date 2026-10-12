# 构建阶段：使用 Rust 官方镜像编译 release 版本
FROM rust:1.83-slim AS build
WORKDIR /src

# 先复制清单文件并创建占位源文件，以便缓存依赖下载与编译层
COPY Cargo.toml ./
RUN mkdir src && echo 'fn main() {}' > src/main.rs
RUN cargo build --release

# 复制真实源码与静态资源，重新构建最终二进制
COPY src ./src
COPY static ./static
RUN cargo build --release

# 运行阶段：使用精简 Debian 镜像，仅保留运行所需内容
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# 复制编译产物与静态资源
COPY --from=build /src/target/release/mini-os /app/mini-os
COPY --from=build /src/static /app/static

# 运行环境变量
ENV PORT=8090 DATABASE_PATH=/app/data/mini-os.db STATIC_DIR=/app/static

# 数据持久化与端口暴露
VOLUME ["/app/data"]
EXPOSE 8090

CMD ["/app/mini-os"]
