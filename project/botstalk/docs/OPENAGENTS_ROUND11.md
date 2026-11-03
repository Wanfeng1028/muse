# OpenAgents 第 11 轮：分享管理 UI 与只读查看页实时刷新

## 1. 原版规格

本轮不改服务端分享协议：签发（POST）、列表（GET）、吊销（DELETE）、只读查看端点全部原样复用第 10 轮已验证的实现。本轮任务只有两块，均属第 10 轮明确遗留的 Web 端工作：

- 在管理端 Web UI 中为房主/管理员提供分享链接管理界面：签发新链接、列出链接、撤销链接。
- 让已发布的只读查看页周期性刷新内容，使查看者无需手动重载即可看到房间内的新消息。

## 2. 本轮设计决策

### 2.1 客户端 API 层（api.ts）

- 新增类型 `ShareLinkMeta`（列表行：id、room、created_at_ms、expires_at_ms、revoked_at_ms）与 `IssuedShareLink`（签发响应：id、room、share_token、share_url、expires_at_ms；share_url 为相对路径 "/share/" + 令牌）。
- 新增三个函数：`listShareLinks`、`issueShareLink`（可选有效期小时数）、`revokeShareLink`。
- `revokeShareLink` 发 DELETE；网关成功返回 204 空 body，故按空 body 处理，不解析 JSON。
- 列表响应绝不包含令牌本身，客户端只用 `shareUrl` 展示。

### 2.2 ShareManager 组件

- 复用现有 `appr-*` 样式类，不新增 CSS。
- 有效期输入默认 168 小时，提交时钳制到 1–720 小时。
- 签发成功后的一次性链接区块只保存在组件 state，不写入 localStorage，关闭组件即消失。
- 列表行只显示 id 前 8 位与创建时间、到期时间、状态（有效 / 已过期 / 已撤销）；仅“有效”行显示撤销按钮。
- 非管理员尝试签发时由 API 层返回 403，界面显示“只有房主或管理员能管理分享链接”。

### 2.3 入口

Chat 顶栏与底部模块条各加一个“分享”入口，打开 ShareManager 管理面板。

### 2.4 ShareView 只读查看页

- 原有文案与类名保持不变。
- 新增 15 秒定时轮询刷新消息列表：token 变化时重建定时器，组件卸载时清除，`alive` 守卫防止卸载后写入 DOM。
- 底部新增一行“每 15 秒自动刷新”。

## 3. 交付

- 服务端：`server.ts` 加全局 OPTIONS 预检处理（见第 4 节）。
- Web：`api.ts`（类型与三个函数）、`ShareManager` 组件、Chat 顶栏/底部模块条入口、`ShareView` 轮询。
- 测试：网关测试 `cors-preflight.test.ts`（2 例）、真实网关冒烟脚本 `scripts/smoke-share-manage.mjs`（11 步）。
- 截图：`docs/screenshots/share/share-manage.png`、`docs/screenshots/share/share-manage-issued.png`、`docs/screenshots/share/share-view.png`。

## 4. 验收

### 4.1 静态检查与网关测试

Web 端 `tsc -b` 与 `vite build` 通过。网关全量 74 文件 964 例全绿（含新增预检 2 例；此前为 962 例）。

### 4.2 真实网关冒烟

`scripts/smoke-share-manage.mjs` 11 步全过：建房、非房主签发 403、房主签发 201、列表无令牌泄露、只读查看、重复查看、非房主撤销 403、房主撤销 204、列表已撤销、已撤销查看 410。

### 4.3 截图与 DOM 实测

3 张真实截图亲眼验收（`docs/screenshots/share/` 下 share-manage.png、share-manage-issued.png、share-view.png），控制台零错误。分享查看页底部两行以 DOM 实测与文本断言验证。

说明：截图 harness 的 `setContent` 环境为 opaque origin，完整链接显示为相对路径 `/share/…`；真实部署下为实际域名加该路径。`ShareManager` 已做 origin 为 null 时回退相对路径的处理。

### 4.4 验收中发现并修复的两个真问题

1. **网关此前无 OPTIONS 预检处理**：跨域 POST 签发在浏览器里被预检挡住。本轮在 `server.ts` 全局加 OPTIONS 204 处理，响应头为 `Access-Control-Allow-Origin: *`、`Access-Control-Allow-Methods` 含 GET/POST/PATCH/DELETE/OPTIONS、`Access-Control-Allow-Headers: content-type`、`Access-Control-Max-Age: 86400`。新增网关测试 `cors-preflight.test.ts` 2 例。
2. **冒烟脚本 bug**：Node fetch 助手未设 `Content-Length`，导致 DELETE 请求体无帧界定，被网关解析器回 400。修法为显式设 `Content-Length`。浏览器 fetch 本来就带 `Content-Length`，故 Web 撤销不受影响；此为测试脚本 bug，非服务端 bug。

### 4.5 模型链

本轮全部调用走 BotsRouter（入口 `https://api.botsarena.tech/v1`）。智谱 `glm-4.7` 撞上游周/月上限（重置 2026-10-30）后，按优先级切讯飞星辰 `spark-x2.6` 完成全部批次。旧 lane（`zhipu-call.py`、`openrouter-call.py`、`s193-call.py`、`dpsk`）未用。

## 5. 未做与已知局限

- 分享链接仍只读，不能凭链接入群或发消息。
- 查看页不走 WebSocket，靠 15 秒轮询刷新，新消息延迟最高约 15 秒。
- Chat 顶栏按钮过多时在窄视口下会横向溢出（既存布局问题，本轮未改）。
- Web 端的令牌在 opaque origin 下只显示相对路径，无法生成完整可点链接（真实部署正常）。