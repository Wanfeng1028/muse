# 构建阶段：编译并运行测试（需联网，FetchContent 拉取 googletest）
FROM debian:12-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .

RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j$(nproc) \
    && ./build/docseek_tests

# 运行阶段：仅包含可执行文件
FROM debian:12-slim

COPY --from=build /src/build/docseek /usr/local/bin/docseek
# 词典必须跟镜像走：对应 resolveDictDir 的第二级定位
# （可执行文件 ../share/docseek/dict），缺了它 serve 启动即报错。
COPY --from=build /src/build/dict /usr/local/share/docseek/dict

ENTRYPOINT ["docseek"]
