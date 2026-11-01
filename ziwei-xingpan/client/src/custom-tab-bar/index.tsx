import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Icon, type IconName } from '../components/icons';
import { getTheme, type Theme } from '../lib/theme';
import './index.scss';

// Floating iOS-style tab bar (WeChat custom tabBar).
// WeChat creates a fresh instance per tab page, so the selected tab is
// derived from the current route on mount — no cross-page setState sync.
// Variant follows the theme setting (light default), NOT the page: the
// old LIGHT_PAGES list froze the bar to the wrong variant whenever a
// dark page sat next to a light one.
//
// Icons are Lucide PNGs (see components/icons.tsx): WeChat <image>
// cannot render SVG, and Taro's default base64 inlining of small
// images is disabled for this project (config imageUrlLoaderOption),
// so imported PNG files resolve to real package files.
const TABS: Array<{ path: string; text: string; icon: IconName }> = [
  { path: 'pages/index/index', text: '首页', icon: 'home' },
  { path: 'pages/interpret/index', text: '解读', icon: 'message-circle' },
  { path: 'pages/knowledge/index', text: '知识', icon: 'book-open' },
  { path: 'pages/mine/index', text: '我的', icon: 'user' },
];

function currentPath(): string {
  // Taro's router/page objects are loosely typed; any is the API's own
  // shape here, guarded by try/catch so a missing router never throws.
  try {
    const p = (Taro.getCurrentInstance() as any)?.router?.path;
    if (p) return String(p);
  } catch { /* fall through */ }
  try {
    const pages = Taro.getCurrentPages() as any[];
    const last = pages[pages.length - 1];
    if (last) return String(last.route || last.path || last?.$router?.path || '');
  } catch { /* fall through */ }
  return '';
}

export default function CustomTabBar() {
  const [selected, setSelected] = useState(0);
  const [theme, setTheme] = useState<Theme>('light');

  // Derive on BOTH mount and show. Mount covers same-page remounts
  // (mine section switches create a fresh bar instance with no show
  // event); show covers tab switches where mount can precede the route
  // update. Both run the same derivation; the later one wins.
  const derive = () => {
    const path = currentPath();
    const idx = TABS.findIndex((t) => path.includes(t.path));
    if (idx >= 0) setSelected(idx);
    setTheme(getTheme());
  };
  useEffect(derive, []);
  // useDidShow, not mount-only useEffect: after a tab switch the new
  // page can mount before the router path updates, which froze the bar
  // on the previous tab's variant. Show fires after the route settles.
  useDidShow(derive);

  const light = theme === 'light';
  return (
    <View className={light ? 'floatbar floatbar-light' : 'floatbar floatbar-dark'}>
      {TABS.map((t, i) => {
        const active = i === selected;
        return (
          <View
            key={t.path}
            className='floatbar-item'
            onClick={() => { if (!active) Taro.switchTab({ url: '/' + t.path }); }}
          >
            <Icon
              name={t.icon}
              tone={active ? (light ? 'blue' : 'sky') : 'gray'}
              size='46px'
            />
            <Text className={active ? 'floatbar-label floatbar-label-active' : 'floatbar-label'}>{t.text}</Text>
          </View>
        );
      })}
    </View>
  );
}
