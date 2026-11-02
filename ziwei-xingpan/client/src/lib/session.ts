import Taro from '@tarojs/taro';

// 登录标记（2026-11-02 用户定：登录后进首页）:微信登录成功后写入，
// 首页冷启动守夜读它——已登录不推欢迎页，未登录推欢迎页。
// 注意：云开发未配置时真实登录走不通，标记也就写不上；联调后才生效。
const LOGIN_KEY = 'zw_login';

export function setLoginFlag(): void {
  try {
    Taro.setStorageSync(LOGIN_KEY, '1');
  } catch {
    // 储存不可用时不阻断登录流程。
  }
}

export function hasLoginFlag(): boolean {
  try {
    return Taro.getStorageSync(LOGIN_KEY) === '1';
  } catch {
    return false;
  }
}
