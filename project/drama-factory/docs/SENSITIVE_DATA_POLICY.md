# 敏感数据策略（SENSITIVE_DATA_POLICY）

> 适用范围：drama-factory（Java 21 + Spring Boot AI 短剧 Harness）。
> 本文是 `docs/SECURITY_DATA.md`（2026-10-14 审计结论摘要）的完整策略版，二者关系见文末第 7 节。
> 红线：本文只描述已核实事实；凡未核实或未实现，一律标注"待实现/待核实"，不得当作已实现。

---

## 1. 敏感数据清单

| 类型 | 示例 / 配置键 | 存在哪 | 形态 | 谁可读 | 对应代码 |
|---|---|---|---|---|---|
| BYOK 密钥（DeepSeek） | `deepseek.api-key` | `data/settings.json`（`SettingsService.SETTINGS_PATH`） | **明文落盘** | 本机文件系统可读者；运行时由服务读取 | `SettingsService`、`com.dramafactory.service.CredentialResolver` |
| BYOK 密钥（DashScope） | `dashscope.api-key` | `data/settings.json` | **明文落盘** | 同上 | 同上 |
| JWT 签名密钥 | 环境变量 `AUTH_JWT_SECRET` | 进程环境变量 | 明文（仅内存/环境） | 进程与能读环境变量者 | `com.dramafactory.config.JwtAuthFilter` |
| auth-service 账号密码 | 用户登录凭据 | **不由本服务持久化** | 不落盘（仅代理转发） | auth-service | `com.dramafactory.controller.AuthProxyController` |
| 浏览器 access token | Cookie `df_at`，`Path=/` | 浏览器 Cookie | HttpOnly + SameSite=Lax；`Secure` 由 `auth.cookie.secure` 控制（默认 false，`AUTH_COOKIE_SECURE=true` 开启） | 浏览器（脚本不可读） | 认证链路（Cookie 下发/校验） |
| 浏览器 refresh token | Cookie `df_rt`，`Path=/api/auth`，`Max-Age` 7 天 | 浏览器 Cookie | 同上 | 浏览器（脚本不可读） | 同上 |
| Authorization / Bearer 头 | `Authorization: Bearer <token>` | HTTP 请求头（瞬时） | 传输中明文；日志中经 `maskBearer` 脱敏 | 请求链路、日志读取者（脱敏后） | `com.dramafactory.util.SecretMasker.maskBearer` |
| 请求追踪 ID | `request_id` | 日志字段 | **非敏感**，可原样记录 | 日志读取者 | `logback-spring.xml` pattern |
| H2 文件库 | `data/drama-factory.mv.db` | 本地磁盘文件 | **明文** | 本机文件系统可读者 | H2 持久化 |
| 备份归档 | `scripts/backup.sh` 产物（H2 + `media/` + `settings/`） | 归档目录 | 明文（含密钥与业务数据） | 能读归档者 | `scripts/backup.sh` |
| 用户自创内容：人名/联系方式 | `prompt_templates`、`prompt_recipes`、`runs.goal`、`runs.plan_json`、`drama_characters` 角色名 | H2 文件库 / 备份 | 明文（业务数据，非密钥但敏感） | 能读 H2/备份者、有权限的接口调用者 | 对应实体与 DAO |

**要点**：数据库（H2）内**没有任何密钥字段**；BYOK 密钥只在设置文件，JWT 只在环境变量，auth 密码不在本服务。

---

## 2. 存储策略

### 2.1 BYOK 密钥
- 只落本地设置文件 `data/settings.json`，**不入数据库**。
- 运行时由 `CredentialResolver` 读取。
- 文件权限建议：`chmod 600 data/settings.json`，属主为服务运行账号，禁止组/其他可读。
- 禁止把 `data/settings.json` 提交进版本库；`.gitignore` 应包含 `data/`。

