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
  ],
  tabBar: {
    custom: true,
    // List kept for compatibility (WeChat requires list items even with a
    // custom tabBar); the floating pill in src/custom-tab-bar/ is what
    // actually renders, with Lucide PNG icons (not the old PNGs below,
    // which are opaque squares painted on #111518 and only fit the old
    // native dark bar).
    color: '#9a9ba2',
    selectedColor: '#346bf0',
    backgroundColor: '#f5f6f8',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/index/index', text: '首页', iconPath: 'assets/tabbar/home.png', selectedIconPath: 'assets/tabbar/home-active.png' },
      { pagePath: 'pages/interpret/index', text: '解读', iconPath: 'assets/tabbar/chat.png', selectedIconPath: 'assets/tabbar/chat-active.png' },
      { pagePath: 'pages/knowledge/index', text: '知识', iconPath: 'assets/tabbar/book.png', selectedIconPath: 'assets/tabbar/book-active.png' },
      { pagePath: 'pages/mine/index', text: '我的', iconPath: 'assets/tabbar/mine.png', selectedIconPath: 'assets/tabbar/mine-active.png' },
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
