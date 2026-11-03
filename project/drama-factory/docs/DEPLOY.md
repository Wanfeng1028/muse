# Drama Factory 部署文档（DEPLOY）

一台服务器，一条命令，全套起飞：`auth-service`（账号）+ `app`（主服务）+ `nginx`（反代）。

## 1. 服务器规模建议

| 阶段 | 配置 | 说明 |
|---|---|---|
| 起步 | **1 台 2核4G 轻量服务器** | auth + app + 内嵌文件库（H2）+ nginx 全装，用户几千无压力；auth 本身 1核1G 就够 |
| 上量 | 4核8G 起 | 换 PostgreSQL + Redis（替换 H2 文件库与内存限流），auth 与 app 可分开部署 |

内嵌文件库（H2）与内存限流是单机方案；多机/上量后再拆（见 ROADMAP）。

## 2. 部署步骤

```bash
# 1. 准备环境变量
cp .env.example .env
# 生成 JWT 密钥并填入 .env 的 AUTH_JWT_SECRET
openssl rand -base64 48

# 2. 一键启动
docker compose up -d --build

# 3. 验证
curl http://localhost/api/health                       # 主服务 200
curl http://localhost/api/auth/oauth/providers         # ["google","github","apple"]

# 4. 看日志 / 停止
docker compose logs -f
docker compose down
```

打开 `http://<服务器IP>` 即可使用（nginx 80 → 主服务；`/api/auth/*` → auth-service）。

## 3. 环境变量表

| 变量 | 必填 | 说明 |
|---|---|---|
| `AUTH_JWT_SECRET` | 是 | JWT HS256 密钥，auth 签发、app 验签共用。生成：`openssl rand -base64 48`。为空时 auth-service **拒绝启动**，主服务 API 为开放模式（仅适合单机） |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | 否 | Google OAuth；申请：console.cloud.google.com/apis/credentials |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | 否 | GitHub OAuth；申请：github.com/settings/developers |
| `APPLE_CLIENT_ID` / `APPLE_TEAM_ID` / `APPLE_KEY_ID` / `APPLE_PRIVATE_KEY` | 否 | Apple OAuth；`.p8` 内容换行用 `\n` 转义 |
| `PORT` | 否 | 主服务端口（默认 8081） |
| `VIDEO_PROVIDER` | 否 | `mock`（默认）/ `qwen` / `agnes` |

**secret 不许进仓库**：`.env` 已在 `.gitignore`，只提交 `.env.example`（值全空）。

## 4. 账号体系说明

- 注册：`POST /api/auth/register`（邮箱+密码+昵称），首个注册用户为管理员
- 登录：`POST /api/auth/login` → accessToken（15 分钟）+ refreshToken（7 天）
- 刷新：`POST /api/auth/refresh`（轮换，旧 token 作废）
- 登出/资料/改密码/改邮箱/会话列表与撤销：见 auth-service `AuthController`
- OAuth：`GET /api/auth/oauth/{google|github|apple}/url` → 跳转 → `/callback`
- **诚实声明**：OAuth 未配置凭证时返回 `501 OAUTH_NOT_CONFIGURED`，handshake 未实测，不伪造"已验证"
- 安全：密码只存 PBKDF2-HMAC-SHA256 hash（600k 轮，OWASP 参数；见下）；登录防爆破（同邮箱+IP 15 分钟 5 次失败 → 429）；密码强度（≥8 位含字母数字）；敏感操作（改密码/改邮箱）必须重新验证密码；改密码后撤销其他会话；密码不打日志

## 5. 与原计划的偏离（离线构建约束，如实记录）

1. **数据库用 H2 文件而非 SQLite**：离线 Maven 仓库无 `sqlite-jdbc`，auth-service 采用与主服务一致的 H2 文件库（`./data/auth`），同样"内嵌文件、无需独立 DB"，满足本意；上量后统一换 PostgreSQL。
2. **密码哈希用 PBKDF2-HMAC-SHA256 而非 BCrypt**：离线仓库无 spring-security，PBKDF2（600k 轮）为 JDK 标准库实现、OWASP 推荐参数，与 BCrypt 同等安全级别；不手写 crypto。
3. **JWT 手写 HS256**：离线仓库无 jjwt，用 `javax.crypto` + Jackson 实现（签发/验签/过期检查），auth 与 app 共用同一密钥。

## 6. 数据卷

- `./data` → 主服务 H2 文件库、媒体、设置
- `./auth-data` → auth-service H2 文件库
- 备份：定期拷贝这两个目录即可
