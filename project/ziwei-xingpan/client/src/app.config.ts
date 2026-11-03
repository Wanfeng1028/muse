export default {
  pages: [
    'pages/index/index',
    'pages/chart/index',
    'pages/interpret/index',
    'pages/knowledge/index',
    'pages/mine/index',
    'pages/auth/index',
    'pages/demo/index',
    // Birth form (source BirthForm) + compare (source heming, two charts).
    'pages/birth/index',
    'pages/compare/index',
    // Chat-agent round (2026-11-01): profiles (命例库) + chat (轻量纯对话)
    // + persona (人格形象) + annual (年度运势).
    'pages/profiles/index',
    'pages/chat/index',
    'pages/persona/index',
    'pages/annual/index',
    // Welcome splash (2026-11-02 user order): shown on first launch
    // when no local login marker exists (see home mount-only guard).
    'pages/welcome/index',
  ],
  tabBar: {
    // 2026-11-02 rule 9: the floating custom pill is gone (it was
    // position:fixed). Native tabBar renders from this list; icons
    // are the central Lucide PNGs (gray unselected, Gemini blue
    // selected). Dark-mode colors follow via lib/theme setTabBarStyle.
    color: '#9a9ba2',
    selectedColor: '#346bf0',
    backgroundColor: '#f5f6f8',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/index/index', text: '首页', iconPath: 'assets/lucide/png/home-gray.png', selectedIconPath: 'assets/lucide/png/home-blue.png' },
      { pagePath: 'pages/interpret/index', text: '解读', iconPath: 'assets/lucide/png/message-circle-gray.png', selectedIconPath: 'assets/lucide/png/message-circle-blue.png' },
      { pagePath: 'pages/knowledge/index', text: '知识', iconPath: 'assets/lucide/png/book-open-gray.png', selectedIconPath: 'assets/lucide/png/book-open-blue.png' },
      { pagePath: 'pages/mine/index', text: '我的', iconPath: 'assets/lucide/png/user-gray.png', selectedIconPath: 'assets/lucide/png/user-blue.png' },
    ],
  },
  window: {
    backgroundTextStyle: 'light',
    backgroundColor: '#f5f6f8',
    navigationBarBackgroundColor: '#f5f6f8',
    navigationBarTextStyle: 'black',
    navigationBarTitleText: '星命盘',
  },
};
