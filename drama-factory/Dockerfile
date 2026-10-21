# syntax=docker/dockerfile:1
#
# 构建上下文（build context）必须是 drama-factory/ 目录本身：
#   cd drama-factory
#   docker build -t drama-factory .
#   # 或在 drama-factory/ 下使用 docker compose up -d --build
#
# 多阶段构建：
#   阶段一用 Maven 镜像离线拉依赖并打包（跳过测试以加速构建）
#   阶段二用 JRE 镜像运行，并安装 ffmpeg（剪辑成片必需）

# ---------- 阶段一：构建 ----------
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build

# 先只拷贝 pom.xml，利用 Docker 层缓存离线拉取依赖
COPY pom.xml ./
RUN mvn -B dependency:go-offline

# 再拷贝源码并打包（跳过测试：Docker 内跑测试太慢）
COPY src ./src
RUN mvn -B package -DskipTests

# ---------- 阶段二：运行 ----------
FROM eclipse-temurin:25-jre
WORKDIR /app

# 安装 ffmpeg（含 ffprobe），并清理 apt 缓存以减小镜像体积
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 拷贝构建产物为固定文件名 /app/app.jar
COPY --from=build /build/target/drama-factory-*.jar /app/app.jar

# 数据目录（H2 文件库、媒体、日志、设置）挂载点
VOLUME /app/data

# 默认端口
EXPOSE 8081

# 健康检查：调用 /api/health，返回 200 即就绪。
# jre 镜像通常不带 curl，这里用 busybox wget（eclipse-temurin 基础镜像一般自带）。
# 若你的环境没有 wget，可退化为：HEALTHCHECK CMD-SHELL true
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD wget -qO- http://localhost:8081/api/health || exit 1

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
