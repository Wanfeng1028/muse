# PRODUCTION CHECKLIST REPORT v1.4

## 0. 结论先行
- 发版结论：**通过**。核心链路全绿：magic-bytes 嗅探、可执行上传 415 拒绝、mime 优先级、前端上传队列失败继续，均按契约落地。
- 已知限制：仅按魔数拒绝已知可执行类型，未做病毒扫描；zip 内嵌可执行不检测；不支持断点续传（v1.1 已知限制延续）。

## 1. 版本信息与范围
- 版本：v1.4「安全上传」里程碑，2026-10-16。
- 范围一句话：后端引入 sniff_mime magic-bytes 嗅探，命中可执行上传直接 415 拒绝不入库；mime 取值优先级改为嗅探结果 > 客户端 Content-Type 头 > 扩展名猜测；前端上传队列单文件失败不再中断整队并给出失败汇总。无新增依赖。
- 沿用项：JSONL 日志与 request_id、/metrics、健康/就绪、优雅关闭、docker-compose、backup/restore CLI 与脚本。
- Checklist：
  - [通过] 版本范围与设计契约一致，未声明契约外特性。
  - [通过] 未引入新依赖。

## 2. 可靠性
- 测试金字塔数字（2026-10-16 验收实测）：`cargo test` **73/73 全过**——lib 15、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、share_test 6、upload_security_test 8（新增）；`cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过。
- 新增 upload_security_test 8 例覆盖 magic-bytes 嗅探与可执行文件 415 拒绝。
- 前端上传队列：单个文件失败不再中断，失败记名后继续下一个。
- 真服务冒烟（127.0.0.1:18091）：注册 200 → 上传文本 201 → 下载 200 且字节一致 → MZ 可执行上传 415 → bob 跨用户下载 404 → 未登录下载 401。
- 健康与生命周期：GET /api/health、GET /api/readyz、优雅关闭沿用既有实现。
- Checklist：
  - [通过] cargo test 73/73 全过，新增 upload_security_test 8 例。
  - [通过] cargo clippy --all-targets 零警告。
  - [通过] cargo fmt --check 通过。
  - [通过] 真服务冒烟全链路通过。
  - [通过] 健康/就绪/优雅关闭沿用。

## 3. 可观测性
- 沿用：JSONL 日志与 request_id 贯穿请求链路。
- 沿用：/metrics 端点与既有指标。
- 排障：结合 request_id 定位上传请求的嗅探结果与 415 拒绝路径。
- Checklist：
  - [通过] JSONL + request_id 沿用。
  - [通过] /metrics 沿用。
  - [通过] 排障路径可由 request_id 定位上传拒绝。

## 4. 数据与状态
- 备份/恢复：单 SQLite 文件，现有 backup/restore CLI 与脚本整库备份，v1.4 无表结构变更。
- 上传拒绝语义：命中可执行 magic-bytes 的上传返回 415，文件不入库，无残留状态。
- mime 取值优先级：嗅探结果 > 客户端 Content-Type 头 > 扩展名猜测。
- Checklist：
  - [通过] 备份沿用，无表结构变更。
  - [通过] 可执行上传 415 不入库，无残留。
  - [通过] mime 优先级按契约落地。

## 5. 部署与运维
- 沿用：docker-compose 部署方式，无新增依赖。
- 沿用：OPERATIONS.md 既有内容。
- Checklist：
  - [通过] docker-compose 沿用，无部署方式变更。
  - [通过] 无新增依赖需安装。

## 6. 安全与健壮性
- 嗅探类型：PE/MZ、ELF、Mach-O/fat binary、MSI/OLE 复合文档、shebang 脚本。
- 命中可执行上传：返回 415 `{"error": "可执行文件不允许上传"}`，文件不入库。
- mime 取值优先级：嗅探结果 > 客户端 Content-Type 头 > 扩展名猜测。
- 前端上传队列：单个文件失败不再中断，失败记名后继续下一个，结束后给出失败汇总（最多列 3 个名）。
- 未做（已知限制）：仅按魔数拒绝已知可执行类型，未做病毒扫描；zip 内嵌可执行不检测；不支持断点续传。
- Checklist：
  - [通过] 五类 magic-bytes 嗅探按契约实现。
  - [通过] 可执行上传 415 且不入库。
  - [通过] mime 优先级按契约落地。
  - [通过] 前端队列失败不中断并有汇总。
  - [未通过] 病毒扫描未实现 → 已知限制。
  - [未通过] zip 内嵌可执行检测未实现 → 已知限制。
  - [不适用] 断点续传：v1.1 已知限制延续。

## 7. 可维护性
- sniff_mime 模块边界清晰，承载 magic-bytes 嗅探。
- API 契约表：上传行已补充"可执行文件 415 拒绝"。
- CHANGELOG v1.4 记录本里程碑。
- 技术债记录：见已知限制与第 8 节。
- Checklist：
  - [通过] sniff_mime 模块边界清晰。
  - [通过] API 契约表与实现一致。
  - [通过] CHANGELOG v1.4 已记录。
  - [通过] 技术债已记录。

## 8. 发版结论
- 结论：**通过**。核心安全上传链路满足设计契约，可发版；已知限制需在后续版本收敛。
- 已知限制清单：
  - 仅按魔数拒绝已知可执行类型，未做病毒扫描。
  - zip 内嵌可执行不检测。
  - 不支持断点续传（v1.1 已知限制延续）。
- Checklist：
  - [通过] 结论为通过并附已知限制。
  - [通过] 未通过项均声明为已知限制。

## 9. 视觉验收（2026-10-16，真服务 + 截图，亲眼检查）
- `docs/screenshots/v14-files-list.png`：文件管理器真实文件列表 + 下载按钮。
- `docs/screenshots/v14-upload-415.png`：415 失败汇总条"上传完成：成功 0 个，失败 1 个（病毒.exe）"。
- Checklist：
  - [通过] 文件列表与下载按钮渲染正常。
  - [通过] 415 失败汇总条按契约显示。
