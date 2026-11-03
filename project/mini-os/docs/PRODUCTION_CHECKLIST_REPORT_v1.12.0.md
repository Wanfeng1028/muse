mini-os v1.12.0 发版对照报告

通过项：
测试金字塔：新测 3/3 全绿（sweep 只删过期行、中间件第 6 次 429 带 Retry-After 与“过于频繁”、parse 默认值 1/5 与非法值点名变量），受影响套件 128/128 全绿（lib 76、config_deep 10、lib_deep 11、ratelimit_deep 12、share_ratelimit_test 8、ratelimit_test 8、twofa_v112_test 3），既有 twofa_test 修复后 11/11 全绿（123.15 秒），理由为全量回归通过。
健康/就绪探针：/api/health 返回 {"status":"ok","version":"1.12.0"}，readyz 沿用既有实现未改，理由为探针与版本符合预期。
配置非法值 fail-fast：MINIOS_2FA_RPS/BURST 非法值启动即报错，parse 测试锁定点名变量，理由为非法配置拦截生效。
敏感数据策略：TOTP 密钥 AES-256-GCM 加密落库沿用 v1.11.0 本轮未改，挑战只存 token 哈希，理由为无敏感明文存储风险。
文档代码同步：CHANGELOG 1.12.0、OPERATIONS 表格与探针示例、.env.example、TECH_DEBT 三项已偿还标注，理由为发布物料与代码实际同步。

未通过项：
clippy 存量 3 错误：src/config.rs:44、src/totp.rs:100、src/totp.rs:120，理由为留待后续轮次处理。
2FA 限流为 IP 维度：同一出口 IP 多用户共享配额，理由为架构限制需诚实说明。
无独立定时清扫任务：改为发挑战/验码两入口驱动清扫，理由为挑战行只在登录流程中产生无需常驻后台。
Docker 镜像实跑验证：沿用 v1.2.0 已知限制，理由为本机无 daemon 本轮未做。

不适用项：
无 schema 变更故无迁移验证：理由为本轮无数据库表结构改动。
前端无改动故无视觉验收截图：理由为本轮未改任何前端文件。

回归教训——首版清扫误删本次挑战致 410 退化为 401，已用排除变体修复并由既有 tfa_challenge_expiry 用例锁定。