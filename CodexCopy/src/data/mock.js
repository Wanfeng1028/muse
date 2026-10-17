// CodexCopy mock 数据 — 按逆向确认的项目中心结构组织
// 证据： "Add a project to use Codex" / "Choose project for new chats" /
//       "This remote folder will appear as its own project in the sidebar"

export const projects = [
  {
    id: 'p1',
    name: 'codex-copy',
    path: '~/workspace/muse-repo/CodexCopy',
    branch: 'main',
    chats: [
      {
        id: 't1',
        title: '给 auth 模块加上 refresh token',
        updated: '今天',
        model: 'gpt-5.2',
        status: 'working',
        messages: [
          { role: 'user', text: '给 auth 模块加上 refresh token 支持，access token 15 分钟过期后自动用 refresh token 续期' },
          {
            role: 'agent',
            thinking: '用户要在 auth 模块加 refresh token。我先看看现有 auth 模块的结构，\n找到 token 签发和校验的位置，再设计续期流程。',
            tools: [
              { name: 'read', target: 'src/auth/tokens.ts', status: 'ok', output: '→ 读取 84 行\n  - issueAccessToken(user): 签发 15min JWT\n  - verifyToken(token): 校验中间件\n  - 无 refresh 逻辑' },
              { name: 'read', target: 'src/auth/middleware.ts', status: 'ok', output: '→ 读取 42 行\n  - authenticate: 从 Authorization 头解析 token' },
            ],
            text: '看了一下，`tokens.ts` 里只有 access token 签发，没有 refresh 机制。我的方案：\n\n1. 新增 `issueRefreshToken()`，有效期 7 天，httpOnly cookie 下发\n2. 新增 `POST /auth/refresh` 接口，用 refresh token 换新的 access token\n3. 中间件里 access token 过期时返回 401 + `token_expired`，客户端拦截后自动调 refresh 重试\n\n开始改：',
          },
          {
            role: 'agent',
            tools: [
              {
                name: 'edit', target: 'src/auth/tokens.ts', status: 'ok',
                output: '+ export function issueRefreshToken(userId: string) {\n+   return jwt.sign({ sub: userId, type: \'refresh\' }, SECRET, { expiresIn: \'7d\' });\n+ }\n+\n+ export async function rotateRefreshToken(old: string) {\n+   const payload = verifyRefresh(old);\n+   await revokeToken(old); // refresh token 一次性使用\n+   return issueRefreshToken(payload.sub);\n+ }',
              },
            ],
            text: '`tokens.ts` 改好了，refresh token 一次性轮换，防重放。接着加接口和中间件逻辑。',
          },
        ],
      },
      {
        id: 't2',
        title: '修 dashboard 白屏问题',
        updated: '今天',
        model: 'gpt-5.2',
        status: 'done',
        messages: [
          { role: 'user', text: '生产环境 dashboard 白屏，console 报 ChunkLoadError，帮我看看' },
          {
            role: 'agent',
            thinking: 'ChunkLoadError 通常是前端 chunk 加载失败。可能原因：\n1. CDN 缓存了旧的 index.html，引用了已删除的 chunk\n2. 部署时 chunk 哈希变化但 HTML 没更新\n先查构建配置和部署流程。',
            tools: [
              { name: 'bash', target: 'ls dist/assets | head', status: 'ok', output: 'index-a1b2c3.js\nindex-d4e5f6.js   <- 旧 chunk 还在\nvendor-9f8e7d.js' },
            ],
            text: '找到原因了：`dist/assets` 里残留着上个版本的 chunk（`index-d4e5f6.js`），CDN 边缘节点缓存的旧 `index.html` 还在引用它，但源站部署时被删了。\n\n修法：部署脚本里加 `rm -rf dist` 全量清理后再构建，避免增量残留。另外给 CDN 的 `index.html` 设置 `no-cache`。',
          },
        ],
      },
    ],
  },
  {
    id: 'p2',
    name: 'botstalk',
    path: '~/workspace/botstalk',
    branch: 'main',
    chats: [
      {
        id: 't3',
        title: '用 SQLite 给 CLI 加历史记录',
        updated: '昨天',
        model: 'gpt-5.1',
        status: 'done',
        messages: [
          { role: 'user', text: '给这个 CLI 工具加个历史记录功能，用 SQLite 存，支持上下键翻看' },
          {
            role: 'agent',
            text: '好，用 `better-sqlite3`，表结构一行搞定：\n\n```sql\nCREATE TABLE IF NOT EXISTS history (\n  id INTEGER PRIMARY KEY,\n  cmd TEXT NOT NULL,\n  cwd TEXT NOT NULL,\n  created_at INTEGER NOT NULL\n);\n```\n\n做了三件事：命令执行后写入、启动时读最近 500 条、readline 接上下键。跑下测试确认。',
            tools: [
              { name: 'bash', target: 'npm test -- history', status: 'ok', output: '✓ 写入 3 条命令并按时间倒序读出\n✓ 上下键翻看不越界\n✓ 500 条上限淘汰最旧\n\n3 passed' },
            ],
          },
        ],
      },
    ],
  },
  {
    id: 'p3',
    name: 'spark',
    path: '~/workspace/spark',
    branch: 'feature/mobile',
    chats: [
      {
        id: 't4',
        title: 'review PR #428 的并发改动',
        updated: '过去 7 天',
        model: 'gpt-5.2',
        status: 'done',
        messages: [
          { role: 'user', text: 'review 一下 PR #428，重点看并发那块有没有 race' },
          {
            role: 'agent',
            thinking: '先拉 PR diff，重点看新增的并发代码：锁、channel、goroutine 生命周期。',
            tools: [
              { name: 'bash', target: 'gh pr diff 428 --stat', status: 'ok', output: ' worker/pool.go      | 120 +++++++++++++++\n worker/dispatch.go  |  45 ++++++\n 2 files changed' },
            ],
            text: '看完 diff，`pool.go` 里有个真 race：\n\n`dispatch.go:31` 的 `active++` 和 `pool.go:87` 的 `active--` 不在同一把锁里，高并发下计数会漂。修法很简单——把计数器收拢到 pool 内部用 mutex 保护，或者直接换 `atomic.Int32`。\n\n其他部分没问题，channel 关闭顺序是对的。',
          },
        ],
      },
    ],
  },
];

export const suggestions = [
  { title: '解释这段代码', desc: '选中仓库里的代码，让 Codex 讲讲它在干嘛' },
  { title: '修一个 bug', desc: '贴报错信息，Codex 定位并修复' },
  { title: '写个新功能', desc: '描述需求，Codex 设计并实现' },
  { title: 'Review PR', desc: '看看改动有没有问题，给出意见' },
];

export const models = ['gpt-5.2', 'gpt-5.1', 'gpt-5-mini'];
