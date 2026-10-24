# mini-os v1.11.0 发版对照报告（两步验证）

日期：2026-10-24

## 1. 可靠性

- [x] 通过：11个集成测试全过，覆盖锁定429、过期410、一次一码及非明文落库
- [x] 通过：迁移008列判存在且表用IF NOT EXISTS，老库启动自动升级
- [x] 通过：TOTP符合RFC 6238，9个单测通过官方向量
- [ ] 未通过：未做故障演练（杀进程/断网）
- [ ] 未通过：未做真实负载压测
- [ ] 未通过：v1.11.0 合入时全量套件红（tests/mig006_expiry_deep.rs 11 例：密码策略收紧后旧测试弱密码 pw-alice 注册返回 400 而非 201）；本轮已机械修复（7 处 pw-alice→pw-alice9）并重跑验证通过
- [ ] 未通过：v1.11.0 合入时另有 4 例迁移 fixture 失败（tests/mig006_expiry_deep.rs A 组：手写 legacy-005 fixture 只建了 shares 表，真实 005 时代库已有 users 表，008 的 ALTER TABLE users 报 no such table；属 fixture 未随迁移注册表同步，非产品迁移 bug）；本轮已修复（fixture 补建 users 表最小列集，a2 断言 7→8，a1 加 008 断言）并重跑验证通过
- [ ] 未通过：v1.11.0 合入时另有 2 例迁移版本硬编码断言失败（tests/migrate_deep.rs 两处断言写死"共 7 个版本"，008 加入后应为 8，上一轮只改了 failure_injection.rs 漏了此处）；本轮已改为从 MIGRATIONS 注册表派生并重跑验证通过
- [ ] 未通过：v1.11.0 合入时另有 1 例迁移版本硬编码断言失败（tests/migrate_versions_deep2.rs 的 applied_versions_returns_sorted_seven 写死 7 版本列表，008 加入后失败）；本轮已改为从 MIGRATIONS 注册表派生（测试改名 applied_versions_returns_sorted_all）并重跑验证通过

## 2. 安全

- [x] 通过：敏感操作需密码二次验证，challenge限5次，输入校验拒绝非法字符
- [x] 通过：TOTP密钥AES-256-GCM加密落库，备用码argon2哈希且一次一码
- [ ] 未通过：/api/auth/2fa无独立IP限流
- [ ] 未通过：主密钥轮换无在线迁移方案
- [ ] 未通过：.env.example未收录MINIOS_TOTP_MASTER_KEY变量

## 3. 性能

- [x] 通过：TOTP验证限前后1窗口，单次最多3次SHA1计算
- [x] 通过：备用码用argon2哈希存储，校验时逐个验证
- [ ] 未通过：未做真实负载压测

## 4. 可观测性

- [x] 通过：2FA相关8个计数器已进入/metrics端点
- [x] 通过：输出带request_id的结构化JSONL日志
- [ ] 未通过：已用备用码无归档策略

## 5. 部署

- [x] 通过：单二进制部署，重启即更新
- [x] 通过：沿用既有Docker Compose与Dockerfile
- [x] 通过：依赖走vendor离线补丁且Cargo.lock钉版本，构建可重复
- [ ] 未通过：.env.example未收录主密钥变量

## 6. 运维

- [x] 通过：OPERATIONS.md已新增2FA章节
- [x] 通过：沿用既有备份与恢复脚本
- [ ] 未通过：主密钥轮换无在线迁移方案

## 7. 兼容性

- [x] 通过：启用2FA后login返回202+challenge，未启用保持原流程
- [x] 通过：迁移008幂等，老库启动自动升级
- [ ] 未通过：E2E为HTTP集成测试，无浏览器端到端

## 8. 周期机制

- [x] 通过：TOTP时间步长30秒，允许前后1窗口
- [ ] 未通过：过期challenge无定时清理机制
- [ ] 未通过：SIGTERM排空与就绪探针沿用既有实现，未验证

## 未通过项排期

- /api/auth/2fa无独立IP限流：排期 v1.12
- 主密钥轮换无在线迁移方案：未排期
- .env.example未收录主密钥变量：未排期
- 已用备用码无归档策略：未排期
- 过期challenge无定时清理机制：未排期
- 未做故障演练（杀进程/断网）：未排期
- 未做真实负载压测：未排期
- E2E为HTTP集成测试，无浏览器端到端：未排期
- SIGTERM排空与就绪探针沿用既有实现，未验证：未排期
- tests/mig006_expiry_deep.rs 11 例失败（v1.11.0 密码策略回归）：本轮已修复（测试密码合规化为 pw-alice9），重跑 11/11 通过
- tests/mig006_expiry_deep.rs A 组 4 例 + tests/migrate_deep.rs 2 例（迁移 fixture/断言随版本漂移）：本轮已修复（fixture 同步/注册表派生），重跑验证通过
- tests/migrate_versions_deep2.rs 1 例（版本列表硬编码）：本轮已修复（注册表派生），重跑验证通过
