import Taro from '@tarojs/taro';

// Tab 页不能用 navigateTo 打开（微信会对 tabBar 页直接报错
// "can not navigateTo a tabbar page"），只能用 switchTab；而
// switchTab 不带 query 参数。解读页的 ?dim= 深链因此改走本地
// 存储中转：goInterpret(dim) 先存后切，解读页显示时取走。
const DIM_KEY = 'zw_dim_target';

export function goInterpret(dim?: string) {
  try {
    if (dim) Taro.setStorageSync(DIM_KEY, dim);
    else Taro.removeStorageSync(DIM_KEY);
  } catch {
    // 存储不可用时仍切 Tab，只是丢深链落点，不阻断主流程。
  }
  Taro.switchTab({ url: '/pages/interpret/index' });
}

// 读一次即清除；解读页 chart 为空时不调用（不提前消费）。
export function takeDimTarget(): string | undefined {
  try {
    const v = Taro.getStorageSync(DIM_KEY) as string | undefined;
    if (v) Taro.removeStorageSync(DIM_KEY);
    return v || undefined;
  } catch {
    return undefined;
  }
}

// 首页输入框 → 对话页：问题预填中转（与 goInterpret 的深链模式相同）。
// 首页输入框是真输入框：输入文字后点发送，问题存这里，对话页显示时取走预填；
// 只进对话页不带问题时不存不取。
const HOME_Q_KEY = 'zw_home_question';

export function setHomeQuestion(q: string): void {
  try {
    if (q) Taro.setStorageSync(HOME_Q_KEY, q);
    else Taro.removeStorageSync(HOME_Q_KEY);
  } catch {
    // 储存不可用时仍进对话页，只是丢预填问题，不阻断主流程。
  }
}

export function takeHomeQuestion(): string | undefined {
  try {
    const v = Taro.getStorageSync(HOME_Q_KEY) as string | undefined;
    if (v) Taro.removeStorageSync(HOME_Q_KEY);
    return v || undefined;
  } catch {
    return undefined;
  }
}

// 知识页同样是 Tab 页，只能 switchTab（无深链参数需求）。
export function goKnowledge() {
  Taro.switchTab({ url: '/pages/knowledge/index' });
}

// 我的页同样是 Tab 页：goMine(section) 先存后切，我的页显示时
// 取走并落到对应 section（与 goInterpret 同一模式）。
const MINE_KEY = 'zw_mine_section';

export function goMine(section?: string) {
  try {
    if (section) Taro.setStorageSync(MINE_KEY, section);
    else Taro.removeStorageSync(MINE_KEY);
  } catch {
    // 存储不可用时仍切 Tab，只是丢深链落点，不阻断主流程。
  }
  Taro.switchTab({ url: '/pages/mine/index' });
}

// 读一次即清除；我的页 section 为 main 时不调用（不提前消费）。
export function takeMineSection(): string | undefined {
  try {
    const v = Taro.getStorageSync(MINE_KEY) as string | undefined;
    if (v) Taro.removeStorageSync(MINE_KEY);
    return v || undefined;
  } catch {
    return undefined;
  }
}
