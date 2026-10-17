// CodexCopy mock 数据 — 按 Codex 真实三栏结构：任务列表(左) + 会话(中) + 多功能区(右)
// 界面指南依据：web-tutorial.com/codex/app-interface.html

export const projects = [
  { id: 'p1', name: 'codex-copy', path: '~/workspace/muse-repo/CodexCopy', branch: 'main' },
  { id: 'p2', name: 'botstalk', path: '~/workspace/botstalk', branch: 'main' },
];

// 任务状态：running | awaiting | completed | failed | cancelled
export const tasks = [
  {
    id: 't1',
    projectId: 'p1',
    title: '给 auth 模块加上 refresh token',
    status: 'running',
    model: 'gpt-5.2',
    sandbox: 'Auto Edit',
    branch: 'main',
    worktree: 'local',
    files: [
      { name: 'src/auth/tokens.ts', modified: true },
      { name: 'src/auth/middleware.ts', modified: true },
      { name: 'src/auth/index.ts', modified: false },
    ],
    terminal: [
      { cmd: 'npm test -- auth', out: '✓ 12 passed\n✓ 0 failed' },
    ],
    messages: [
      { role: 'user', text: '给 auth 模块加上 refresh token 支持，access token 15 分钟过期后自动用 refresh token 续期' },
      {
        role: 'agent',
        thinking: '用户要在 auth 模块加 refresh token。我先看看现有 auth 模块的结构。',
        tools: [
          { name: 'read', target: 'src/auth/tokens.ts', status: 'ok', output: '→ 读取 84 行\n  - issueAccessToken(user): 签发 15min JWT\n  - 无 refresh 逻辑' },
        ],
        text: '看了一下，`tokens.ts` 里只有 access token 签发。我的方案：\n\n1. 新增 `issueRefreshToken()`，有效期 7 天\n2. 新增 `POST /auth/refresh` 接口\n3. 中间件过期返回 401，客户端自动续期\n\n开始改：',
      },
      {
        role: 'agent',
        needsApproval: true,
        approval: { title: 'Edit src/auth/tokens.ts', desc: '新增 issueRefreshToken + rotateRefreshToken，共 12 行' },
        tools: [
          { name: 'edit', target: 'src/auth/tokens.ts', status: 'ok', output: '+ export function issueRefreshToken(userId: string) {\n+   return jwt.sign({ sub: userId, type: \'refresh\' }, SECRET, { expiresIn: \'7d\' });\n+ }' },
        ],
        text: '改好了，需要你确认一下这个编辑：',
      },
    ],
  },
  {
    id: 't2',
    projectId: 'p1',
    title: '修 dashboard 白屏问题',
    status: 'awaiting',
    model: 'gpt-5.2',
    sandbox: 'Suggest',
    branch: 'main',
    worktree: 'local',
    files: [{ name: 'scripts/deploy.sh', modified: true }],
    terminal: [],
    messages: [
      { role: 'user', text: '生产环境 dashboard 白屏，console 报 ChunkLoadError，帮我看看' },
      {
        role: 'agent',
        text: '找到原因了：`dist/assets` 里残留着上个版本的 chunk，CDN 缓存的旧 `index.html` 还在引用它。\n\n建议：部署脚本加 `rm -rf dist` 全量清理，`index.html` 设 `no-cache`。',
        needsApproval: true,
        approval: { title: 'Edit scripts/deploy.sh', desc: '部署前清理 dist，index.html 设 no-cache' },
      },
    ],
  },
  {
    id: 't3',
    projectId: 'p2',
    title: '用 SQLite 给 CLI 加历史记录',
    status: 'completed',
    model: 'gpt-5.1',
    sandbox: 'Full Auto',
    branch: 'main',
    worktree: 'local',
    files: [{ name: 'src/history.ts', modified: true }],
    terminal: [{ cmd: 'npm test -- history', out: '✓ 3 passed' }],
    messages: [
      { role: 'user', text: '给这个 CLI 工具加个历史记录功能，用 SQLite 存' },
      {
        role: 'agent',
        text: '做完了：`history` 表 + 写入逻辑 + 上下键翻看，测试全过。',
        tools: [{ name: 'bash', target: 'npm test -- history', status: 'ok', output: '✓ 3 passed' }],
      },
    ],
  },
];

export const models = ['gpt-5.2', 'gpt-5.1', 'gpt-5-mini'];
export const sandboxModes = ['Suggest', 'Auto Edit', 'Full Auto'];
