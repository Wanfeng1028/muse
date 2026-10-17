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
        messages: [],
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

export const models = ['5.6 Sol', '5.6 Sol High', '5.1']; 
export const sandboxModes = ['Suggest', 'Auto Edit', 'Full Auto'];

// 新建线程三模式（官方定义）
export const THREAD_MODES = [
  { id: 'local', name: 'Local', desc: 'Quick edits, debugging — changes happen directly in your working directory' },
  { id: 'worktree', name: 'Worktree', desc: 'Feature work, experiments — isolated git worktree, no conflicts' },
  { id: 'cloud', name: 'Cloud', desc: 'Heavy refactors — runs remotely, frees your machine' },
];