### 2.2 JWT 签名密钥
- 只走环境变量 `AUTH_JWT_SECRET`；**不进设置文件、不进数据库**。
- 为空时进入开放模式并打 warn（安全降级，生产必须设置）。
- 建议通过部署环境的 secret 管理注入，避免写入 shell history / 进程可见的明文脚本。

### 2.3 浏览器 Cookie
- `df_at`：access，`Path=/`；`df_rt`：refresh，`Path=/api/auth`，`Max-Age` 7 天。
- 两者均为 HttpOnly + SameSite=Lax；前端 localStorage 只保留 `df-theme` / `df-lang` 非敏感偏好。
- `Secure` 由 `auth.cookie.secure` 控制，默认 false；生产应设 `AUTH_COOKIE_SECURE=true`，走 HTTPS。
- 对"无 Authorization 头、靠 cookie 认证"的 POST/PUT/DELETE/PATCH `/api/auth/**` 请求做 Origin/Referer 同源校验，不一致返回 403（CSRF 缓解）。

### 2.4 H2 明文本地文件
- `data/drama-factory.mv.db` 明文存于本地磁盘，包含业务数据（含用户自创内容里的人名/联系方式）。
- 访问控制要求：文件权限建议 `chmod 600`；仅服务账号可读写所在目录；禁止把 `data/` 暴露为静态资源或 Web 目录。
- 备份归档（`scripts/backup.sh` 会归档 H2 + `media/` + `settings/`）同样按敏感文件保护，权限建议 `chmod 600`，仅限授权者读取。

---

## 3. 日志脱敏规则

### 3.1 能记什么
- `request_id` 等非敏感字段（`logback-spring.xml` pattern 只含此类字段）。
- 业务标识（如项目/任务 ID），不包含密钥、完整 Authorization 头、cookie 值。

### 3.2 一律不记什么
- BYOK 密钥（`deepseek.api-key` / `dashscope.api-key`）原值。
- JWT 签名密钥（`AUTH_JWT_SECRET`）原值。
- 完整 `Authorization` 头 / Bearer token 原值。
- cookie `df_at` / `df_rt` 原值。
- auth-service 账号密码。

### 3.3 SecretMasker 用法
- `com.dramafactory.util.SecretMasker.mask(secret)`：
  - `null` / 空 → 原样返回；
  - 长度 ≤ 8 → 返回 `****`；
  - 否则 → 前 2 位 + `****` + 后 2 位。
- `maskBearer(headerValue)`：脱敏 Bearer 后半段。
- 凡需记录可能与密钥相关的字符串，必须先经上述方法处理。

### 3.4 审计结论与复查命令
- 2026-10-14 已用 grep 全量审计 `src/main/java` 下所有 `log.*` / `System.out`，**无直接打印密钥或完整 Authorization 头的语句**。
- 复查命令（可重复执行）：

```bash
# 查可疑日志打印
grep -rnE "(log\.(info|debug|warn|error)|System\.out)" src/main/java | grep -iE "(api-?key|secret|authorization|bearer|df_at|df_rt|password)"
# 期望：无匹配（通过标准：输出为空）

# 查设置文件中是否被误提交
grep -rn "settings.json" .gitignore
# 期望：包含 data/ 或 settings.json
```

---

## 4. 删除与保留

### 4.1 密钥轮换 / 删除
- **现状**：`SettingsController` 只有 `GET ""`、`PUT ""`、`GET /effective-provider`，**当前无删除密钥的 API**。
- 临时流程：手动编辑 `data/settings.json` 删除对应键（`deepseek.api-key` / `dashscope.api-key`），重启服务使 `CredentialResolver` 重新读取。
- JWT 密钥轮换：更换环境变量 `AUTH_JWT_SECRET` 并重启；注意旧 token 失效影响。
- **待实现**：密钥删除 API（排期建议：第 6 轮）。

