# 项目登记册

## kaoyan-os「考研指挥舱」

**定位**：全栈考研复习管理系统，服务考研备考全流程。

**技术栈**：pnpm workspace monorepo——后端 apps/server（Fastify 5 + TypeScript + SQLite，数据库为 Node 内置 node:sqlite）、前端 apps/web（Vite 6 + React 18 + TypeScript + React Router）、共享层 packages/shared（跨端类型与科目常量）。

**功能模块**：

1. 复习计划排程
2. 番茄专注计时
3. 错题本
4. 单词 SRS（SM-2 简化算法）
5. 真题计时与得分统计
6. 仪表盘（初试倒计时与全局概览）

**状态**：工程化 v1（2026-10-13 完成全栈重构，后端 API 与前端构建、集成测试均已跑通）。

**里程碑记录**：

- 里程碑 1（2026-10-13）：静态单页版落地（localStorage 存储），同日被工程化重构取代，仅作历史记录
- 工程化重构 v1（2026-10-13）：前后端分离、SQLite 持久化、vitest 集成测试、GitHub Actions CI、Dockerfile

**后续计划**：

- 数据导入/导出
- 考研核心 500 词词库扩充
- 周报视图
- 深色模式

## second-brain「第二大脑」

**定位**：个人知识库系统，支持笔记、标签、搜索、双链与知识图谱，构建可生长的个人知识网络。

**技术栈**：Go 1.23 单二进制；标准库 net/http 提供 HTTP 服务，modernc.org/sqlite 作为纯 Go SQLite 驱动；go:embed 内嵌 Web UI 静态资源；go test 覆盖单元测试与集成测试；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 second-brain/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 笔记 CRUD
2. 标签体系
3. 全文搜索（相关性排序）
4. [[双链]]与知识图谱
5. Markdown 渲染与预览
6. 统计概览

**状态**：工程化 v1（2026-10-13 完成，构建、vet、全量测试与真实服务冒烟均已跑通）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：单二进制架构落地，内嵌 Web UI、SQLite 持久化、双链与图谱能力、CI 与多阶段构建就绪

**后续计划**：

- 数据导入/导出
- 附件支持
- 反向链接面板
- PWA

## drama-factory「AI 短剧工坊」

**定位**：短剧生产管理与剧本生成系统，服务短剧内容团队的立项到剧本初稿全流程。

**技术栈**：Java 21 + Spring Boot 3.3.5 + Maven；Spring Data JPA + H2 文件库（可平滑切换 PostgreSQL/MySQL）；企业级分层 controller / service / repository / model / dto；内置 Web 控制台由 Spring 静态托管；JUnit 5 + MockMvc 集成测试；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 drama-factory/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 短剧项目管理
2. 剧集管理
3. 角色管理
4. 场景管理
5. 基于大纲的四场式剧本自动生成（开场钩子 / 冲突升级 / 反转 / 高潮收尾，每场带英文视频生成提示词）
6. 全局统计

**状态**：工程化 v1（2026-10-13 完成，mvn test 全量 4 例通过、可执行 jar 打包成功、真实服务冒烟全过）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Spring Boot 分层架构落地，项目/剧集/角色/场景 CRUD、四场式剧本生成、Web 控制台、CI 与多阶段 Dockerfile 就绪

**后续计划**：

- 接入真实大模型生成剧本
- 对接视频生成管线
- 审核流状态机
- 多用户与权限

## mini-os「网页操作系统」

**定位**：浏览器里的桌面操作系统，后端提供虚拟文件系统、设置持久化与应用注册表，前端实现可拖拽多窗口桌面。

