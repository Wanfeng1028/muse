# 构建阶段：使用 Maven 编译并打包 Spring Boot 应用
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
# 先复制 pom.xml，利用缓存加速依赖下载
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
# 再复制源码并执行打包
COPY src ./src
RUN mvn -q -B package -DskipTests

# 运行阶段：仅包含 JRE，减小镜像体积
FROM eclipse-temurin:21-jre
WORKDIR /app
# 剪辑成片与 mock 视频生成需要 ffmpeg；compose 健康检查需要 curl
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/target/drama-factory-1.0.0.jar /app/app.jar
ENV PORT=8081
VOLUME ["/app/data"]
EXPOSE 8081
ENTRYPOINT ["java","-jar","/app/app.jar"]
