// CodexCopy 数据 — 按真实 Codex 结构：项目（对应磁盘目录）→ 线程（带 Local/Worktree/Cloud 模式）
// 依据：OpenAI 官方文档 + 2026-07 真机截图 + 评测文章

export const projects = [
  {
    id: 'p1',
    name: 'codex-copy',
    path: '~/workspace/muse-repo/CodexCopy',
    threads: [
      {
        id: 't1',
        title: '给 auth 模块加上 refresh token',
        mode: 'local', // local | worktree | cloud
        branch: 'main',
        status: 'running',
        model: 'gpt-5.2',
        messages: [
          { role: 'user', text: '给 auth 模块加上 refresh token 支持，access token 15 分钟过期后自动用 refresh token 续期' },
          {
            role: 'agent',
            thinking: '用户要在 auth 模块加 refresh token。先看现有结构。',
            tools: [
              { name: 'read', target: 'src/auth/tokens.ts', status: 'ok', output: '→ 读取 84 行\n  - issueAccessToken(user): 签发 15min JWT\n  - 无 refresh 逻辑' },
            ],
            text: '看了一下，`tokens.ts` 里只有 access token 签发。方案：\n\n1. 新增 `issueRefreshToken()`，有效期 7 天\n2. 新增 `POST /auth/refresh` 接口\n3. 中间件过期返回 401，客户端自动续期\n\n开始改：',
          },
          {
            role: 'agent',
            needsApproval: true,
            approval: { title: 'Edit src/auth/tokens.ts', desc: '新增 issueRefreshToken + rotateRefreshToken，共 12 行' },
            tools: [
              { name: 'edit', target: 'src/auth/tokens.ts', status: 'ok', output: '+ export function issueRefreshToken(userId) {\n+   return jwt.sign({ sub: userId }, SECRET, { expiresIn: \'7d\' });\n+ }' },
            ],
            text: '改好了，需要你确认一下这个编辑：',
          },
        ],
      },
      {
        id: 't2',
        title: '重构实验分支的鉴权',
        mode: 'worktree',
        branch: 'feat/auth-v2',
        status: 'running',
        model: 'gpt-5.2',
        messages: [
          { role: 'user', text: '在 worktree 里重构鉴权模块，别碰我本地的 main' },
          {
            role: 'agent',
            text: '已在独立 worktree（`feat/auth-v2`，detached HEAD）里开工，你本地的 main 不受影响。改完你可以用 Handoff 切回 Local 继续。',
          },
        ],
      },
    ],
  },
  {
    id: 'p2',
    name: 'botstalk',
    path: '~/workspace/botstalk',
    threads: [
      {
        id: 't3',
        title: '重型重构放云端跑',
        mode: 'cloud',
        branch: 'main',
        status: 'completed',
        model: 'gpt-5.2',
        messages: [
          { role: 'user', text: '把 protocol 包的重构放云端跑，别占我机器' },
          {
            role: 'agent',
            text: '已提交到云端环境跑，跑完通知你。本地机器零占用。',
            tools: [{ name: 'bash', target: 'npm test', status: 'ok', output: '✓ 48 passed' }],
          },
        ],
      },
    ],
  },
];

export const models = ['gpt-5.2', 'gpt-5.1', 'gpt-5-mini'];
export const sandboxModes = ['Suggest', 'Auto Edit', 'Full Auto'];

// 新建线程三模式（官方定义）
export const THREAD_MODES = [
  { id: 'local', name: 'Local', desc: 'Quick edits, debugging — changes happen directly in your working directory' },
  { id: 'worktree', name: 'Worktree', desc: 'Feature work, experiments — isolated git worktree, no conflicts' },
  { id: 'cloud', name: 'Cloud', desc: 'Heavy refactors — runs remotely, frees your machine' },
];
