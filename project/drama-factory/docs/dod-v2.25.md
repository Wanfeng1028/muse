# 发版对照报告：v2.25 第 24 轮「账号体系 P0#2 收官」

一句话：本轮按 v2.24 排期建议从分支覆盖转向功能深耕，完成账号体系 P0#2 收官，同时挖出并修掉一个让整个登录链路失效的致命 bug。

- 日期：2026-10-16
- 基线：v2.24（分支覆盖 94.03%，门禁 BRANCH 0.94 / LINE 0.92）
- 目标：ROADMAP P0#2「账号体系」收官；分支覆盖不再冲刺
- 结果：A/B1/B2/B3 四批 + 编排手工 3 处，账号体系功能闭环，API E2E 与浏览器交互全过
- 测试数：auth-service `mvn -o test` 16/16 全绿（原 12 + 新增 4），BUILD SUCCESS
- 分支覆盖：保持 94.03%（门禁未动）
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash 生成，A/B1/B2/B3 四批 PATCH + 编排手工 3 处
- 轮次定位：本轮未做原排期的 v2.25 分支覆盖冲 95%。v2.24 排期原文写「剩余可达约 15 个分支，边际收益递减，建议转功能深耕」，本轮按此建议转向功能深耕。

## 各批交付

| 批次 | 范围 | PATCH 数 | 应用情况 | 交付要点 |
|---|---|---|---|---|
| A | 后端语言偏好（auth-service） | 10 | 10/10 全应用 | `User.java` 新增 `language` 字段（`@Column(length=16)` 可空，`ddl-auto: update` 下给已有数据的库加 NOT NULL 列会失败）；`AuthService` `UserDto` 加第 6 组件 `language`，`updateProfile` 改 4 参，白名单 `{"zh-CN","en"}` 校验，非法抛 `ApiException(400, "BAD_REQUEST", "不支持的语言")`，新增 `normalizeLanguage`（null 回退 zh-CN），`toDto` 传入回退值；`AuthController` `ProfileRequest` 加 `language` 组件，`PUT /profile` 透传；`AuthServiceTest` 2 处既有调用改 4 参，新增 4 测试 |
| B1 | 前端 HTML（static） | 8 | 8/8 全应用 | `auth.js` `updateProfile(nickname, avatarUrl, language)`，language 非 undefined 才进 body；`login.html` 修 OAuth 按钮选择器 bug；`account.html` 33 处 `data-i18n` + 语言选择器（`input[name="lang"]` zh-CN/en + `lang-error`） |
| B2 | account.js 双语 | 17 | 15 应用 + 2 手工 | 41 key 中英字符串表 + `tr(key)` + `readLang()`（localStorage `df-lang`）+ `applyI18n(lang)`；`bindLanguage()` radio 切换先落服务端再写本地；`reloadMe()` 以服务端 `u.language` 为准；`boot()` 先 `applyI18n(readLang())` 秒开；15 处硬编码中文换 `tr()`；`node --check` 通过 |
| B3 | auth.js 致命 bug 修复 | 5 | 5/5 全应用 | token 存取（`df-access-token`/`df-refresh-token`）、`rawFetch` 默认附 Bearer 头（`opts.noAuth` 跳过）、`tryRefresh` 用存量 refreshToken 调 `/refresh`、`login`/`register` 直调 `rawFetch` 并存 token、`logout` 成功失败都清 token；`node --check` 通过 |
| 编排手工 | 视觉验收补丁 | 1 | 1/1 | `bindLanguage()` 补 `syncChecked(currentLang);` 初始调用 |

## 真实验证

以下全部为实测，非推演。

### API E2E（真实 auth-service :8082，H2 文件库）

register→201（language 默认 zh-CN）→login→token 对→`GET /me` 200→`PUT /profile {language:"en"}` 200→`PUT {language:"fr"}` 400「不支持的语言」→`/me` 持久化 en→`/sessions` 200→`/refresh` 轮换成功→`/logout` 200。全过。

### 浏览器交互（Playwright 真实 Chromium，route 代理到真实服务）

账号页点 English radio → 抓到 `PUT /profile {nickname:null,avatarUrl:null,language:"en"}` → 页标题「账号 · AI 短剧工坊」→「Account · AI Drama Factory」→ 服务端 language=en、localStorage df-lang=en、无错误框。INTERACT PASS。

### 视觉验收（亲眼看过 4 张）

- login 页（未登录态）：表单 + 三 OAuth 按钮正常
- account-zh：中文全页，资料/安全/会话「—本机」/个性化语言选择器/退出
- account-en：英文全页，English radio 选中态已修复验证

无布局/文案 bug。

## 本轮发现的真实 bug

