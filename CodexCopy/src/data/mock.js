// CodexCopy 数据 — 按真实 Codex 结构：项目（对应磁盘目录）→ 线程（带 Local/Worktree/Cloud 模式）
// 依据：OpenAI 官方文档 + 2026-07 真机截图 + 评测文章

export const projects = [
  {
    id: 'p1',
    name: 'plugins',
    path: '~/plugins',
    threads: [
      {
        id: 't1',
        title: 'Review email spam patterns',
        mode: 'local',
        branch: 'main',
        status: 'idle',
        model: '5.6 Sol',
        messages: [
          { role: 'user', text: 'Review the email spam patterns in src/filters/' },
          {
            role: 'agent',
            thinking: '先看一下现有的过滤规则。',
            tools: [
              { name: 'read', target: 'src/filters/spam.ts', status: 'ok', output: '→ 120 lines' },
            ],
            text: '看了一下，`spam.ts` 里有 3 条规则。建议：\n\n1. 发件人黑名单支持通配符\n2. 关键词权重可配置\n3. 加一层贝叶斯打分',
          },
        ],
      },
      {
        id: 't2',
        title: 'Note smoke tests need server',
        mode: 'local',
        branch: 'main',
        status: 'idle',
        model: '5.6 Sol',
        messages: [],
      },
      {
        id: 't3',
        title: 'Add spam pattern',
        mode: 'local',
        branch: 'main',
        status: 'idle',
        model: '5.6 Sol',
        messages: [],
      },
      {
        id: 't4',
        title: 'Check spam email patterns',
        mode: 'local',
        branch: 'main',
        status: 'idle',
        model: '5.6 Sol',
        messages: [],
      },
    ],
  },
];

export const models = ['5.6 Sol', '5.6 Terra', '6 Sol'];
export const sandboxModes = ['Suggest', 'Auto Edit', 'Full Auto'];

// 新建线程三模式（官方定义）
export const THREAD_MODES = [
  { id: 'local', name: 'Local', desc: 'Quick edits, debugging — changes happen directly in your working directory' },
  { id: 'worktree', name: 'Worktree', desc: 'Feature work, experiments — isolated git worktree, no conflicts' },
  { id: 'cloud', name: 'Cloud', desc: 'Heavy refactors — runs remotely, frees your machine' },
];