### 4.2 用户数据删除
- 项目删除是否级联删除剧集 / 分镜 / 视频任务 / 成片：**待核实**（需查项目删除链路是否含级联删除逻辑；未核实前不得声称"已级联"）。
- 用户自创内容（`prompt_templates`、`prompt_recipes`、`runs.goal`、`runs.plan_json`、`drama_characters`）应随所属项目一并删除；级联范围待核实。
- 多用户归属：`V6__owner_id.sql` 给 `drama_projects` 加 `owner_id VARCHAR(128)`，老数据回填 `'local'` 后设 NOT NULL；`CurrentUser.currentUserId()` 从 request attribute `auth.userId` 取，取不到回退 `"local"`。删除操作应校验 `owner_id` 归属。

### 4.3 备份保留期
- `scripts/backup.sh` 保留最近 7 个归档。
- 归档含 H2 + `media/` + `settings/`，等同敏感文件保护；到期清理应确保彻底删除，避免残留明文密钥。

---

## 5. 审计清单（可重复执行）

| 检查项 | 命令 / 操作 | 通过标准 |
|---|---|---|
| 日志无密钥打印 | `grep -rnE "(log\.(info|debug|warn|error)\|System\.out)" src/main/java \| grep -iE "(api-?key\|secret\|authorization\|bearer\|df_at\|df_rt\|password)"` | 输出为空 |
| 设置文件权限 | `ls -l data/settings.json` | 权限为 `600`（仅属主可读写） |
| H2 文件权限 | `ls -l data/drama-factory.mv.db` | 权限为 `600` |
| 备份归档权限 | `ls -l <备份目录>` | 归档权限为 `600`，仅授权者可读 |
| JWT 环境变量 | `printenv AUTH_JWT_SECRET \| wc -c` | 生产环境非空；为空时确认仅限本地开发 |
| Cookie Secure 标志 | 检查部署配置 `auth.cookie.secure` / `AUTH_COOKIE_SECURE` | 生产为 `true` |
| Cookie 属性 | 浏览器 DevTools 查看 `df_at` / `df_rt` | 均为 HttpOnly + SameSite=Lax；`df_rt` Path=/api/auth，Max-Age 7 天 |
| 设置文件未入库 | 检查 H2 schema/表结构 | 无任何密钥字段 |
| 设置文件未提交 | `git check-ignore data/settings.json` | 返回被忽略（或不在版本库中） |
| Origin 校验 | 对 `/api/auth/**` 的 POST/PUT/DELETE/PATCH 发跨源请求 | 返回 403 |

---

## 6. 缺口与排期表

| 缺口 | 现状 | 排期建议 |
|---|---|---|
| 密钥删除 API | `SettingsController` 无删除接口，仅 `GET ""`、`PUT ""`、`GET /effective-provider` | 第 6 轮 |
| BYOK 密钥加密存储 | `data/settings.json` 明文落盘 | 待评估（第 6 轮后） |
| H2 文件加密 | `data/drama-factory.mv.db` 明文 | 待评估 |
| 项目删除级联范围 | 是否级联删剧集/分镜/视频任务/成片 **待核实** | 核实后补文档 |
| 备份归档加密 | 归档明文（含密钥与业务数据） | 待评估 |
| auth 密码存储 | 不由本服务持久化（现状即目标） | 无需改动 |

> 以上"待实现/待核实"项不得在实现前对外表述为已完成。

---

## 7. 与 docs/SECURITY_DATA.md 的关系

- `docs/SECURITY_DATA.md`（2026-10-14，65 行）是当次审计的**结论摘要**，记录"当时查了什么、结论是什么"。
- 本文是同一主题的**完整策略版**：给出敏感数据清单、存储策略、日志脱敏规则、删除与保留、审计清单、缺口排期。
- 两份文档**并存**：摘要保留历史审计结论，策略版随实现演进而更新；若两者冲突，以本文为准，并回填修正 `SECURITY_DATA.md`。
- 本文不替代 `SECURITY_DATA.md`，也不删除它。
</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>