# 敏感数据策略（SECURITY_DATA）

本文说明 drama-factory 里哪些数据算敏感、存在哪、谁能读、怎么脱敏、怎么删，以及还没补上的缺口。
原则：**密钥类数据只落在本地，不进数据库，不写日志。** 日志里能出现的只有 request_id 这类非敏感标识。

## 1. 敏感数据清单

| 数据类型 | 配置键 / 来源 | 存在哪 | 明文/脱敏 | 谁可读 |
|---|---|---|---|---|
| DeepSeek BYOK 密钥 | `deepseek.api-key` | `data/settings.json`（`SettingsService.SETTINGS_PATH`，设置中心持久化） | 明文落盘，展示/日志时脱敏 | 本机同账号用户；运行时由 CredentialResolver 读取 |
| DashScope BYOK 密钥 | `dashscope.api-key` | `data/settings.json` | 明文落盘，展示/日志时脱敏 | 同上 |
| JWT 签名密钥 | `AUTH_JWT_SECRET` | 仅环境变量 | 明文（进程内存） | 启动该进程的人 / 同主机可见环境变量者 |
| auth-service 账号密码 | 由 auth-service 自行管理 | 不在本服务持久化 | 不落本服务 | auth-service |
| Authorization / Bearer 头 | 请求头 | 不落盘，仅请求生命周期内 | 需要展示时用 SecretMasker 脱敏 | 请求处理链 |
| Cookie（含鉴权 cookie） | 请求头 | 不落盘 | 原样转发，不记日志 | 请求处理链 |
| request_id | `X-Request-Id` | 日志 | 明文（非敏感） | 看日志的人 |
| H2 文件库 | 本地文件 | 本地磁盘（`data/drama-factory.mv.db`） | 明文 | 本机同账号用户 |

## 2. 存储策略

- **BYOK 密钥只存本地设置文件，不入库。** 由 `com.dramafactory.service.CredentialResolver` 从设置中心读取 `deepseek.api-key`、`dashscope.api-key`。数据库（H2）里没有密钥字段。
- **JWT secret 只走环境变量 `AUTH_JWT_SECRET`。** 由 `com.dramafactory.config.JwtAuthFilter` 读取；为空时进入开放模式（启动打 warn）。密钥不写进设置文件、不进数据库。
- **auth-service 的密码不由本服务持久化。** 本服务通过 `com.dramafactory.controller.AuthProxyController` 把 `/api/auth/**` 代理给 auth-service，只是转发 Authorization 相关 cookie/header，自身不存账号密码。
- 设置文件属于本机敏感文件，权限建议见第 5 节。

### 浏览器 token 存储（httpOnly Cookie）

- 浏览器侧登录态由 httpOnly Cookie 承载：`df_at`（access token，Path=/，Max-Age 为 access token 有效期）与 `df_rt`（refresh token，Path=/api/auth，Max-Age 7 天）。
- 两个 cookie 都是 HttpOnly + SameSite=Lax，前端 JS 读不到，auth.js 不再用 localStorage 存 token；localStorage 只留 `df-theme`/`df-lang` 这类非敏感偏好。
- BFF 代理（AuthProxyController）负责翻译：登录/刷新/OAuth 回调成功时，把响应体里的 token 剥掉，改成下发 Set-Cookie；其余 /api/auth/** 请求把 `df_at` 转成 `Authorization: Bearer` 头再发给上游；登出时下发 Max-Age=0 清 cookie。
- Secure 标志由 `auth.cookie.secure` 控制（默认 false，环境变量 `AUTH_COOKIE_SECURE=true` 开启）；生产 HTTPS 部署开启后，浏览器只在 HTTPS 下发送 cookie。
- CSRF 纵深：对"没有 Authorization 头、靠 cookie 认证的 POST/PUT/DELETE/PATCH /api/auth/** 请求"，校验 Origin（没有就回退 Referer）与 Host 是否同源；不一致返回 403 `{"code":"FORBIDDEN"}`。
- 没有 Origin/Referer 的请求（比如 curl）放行；GET 请求和自带 Bearer 的请求不受这条校验影响。
- API 客户端（非浏览器）仍可直连 auth-service（默认 :8082），用响应体里的 accessToken/refreshToken 走 `Authorization: Bearer`；浏览器和 API 两条路径并存。
- 静默刷新：access 过期 → 前端 POST /api/auth/refresh（无 body，代理从 `df_rt` 取）→ 新 cookie 下发 → 原请求重试；refresh 也过期 → 跳登录页。

## 3. 日志脱敏策略

- **可以记**：`X-Request-Id`（由 `com.dramafactory.config.RequestIdFilter` 透传或生成），用于串联一次请求。
- **一律不记**：`Authorization` 头、Bearer token、`deepseek.api-key` / `dashscope.api-key` 的值、`AUTH_JWT_SECRET`。
- 任何"需要打印一段疑似密钥/令牌"的场景，必须先用 `com.dramafactory.util.SecretMasker` 脱敏：
  - `SecretMasker.mask(secret)`：null/空原样返回；长度 ≤8 返回 `****`；否则保留前 2 + `****` + 后 2。
  - `SecretMasker.maskBearer(headerValue)`：`Bearer <redacted>` 形式则脱敏后半段，否则走 `mask()`。
- logback（`logback-spring.xml`）的 pattern 只包含 request_id 等非敏感字段；json profile 同理，不新增打印请求头的字段。
- **日志审计结论（2026-10-14，v2.6）**：用 grep 全量核对过 `src/main/java` 下所有 `log.*` / `System.out` 语句，**没有直接打印密钥或完整 Authorization 头的语句**。`CredentialResolver` 的 javadoc 也明确声明"密钥仅从设置文件读取，绝不打印到日志"。排查命令留档备查：
  ```
  grep -rn "api-key\|apiKey\|api_key" src/main/java | grep -i "log\.\|System.out"
  grep -rn "Authorization\|Bearer" src/main/java | grep -i "log\.\|System.out"
  ```

## 4. 删除策略

- **删除 provider 配置即删除密钥**：用户在设置中心移除某个 provider 配置时，对应的 `deepseek.api-key` / `dashscope.api-key` 随之从 `data/settings.json` 删除（SettingsService 写回全量设置，不保留已删键）。
- **备份文件含明文密钥**：`scripts/backup.sh` 会把 `data/settings.json` 一起打进备份包，所以备份里带着 BYOK 密钥明文。要求：
  - 备份文件按敏感文件对待，限制访问权限、不外传。
  - **恢复后密钥仍然有效**：因为密钥是明文存储的，从备份恢复设置文件后，原密钥可继续使用，**不需要也不应重新生成**——但若该密钥在别处已泄露或被轮换过，恢复后要立刻按第 5 节轮换。

## 5. 已知缺口与排期

| 缺口 | 现状 | 建议 | 排期 |
|---|---|---|---|
| 设置文件权限未强制 600 | `data/settings.json` 默认按进程 umask 创建 | 写入时设为仅属主可读写（POSIX 600） | v2.7 |
| 无密钥轮换手册 | 当前靠手动改设置文件 | 补轮换步骤：改文件 → 重启 → 验证旧密钥失效 | v2.7 |
| 备份含明文密钥 | 见第 4 节，已核实 | 评估备份时排除设置文件，或给备份加密 | v2.7 |
| 开放模式无隔离 | `AUTH_JWT_SECRET` 为空即开放 | 生产环境强制要求设置该变量，启动校验 | v2.7 |
