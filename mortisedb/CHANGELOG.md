# 更新日志

本文件记录 MortiseDB 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

## [0.1.0] - 2026-10-13

首个公开版本。MortiseDB 是一个面向多数据源的同步与视图中间层，本版本奠定了连接、同步、冲突处理、视图、调度与操作界面的完整基础能力。

### 新增

#### 连接器
- 新增 4 种数据源连接器：
  - **MySQL 连接器**：支持库表结构发现、全量与增量读取。
  - **PostgreSQL 连接器**：支持 schema 隔离与逻辑复制位点读取。
  - **SQLite 连接器**：支持本地文件库接入，适用于边缘与嵌入式场景。
  - **REST API 连接器**：支持基于 HTTP 的 JSON 数据源接入，可配置分页与鉴权。
- 连接器统一抽象接口，支持连接测试、字段类型映射与元数据探查。
- 连接配置支持环境变量与密钥引用，避免凭据明文落盘。

#### 增量同步
- 新增增量同步能力，基于水位线（watermark）记录同步位点。
- 支持按时间戳、自增主键与自定义游标字段进行增量识别。
- 支持同步位点持久化与断点续传，任务中断后可从中断处恢复。
- 支持全量初始化 + 增量追平的组合同步模式。

#### 冲突策略
- 新增可配置的冲突处理策略：
  - `source-wins`：以数据源为准覆盖目标。
  - `target-wins`：保留目标已有数据。
  - `latest-wins`：按时间戳取较新记录。
  - `manual`：冲突记录进入待处理队列，由人工裁决。
- 冲突事件可记录明细，包含冲突字段、双方取值与最终决策。

#### 视图
- 新增视图能力，可将多个数据源的表映射为统一逻辑视图。
- 支持字段重命名、类型转换、字段裁剪与简单表达式派生列。
- 支持视图级查询接口，屏蔽底层数据源差异。
- 视图定义支持版本化管理与变更校验。

#### 调度
- 新增任务调度模块，支持 Cron 表达式与固定间隔两种触发方式。
- 支持任务依赖编排，可配置前置任务成功后触发。
- 支持并发度控制、失败重试与超时中断。
- 提供调度执行历史与运行状态查询。

#### Web UI
- 新增 Web 管理界面，覆盖连接管理、同步任务、视图配置、调度计划与运行日志。
- 提供任务运行状态看板与失败任务告警提示。
- 支持冲突待处理队列的可视化查看与人工裁决操作。
- 界面支持简体中文。

#### CLI
- 新增命令行工具 `mortise`，覆盖全部核心能力，命令如下：
  - `mortise init`：初始化配置目录与默认配置文件。
  - `mortise connector list`：列出已注册的连接器类型。
  - `mortise connector test`：测试指定连接是否可用。
  - `mortise source add|list|remove`：管理数据源连接。
  - `mortise sync create|list|run|status`：创建、查看、执行同步任务并查询状态。
  - `mortise sync resume`：从上次位点恢复增量同步。
  - `mortise conflict list|resolve`：查看冲突记录并执行裁决。
  - `mortise view create|list|query`：创建、查看与查询视图。
  - `mortise schedule add|list|enable|disable`：管理调度计划。
  - `mortise serve`：启动 Web UI 与后台调度服务。
  - `mortise version`：输出版本信息。
- CLI 支持 `--config` 指定配置文件，支持 `--json` 输出便于脚本集成。

### 说明

- 本版本为 0.x 系列，配置结构与 CLI 参数在 1.0 之前可能发生不兼容变更。
- 增量同步依赖数据源具备可靠的游标字段，若源表无可用游标，请使用全量同步模式。

[未发布]: https://example.com/mortisedb/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/mortisedb/releases/tag/v0.1.0
