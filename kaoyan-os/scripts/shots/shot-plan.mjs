export const defaultShotPlan = [
  {
    name: '仪表盘',
    route: '/',
    waitFor: '.stat-card',
    shotName: 'dashboard.png',
  },
  {
    name: '复习计划（浅色）',
    route: '/plans',
    waitFor: '.plans-list-item',
    shotName: 'plans-light.png',
  },
  {
    name: '复习计划（深色）',
    route: '/plans',
    waitFor: '.plans-list-item',
    actions: [{ click: '.theme-toggle', waitMs: 800 }],
    shotName: 'plans-dark.png',
  },
  {
    name: '错题本',
    route: '/mistakes',
    waitFor: '.mistakes-item',
    actions: [{ click: '.theme-toggle', waitMs: 800 }],
    shotName: 'mistakes.png',
  },
  {
    name: '单词',
    route: '/words',
    waitFor: '.words-table',
    shotName: 'words.png',
  },
  {
    name: '真题记录',
    route: '/exams',
    waitFor: '.exams-table',
    shotName: 'exams.png',
  },
  {
    name: '自律热力图',
    route: '/heatmap',
    waitFor: '.hm-grid',
    actions: [{ clickLast: '.hm-cell.hm-clickable', waitMs: 900 }],
    shotName: 'heatmap.png',
  },
  {
    name: '周报',
    route: '/weekly',
    waitFor: '.wk-stat-grid',
    shotName: 'weekly.png',
  },
  {
    name: '数据导入导出',
    route: '/data',
    waitFor: '.data-transfer-page',
    shotName: 'data-transfer.png',
  },
];
