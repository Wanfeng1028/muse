# OpenAgents 第 10 轮：只读分享链接

## 1. 原版规格

- 清单第 12 项：“邀请链接 + 免安装只读查看”。
- Workspace 可生成邀请链接拉人进群。
- 查看方无需安装任何东西，浏览器打开即只读围观。
- 许可证：Apache-2.0。
- botstalk 为 TS 原生重实现。

## 2. 本轮设计决策

- 令牌：32 位字母数字，Math.random 按字符表抽取（与 pairing 码同风格，random 可注入）。
- 存储：库里只存令牌的 sha256 哈希，不落明文。
- 一次性返回：明文令牌只在签发响应中返回一次，此后任何端点都不再给出。
- 有效期：默认 168 小时（7 天），可按需指定并钳制在 1–720 小时。
- 权限：签发与吊销只允许房主/管理员（canManageRoom）。
- 查看端点只读：不写库、不加成员、不发广播。
- 错误码：INVALID_SHARE_TOKEN 400 / SHARE_LINK_NOT_FOUND 404 / SHARE_LINK_REVOKED 410 / SHARE_LINK_EXPIRED 410。
- Web 查看页路由：#/share/ 加 32 位令牌。

## 3. 交付

- gateway/src/share.ts：令牌生成、sha256 哈希、有效期钳制、ShareLinkRecord 判定（吊销/过期）。
- gateway/src/db.ts：share_links 表 DDL + 5 个函数（建链接、按哈希查、按房间列表、吊销、按 ID 查）。
- gateway/src/server.ts：4 个端点——签发（POST）、列表（GET）、吊销（DELETE）、只读查看（GET /api/share/:token）。
- web/src/components/ShareView.tsx：只读查看页（房间名、话题、只读横条、消息列表，无输入框）。
- web/src/api.ts：新增 fetchShareView。
- web/src/App.tsx：新增 #/share/<token> 路由分支。

## 4. 验收

- share.test.ts 20/20 通过。
- 网关全量 73 个测试文件、962 例全绿。
- 网关源码 tsc 全洁。
- Web tsc -b 与 vite build 通过。
- 真实网关冒烟：建房 201、签发 201、WS 发 2 条消息、GET /api/share 200 且 messages 2 条。
- 截图 docs/screenshots/share-view.png 亲眼验收：房间名/话题/只读横条/2 条消息齐全，无输入框，控制台零错误。

验收抓出的真 bug：

1. db 行 snake_case 直接传给驼峰 Record 判定，致新链接查看 410 —— 修法：服务端映射成 ShareLinkRecord 再判定。
2. B4 测试稿编造签名 —— 按 B2 真实签名机械修正。
3. GET 列表稿引用不存在的 searchParams —— 改为 new URL 取 requester。
4. GET 分享稿把 RoomRow 对象传给 getRoomHistory —— 改为传 row.room。
5. B2 漏交建表 DDL —— 按 pairing_codes 样式机械补齐。
6. 截图 harness：setContent 下 location.hash 读不到且 goto 本地网关被 Chromium Local Network Access 拦截 —— 最终用 setContent 加解析前经典脚本 replaceState 写 hash 解决。

## 5. 未做与已知局限

- 分享链接不能凭链接入群/发消息：只读 scope 为有意为之。
- Web 端签发/管理 UI 未做：本轮只走 REST。
- 查看页不实时刷新。
- test tsc 在未动文件里有既存错误（better-sqlite3 缺失、pairing/werewolf 旧测试类型错），本轮未动；vitest 全绿不受影响。