**技术栈**：Rust + Axum 0.7（含 WebSocket）+ Tokio + rusqlite 0.32（bundled SQLite）；前端原生 HTML/CSS/JS（无框架）；cargo test 集成测试 8 例、cargo clippy 零警告；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 mini-os/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 虚拟文件系统（文件夹/文件 CRUD，SQLite 持久化，种子数据 Desktop/Documents/welcome.txt/notes.txt）
2. 应用注册表（文件管理器、文本编辑器、终端、设置、关于 5 个内置应用）
3. 可拖拽多窗口桌面 + 任务栏 + 开始菜单 + 时钟
4. 主题/壁纸设置持久化
5. WebSocket（连接先发 hello，文本消息 echo 回显）
6. 统计（文件/文件夹数、字节数）

**状态**：工程化 v1（2026-10-13 完成，cargo test 8 例全过、clippy 零警告、release 单二进制真实服务冒烟全过）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Axum + rusqlite 后端落地，虚拟文件系统 API、5 应用桌面前端、WebSocket 协议、CI 与多阶段 Dockerfile 就绪

**后续计划**：

- 文件上传/下载
- 多用户与权限
- 应用商店（插件化）

## ledger「钱迹 · 个人财务管家」

**定位**：个人财务管理系统，覆盖多账户记账、月度预算、统计分析与数据导入导出的完整记账流程。

**技术栈**：Python 3.11+ + FastAPI + SQLAlchemy 2.0（aiosqlite 异步）+ SQLite 单文件库；Jinja2 SSR Web UI（图表为服务端渲染内联 SVG，零外部依赖）；pytest + httpx（34 例测试）、ruff 检查与格式化；Dockerfile 单阶段构建；GitHub Actions CI 暂置于 ledger/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 多账户管理（余额按收支/转账自动汇总）
2. 交易记账（收入/支出/转账，金额统一用「分」整数存储）
3. 分类体系（seed 预置 18 个常用分类）
4. 月度预算与执行进度/超支预警
5. 统计分析（月度汇总、12 个月趋势、分类占比、净资产）
6. CSV 导入/导出
7. 周期性账单与未来 30 天到期提醒
8. Web UI（仪表盘/交易/账户/分类/预算/周期账单/导入导出 7 页）

**状态**：工程化 v1（2026-10-13 完成，pytest 34 例全过、ruff 全洁、真实服务 7 页面与核心业务流冒烟均已跑通）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：FastAPI 分层架构落地，账户/交易/分类/预算/统计/导入导出/周期账单全模块、Jinja2 SSR 前端、CI 与 Dockerfile 就绪

**后续计划**：

- 多币种与汇率
- 账单图片 OCR 录入
- 移动端适配

## sentinel「哨兵 Sentinel · 站点可用性监控」

**定位**：站点与服务可用性监控系统，覆盖监控目标管理、定时检查、停机事件与可用率统计的完整运维流程。

**技术栈**：Go 1.23 单二进制；标准库 net/http 提供 HTTP 服务，modernc.org/sqlite 作为纯 Go SQLite 驱动；go:embed 内嵌 Web UI 静态资源；go test 覆盖存储/检查器/HTTP 层测试；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 sentinel/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 监控目标管理（HTTP(S)/TCP 双协议、期望状态码、超时、检查间隔、启用开关）
2. 定时检查调度器（每 5 秒轮询，按目标间隔并发检查）
3. 检查记录（状态码、延迟毫秒、HTTPS 证书剩余天数）
4. 状态翻转自动生成停机事件（down 创建、recovered 关闭并计算时长）
5. Webhook 告警通知（目标级或全局，状态翻转时推送）
6. 统计分析（可用率、平均延迟、检查总数、停机次数）
7. Web UI（仪表盘/监控管理/事件 三页）

**状态**：工程化 v1（2026-10-13 完成，构建、vet、gofmt、全量测试与真实服务冒烟均已跑通；冒烟验证了 down→incident→recovered→incident 关闭的完整事件流）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：单二进制架构落地，检查器/调度器/事件流、内嵌 Web UI、CI 与多阶段构建就绪

**后续计划**：

- 多渠道告警（邮件/短信/企业微信）
- 公开状态页
- 分布式探针
