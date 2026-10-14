# 提测前 DoD 对照报告（drama-factory）

> 结论先行：**生产级 checklist 8 大类中，硬缺口剩 4 个**（失败注入测试、resolveExtension 死分支、Agnes/Qwen 录制回放、h2c 产品确认），另有 2 个 UI P1 待修（见 `docs/ui-audit-20.md`）。其余历史排期项（OpenAPI、Dependabot、降级策略文档、敏感数据策略）**本轮核实已交付**，不是缺口。并行任务（Skill 市场、快捷工具）尚未合入，**合入后必须复核**本报告第 5 节。

- 对照基线：`docs/dod-*.md`（最新 `dod-v2.13.md`）+ `~/workspace/muse-build/PRODUCTION_CHECKLIST.md`
- 核查对象：`feat/ui-audit-dod` @ `60c7fad`（= main 最新；本报告只读核查，未改代码）
- 测试基数：892/892（mv-import 轮验收结论）；覆盖率门禁行 0.82 / 分支 0.70（v2.13 棘轮锁定）

## 1. 已达标项（抽查核实）

| 大类 | 项 | 证据 |
|---|---|---|
| 可靠性 | 测试金字塔 892 全绿 | mv-import 验收报告；JaCoCo 门禁 pom 已锁定 |
| 可靠性 | Flyway 版本化迁移（V14） | `src/main/resources/db/migration/` |
| 可靠性 | 健康检查 `/api/health` + 优雅关闭 | 本轮真实服务实测 `{"status":"ok"}` |
| 可观测 | 结构化日志 + request_id 贯穿 | `RequestIdFilter`、`SecretMasker` |
| 可观测 | Prometheus 指标 + 4 条告警规则 | `prometheus/rules/drama-factory.yml` |
| 数据 | 在线备份/恢复脚本（真实跑通过） | `scripts/backup.sh` / `restore.sh`、OPERATIONS.md |
| 数据 | 敏感数据策略成文 | `docs/SECURITY_DATA.md`（清单/存储/脱敏/删除，缺口诚实标注） |
| 数据 | 降级策略成文（每条可定位代码） | `docs/DEGRADATION.md`（含"当前无降级"的诚实项） |
| 部署 | Docker Compose、一键部署 | 沿用 v2.2 |
| 部署 | 运维手册（备份/恢复/升级/日志轮转/故障排查） | `docs/OPERATIONS.md` |
| 安全 | JWT 鉴权 + 密钥环境变量分离 | `JwtAuthFilter`、`AUTH_JWT_SECRET` |
| 安全 | Resilience4j 限流/熔断 | 已落地（限制：单实例内存级，已声明） |
| 安全 | Dependabot | `drama-factory/.github/dependabot.yml`（第 4 轮交付） |
| 可维护 | OpenAPI 文档 | springdoc + `OpenApiConfig.java`（第 4 轮交付） |
| 可维护 | CHANGELOG（Keep a Changelog） | `CHANGELOG.md` |

## 2. 未达标项（提测前必须处理或明确声明）

### G1 失败注入测试缺失 —— 建议补（成本约 1 天）
- 现状：`src/test` 无任何失败注入/混沌用例（中英文关键词全无）；`dod-mv-v2.md` 已由编排器确认为缺口，至今未补
- 补救：给关键路径加 3–5 例——视频生成通道失败触发降级（mock Agnes 抛 `RateLimitedException`）、ffmpeg 缺失抛错、auth-service 不可达返回 502；断言降级原因落库与用户提示
- 不补的代价：降级链路（DEGRADATION.md 写明的核心卖点）无测试兜底，回归即裸奔

### G2 `resolveExtension` 不可达 "bin" 分支未删 —— 顺手修（成本约 0.5 天）
- 现状：`ByokGenerateService.java:360` 仍在；v2.13 因 dpsk 两轮 PATCH 锚定失败延期 v2.14
- 补救：人工删（dpsk 已两次失败，建议人肉改 5 行 + 跑相关单测）

### G3 Agnes/Qwen submit/poll 录制回放缺失 —— 可声明为已知限制（需外部 API）
- 现状：真实 provider 的提交/轮询分支无测试覆盖；v2.13 起连续排期
- 建议：提测前如无外部 API 可调用，写成"已知限制"（录制回放 infra 缺），不阻塞；有 API 后补

### G4 h2c 配置锁定待产品确认 —— 需要产品决策（非代码问题）
- 现状：v2.9 起遗留；是否锁定 HTTP/2 明文（h2c）无结论
- 建议：用户拍板"锁定/不锁定"二选一，1 行配置 + 文档 1 段

### G5 UI P1-1/P1-2（本轮审计新发现）—— 必须修（成本约 0.5 天）
- `settings.html` 缺主题脚本（浅色模式渲染深色）；`auth.css` 登录主按钮蓝色违规；详见 `docs/ui-audit-20.md`

## 3. 建议暂缓项（可提测后排期）

| 项 | 理由 |
|---|---|
| 移动端窄屏适配 | 桌面 Harness 定位；审计未覆盖窄屏，提测后按反馈补 |
| 快捷键 D1–D4（`docs/shortcuts-decision.md`） | 产品决策已出；属体验增强，非提测门槛 |
| UI P2-1…P2-7 |  polish 类；建议与快捷键同批交付 |
| 真实负载验证（接近真实数据量/并发） | checklist §8 要求；提测前至少跑一次 100 并发冒烟 |
| 故障演练（杀进程/断网/磁盘满） | 同上；抽查恢复即可 |

## 4. 已知限制（声明即可，不阻塞）

- 限流/熔断为单实例内存级，多实例不共享窗口（dod-v2.3 已声明）
- `/actuator/prometheus` 无鉴权，部署约束：不得将 8081 暴露公网（OPERATIONS.md 已写）
- 开放模式（`AUTH_JWT_SECRET` 为空）下无多用户隔离（DEGRADATION.md 已写）

## 5. 并行任务合入后复核清单

Skill 市场、快捷工具合入 main 后，复核：
1. Flyway 迁移版本号连续（V15+ 无冲突）
2. 全量测试仍全绿（目标 ≥ 当前 892 + 新增）
3. 新增页面的深浅主题截图走查（沿用本报告方法）
4. 新增 API 进 OpenAPI（springdoc 自动收录，抽查 2 个）
5. CHANGELOG/ROADMAP 同步更新

## DoD 缺口 Top5（按提测紧迫度）

1. **UI P1-1/P1-2** —— 用户第一眼即见；0.5 天
2. **失败注入测试** —— 降级链无测试兜底；1 天
3. **resolveExtension 死分支** —— 顺手；0.5 天
4. **h2c 产品确认** —— 等一句话决策；0 天代码量
5. **Agnes/Qwen 录制回放** —— 无外部 API 则声明已知限制；0 天或 1 天
