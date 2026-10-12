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
