export default {
  pages: [
    'pages/index/index',
    'pages/chart/index',
    'pages/interpret/index',
    'pages/knowledge/index',
    'pages/mine/index',
  ],
  tabBar: {
    color: '#6b6c72',
    selectedColor: '#17181c',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/index/index', text: '首页' },
      { pagePath: 'pages/interpret/index', text: '解读' },
      { pagePath: 'pages/knowledge/index', text: '知识' },
      { pagePath: 'pages/mine/index', text: '我的' },
    ],
  },
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTextStyle: 'black',
    navigationBarTitleText: '紫微星盘',
  },
};
