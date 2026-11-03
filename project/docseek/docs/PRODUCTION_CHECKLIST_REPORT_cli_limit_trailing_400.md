# docseek 发版对照报告：CLI search/locate --limit 尾随字符返回错误（2026-10-28）

1. 构建：通过。理由：本轮改动 src/main.cpp 后构建成功。
2. 实测：通过。理由：1 文档小库实测 11 项全过（search --limit 5x/5.0/1a、locate --limit 5x/2y、search --limit 0/-3/abc 均退出码 1 且 stderr 为“错误：--limit 参数无效”；search --limit 5、locate --limit 5、search 不带 limit 均退出码 0 且返回命中文档）。
3. 视觉验收：不适用。理由：无 UI 改动。
4. 全量回归：未通过。理由：全量 ctest 本轮未跑，下一轮补跑。
5. 部署：不适用。理由：无版本号变更、无 schema 变更，仅修复 CLI 参数校验逻辑。
6. 安全：通过。理由：CLI 参数解析层修复，无数据泄露或注入风险。
7. 可维护性：通过。理由：CLI search/locate --limit 改为 stoll 带 pos 整串判定，尾随字符以退出码 1 严格拒绝，其余参数分支未动。
