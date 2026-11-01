export default {
  pages: [
    'pages/index/index',
    'pages/chart/index',
    'pages/interpret/index',
    'pages/knowledge/index',
    'pages/mine/index',
    'pages/demo/index',
  ],
  tabBar: {
    color: '#9a9ba2',
    selectedColor: '#f5f5f7',
    backgroundColor: '#111518',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/index/index', text: '首页', iconPath: 'assets/tabbar/home.png', selectedIconPath: 'assets/tabbar/home-active.png' },
      { pagePath: 'pages/interpret/index', text: '解读', iconPath: 'assets/tabbar/chat.png', selectedIconPath: 'assets/tabbar/chat-active.png' },
      { pagePath: 'pages/knowledge/index', text: '知识', iconPath: 'assets/tabbar/book.png', selectedIconPath: 'assets/tabbar/book-active.png' },
      { pagePath: 'pages/mine/index', text: '我的', iconPath: 'assets/tabbar/mine.png', selectedIconPath: 'assets/tabbar/mine-active.png' },
    ],
  },
  window: {
    backgroundTextStyle: 'dark',
    navigationBarBackgroundColor: '#111518',
    navigationBarTextStyle: 'white',
    navigationBarTitleText: '紫微星盘',
  },
};
