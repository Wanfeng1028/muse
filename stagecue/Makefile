# 舞监台 StageCue —— 构建与运行入口
# 使用前确保工具链位于 ~/workspace/toolchains 下

SHELL := /bin/bash

TOOLCHAIN := $(HOME)/workspace/toolchains
JDK_HOME  := $(TOOLCHAIN)/jdk
KOTLIN_BIN := $(TOOLCHAIN)/kotlin/bin
GRADLE_BIN := $(TOOLCHAIN)/gradle/bin
JDK_BIN    := $(JDK_HOME)/bin

# 统一的工具链环境
export JAVA_HOME := $(JDK_HOME)
export PATH := $(JDK_BIN):$(KOTLIN_BIN):$(GRADLE_BIN):$(PATH)

GRADLE := gradle

.PHONY: build test run-server run-desktop clean

# 构建全部模块
build:
	$(GRADLE) build

# 运行所有 JVM 测试
test:
	$(GRADLE) test

# 启动服务端
run-server:
	$(GRADLE) :server:run

# 启动桌面端
run-desktop:
	$(GRADLE) :desktopApp:run

# 清理构建产物
clean:
	$(GRADLE) clean