| # | 位置 | 现象 | 发现方式 | 修复 |
|---|---|---|---|---|
| 1 | `static/auth.js` | 后端登录返回 token 对、除公开端点外全要 `Authorization: Bearer`，但前端 `login()` 直接丢弃 token、从不发送头——登录成功后 `/me` 等全部 401，账号页永远跳回登录页；`tryRefresh()` 空 body 调 `/refresh`（后端要 `RefreshRequest{refreshToken}`）永远失败。整个账号体系登录链路是断的 | 前端链路核查 | B3 批：token 存取 + `rawFetch` 默认附 Bearer 头 + `tryRefresh` 用存量 refreshToken + `login`/`register` 存 token + `logout` 清 token。注释如实写 XSS 权衡 |
| 2 | `static/login.html` | OAuth 按钮 class 是 `btn-oauth`，绑定代码却写 `.oauth-btn`，三按钮点击无反应 | 前端链路核查 | B1 批：改为 `.btn-oauth` |
| 3 | `static/account.js` | `bindLanguage()` 定义了 `syncChecked` 却从未初始调用，英文态下语言 radio 无选中态 | 视觉验收 | 编排手工加一行 `syncChecked(currentLang);`（有先例，v2.11 同样手工补过） |

## 本轮修 dpsk 输出 / 编排手工修

- B2 双锚定手工等价替换：2 个 PATCH 因 OLD 在 `bindEmail`/`bindPassword` 两处同字（`'修改失败'`）各出现 2 次而锚定失败，编排手工对两处做同一替换（等价应用）。
- `bindLanguage` 漏 `syncChecked`：见上，视觉验收发现，手工补一行。
- 工具链两次写坏与恢复：
  1. `apply_patches.py` 的 `=== FILE:` 头是整文件覆盖语义——prompt 误写 `=== FILE:` 致 4 文件被 PATCH 原文写坏，`git checkout` 恢复后改用 `=== PATCH:` 重放成功。教训：prompt 的块头必须与脚本语义一致。
  2. dpsk 自创 `--- NEW-END` 无尾 `---` 变体（17 处），且单块内放多组 OLD/NEW（17 个微 PATCH 挤在 8 个块里）；旧脚本贪婪 NEW 吞掉后继理由行致 marker 泄漏进 `account.js`（`node --check` 抓出）。

## 工具链沉淀

新增 `scripts/apply_dpsk2.py`（v3）：

- 支持单块内多组 OLD/NEW 逐组应用
- 双变体 closer（兼容 `--- NEW-END` 无尾 `---`）
- `--- NEW-END` 缺失或 marker 泄漏时直接报错不写文件

## 生产级 checklist 对照

按仓库 `PRODUCTION_CHECKLIST.md`，诚实打分。

### 通过

- 输入校验：语言白名单 400、密码强度、头像禁字母既有
- 错误处理：401→refresh 重试→跳登录既有；语言非法 400
- 配置密钥分离：`AUTH_JWT_SECRET` 缺失拒绝启动既有
- 健康检查：主服务既有（auth-service 本轮未加，见下）
- 结构化日志：既有

### 未通过 → 排期

- auth-service 无 Flyway（`ddl-auto: update`，本轮 language 列可空即为兼容历史库的妥协，记技术债）
- token 存 localStorage（XSS 权衡，httpOnly Cookie 需后端配合，排期）
- auth-service 无 `/actuator/prometheus` 与备份脚本（主服务 v2.4 已有，auth-service 待补，排期）
- `GET /api/auth/providers` 需登录（登录页无法预知可用 OAuth 渠道，当前靠 501 诚实报错，可用但体验可优化，排期）
- login/register 页未双语（本轮 v1 仅账号页双语，全站 i18n 为后续里程碑）

### 不适用

- DB 迁移版本化：auth-service 侧不适用既有 Flyway 体系，见上
- 滚动更新：单机 compose 部署，限制已在 `OPERATIONS.md` 声明

## DoD 未通过项新排期

1. auth-service 接 Flyway（或明确声明 `ddl-auto: update` 为长期策略）
2. token httpOnly Cookie 化
3. auth-service 指标/备份/运维手册补齐（对标主服务 v2.4）
4. 全站 i18n（login/register/控制台各页）
5. 分支覆盖冲 95%（剩余约 15 可达分支，长期低优先级）
6. Agnes/Qwen submit/poll 真实链路（需外部 API）
7. h2c 锁定待产品确认（多轮遗留）
8. `testFullPipeline` flaky 根因（多轮遗留）

## 诚实声明

本轮生产代码有逻辑修改：`auth.js` token 链路、`account.js` 双语、`User.language`。这与覆盖率轮「生产代码零修改」不同，如实区分。B3 批修的是登录链路致命 bug，不是样式或文案调整。