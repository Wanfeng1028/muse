# syntax=docker/dockerfile:1
#
# auth-service 镜像：多阶段构建（Maven 打包 → JRE 运行），与主服务 Dockerfile 同构。
# 构建上下文必须是 drama-factory/auth-service/ 目录本身。

# ---------- 阶段一：构建 ----------
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml ./
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B package -DskipTests

# ---------- 阶段二：运行 ----------
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/target/auth-service-*.jar /app/app.jar
VOLUME /app/data
EXPOSE 8082
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD wget -qO- http://localhost:8082/api/auth/oauth/providers || exit 1
# 注意：AUTH_JWT_SECRET 必须经环境变量传入，缺失则拒绝启动
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
