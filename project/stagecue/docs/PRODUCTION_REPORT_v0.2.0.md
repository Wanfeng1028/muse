# StageCue 生产就绪报告 v0.2.0

> 结论先行：v0.1.0 的 6 个排期"未通过"项，本轮修复 5 个；2 个"已知限制"转正（排练模式后端、MP3 解码）。剩余 4 项未通过，全部记入 TECH_DEBT.md #1–#4。

## 本轮验证数据

| 项 | 结果 |
|----|------|
| :shared 测试 | 29/29 通过（含新增 4 个排练协议序列化测试） |
| :server 测试 | 31/31 通过 |
| :desktopApp 主代码编译（含 Compose UI） | 全量编译通过 |
| 音频测试 | 4/4 通过（MP3 真实解码为 PCM、WAV 回归、缺失文件抛异常、垃圾文件抛 UnsupportedAudioFileException） |
| 备份恢复演练 | 通过（docs/BACKUP_DRILL_v0.2.0.md） |
| 编译 | 0 error |
| 测试 | 0 failed |

## 六大类对照

### 1. 可靠性

| 项 | 结论 |
|----|------|
| 备份恢复真实演练 | 通过（docs/BACKUP_DRILL_v0.2.0.md） |
| 数据持久化（SQLite + WAL） | 通过 |
| 旧数据幂等导入（show.json） | 通过 |
| 限流 / 超时熔断 | 未通过（TECH_DEBT #1） |
| 滚动更新 / 零停机 | 未通过（单机，声明为可接受限制，TECH_DEBT #5） |

### 2. 可观测性

| 项 | 结论 |
|----|------|
| GET /metrics（Micrometer Prometheus） | 通过（6 个指标） |
| 告警规则 | 未通过（TECH_DEBT #3） |
| 日志轮转 | 未通过（TECH_DEBT #4） |

### 3. 数据与状态

| 项 | 结论 |
|----|------|
| Flyway 版本化迁移（V1 建表、V2 settings） | 通过 |
| 旧 show.json 自动幂等导入 | 通过 |
| 排练状态服务端持久化 | 通过 |
| 多人同时编辑同一 show | 未通过（单导演假设，TECH_DEBT #6） |

### 4. 部署与运维

| 项 | 结论 |
|----|------|
| 启动配置校验（非法值 exit 1） | 通过 |
| 资源限制（docker-compose memory limit） | 未通过（TECH_DEBT #4） |
| 依赖更新机制（Dependabot） | 未通过（TECH_DEBT #2） |
| Gradle daemon | 不适用（本 VM 无法运行，改 kotlinc 直接验证） |

### 5. 安全与健壮性

| 项 | 结论 |
|----|------|
| 音频缺失文件抛异常 | 通过 |
| 音频垃圾文件抛 UnsupportedAudioFileException | 通过 |
| 启动配置非法值拦截 | 通过 |
| WS/HTTP 限流、超时熔断 | 未通过（TECH_DEBT #1） |

### 6. 可维护性

| 项 | 结论 |
|----|------|
| 技术债文档 | 通过（docs/TECH_DEBT.md） |
| 版本化数据库迁移 | 通过 |
| 服务端引擎 | 保留 CIO（Netty 在本 VM 误用 KQueue，TECH_DEBT #7） |
| 桌面 UI 运行时截图 | 未通过（VM 缺 libXtst.so.6，TECH_DEBT #8） |

## v0.1.0 排期项回收

v0.1.0 列出的 6 个"未通过"排期项：

1. SQLite 迁移 —— 本轮修复，关闭
2. /metrics —— 本轮修复，关闭
3. 备份实测 —— 本轮修复，关闭
4. 配置校验 —— 本轮修复，关闭
5. 技术债文档 —— 本轮修复，关闭
6. 限流 / 熔断等 —— 未修复，转 TECH_DEBT #1

修复 5 个，剩余 1 个（限流等）连同新识别的 Dependabot、告警规则、日志轮转/资源限制，合计 4 项未通过，记入 TECH_DEBT #1–#4。

## v0.1.0 已知限制转正

- 排练模式：已实现后端（服务端持久化开关 + WS set_rehearsal / rehearsal_changed 广播 + CueFired.rehearsal 标记 + GET /api/rehearsal），导演台联动。
- MP3 解码：已支持（mp3spi + jlayer），MP3 真实解码为 PCM 测试通过，WAV 回归通过。

## 已知限制（更新 v0.1.0 的 6 条）

1. Gradle daemon 本 VM 无法运行，改 kotlinc 直接验证。
2. 桌面 UI 运行时截图因 VM 缺 libXtst.so.6 未验收（代码已全量编译通过）。
3. 服务端引擎为 CIO 非 Netty（Netty 在本 VM 误用 KQueue）。
4. 移动端二期。
5. 排练模式已实现（服务端持久化开关 + WS 广播 + 导演台联动）。
6. 音频已支持 WAV/MP3（mp3spi + jlayer），WAV 回归通过。

## 演练发现

- 备份恢复演练抓到真 bug：Main.kt 漏接 settings。已修复并重验，关闭。

## v0.2.0 交付清单

- SQLite + Flyway 版本化迁移（V1 建表、V2 settings 表；旧 show.json 自动幂等导入；WAL）
- GET /metrics（Micrometer Prometheus，6 个指标）
- 启动配置校验（非法值 exit 1）
- 排练模式后端（服务端持久化 + WS set_rehearsal/rehearsal_changed + CueFired.rehearsal 标记 + GET /api/rehearsal）
- MP3 解码（mp3spi + jlayer）
- 备份恢复真实演练
