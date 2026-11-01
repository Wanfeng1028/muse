import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import './index.scss';

// Floating iOS-style tab bar (WeChat custom tabBar).
// WeChat creates a fresh instance per tab page, so the selected tab is
// derived from the current route on mount — no cross-page setState sync.
//
// Icons are pure View shapes, NOT image imports: Taro inlines small
// imported images as base64 inside the custom-tab-bar bundle, and WeChat
// <image> cannot display base64 data URIs (documented Taro pitfall).
// The v3 tabBar PNGs are also unusable here — they are opaque squares
// painted on the old dark bar background (#111518), not transparent
// glyphs. Vector shapes sidestep both traps and tint to any theme color.
const TABS = [
  { path: 'pages/index/index', text: '首页', glyph: 'house' },
  { path: 'pages/interpret/index', text: '解读', glyph: 'chat' },
  { path: 'pages/knowledge/index', text: '知识', glyph: 'book' },
  { path: 'pages/mine/index', text: '我的', glyph: 'person' },
] as const;
const LIGHT_PAGES = ['pages/knowledge/index', 'pages/mine/index'];

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

// 46x46 box, 2pt stroke. Outline = inactive, filled = active.
// Border colors are set per side inline (classes only fix geometry);
// the shared trick: filled shapes use backgroundColor, outline shapes
// use border colors, never both from one shorthand.
function TabIcon({ glyph, active, color, cut }: { glyph: string; active: boolean; color: string; cut: string }) {
  if (glyph === 'house') {
    return (
      <View className='ticon'>
        {active
          ? <View className='ticon-part ticon-house-roof-fill' style={{ borderBottomColor: color }} />
          : <View className='ticon-part ticon-house-roof' style={{ borderTopColor: color, borderLeftColor: color }} />}
        {active
          ? <View className='ticon-part ticon-house-body-fill' style={{ backgroundColor: color }} />
          : <View className='ticon-part ticon-house-body' style={{ borderLeftColor: color, borderRightColor: color, borderBottomColor: color }} />}
      </View>
    );
  }
  if (glyph === 'chat') {
    return (
      <View className='ticon'>
        <View
          className='ticon-part ticon-chat-bubble'
          style={active ? { backgroundColor: color, borderColor: 'transparent' } : { borderColor: color }}
        />
        <View className='ticon-part ticon-chat-tail' style={{ borderTopColor: color }} />
      </View>
    );
  }
  if (glyph === 'book') {
    return (
      <View className='ticon'>
        <View
          className='ticon-part ticon-book-body'
          style={active ? { backgroundColor: color, borderColor: 'transparent' } : { borderColor: color }}
        />
        <View className='ticon-part ticon-book-spine' style={{ backgroundColor: active ? cut : color }} />
      </View>
    );
  }
  return (
    <View className='ticon'>
      <View
        className='ticon-part ticon-person-head'
        style={active ? { backgroundColor: color, borderColor: 'transparent' } : { borderColor: color }}
      />
      <View
        className='ticon-part ticon-person-body'
        style={active
          ? { backgroundColor: color, borderTopColor: 'transparent', borderLeftColor: 'transparent', borderRightColor: 'transparent' }
          : { borderTopColor: color, borderLeftColor: color, borderRightColor: color }}
      />
    </View>
  );
}

export default function CustomTabBar() {
  const [selected, setSelected] = useState(0);
  const [light, setLight] = useState(false);

  // Derive on BOTH mount and show. Mount covers same-page remounts
  // (mine section switches create a fresh bar instance with no show
  // event); show covers tab switches where mount can precede the route
  // update. Both run the same derivation; the later one wins.
  const derive = () => {
    const path = currentPath();
    const idx = TABS.findIndex((t) => path.includes(t.path));
    if (idx >= 0) {
      setSelected(idx);
      setLight(LIGHT_PAGES.includes(TABS[idx].path));
    }
  };
  useEffect(derive, []);
  // useDidShow, not mount-only useEffect: after a tab switch the new
  // page can mount before the router path updates, which froze the bar
  // on the previous tab's variant. Show fires after the route settles.
  useDidShow(derive);

  const activeColor = light ? '#6d28d9' : '#f5f5f7';
  const cut = light ? '#ffffff' : '#1e1f23';
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
            <TabIcon glyph={t.glyph} active={active} color={active ? activeColor : '#9a9ba2'} cut={cut} />
            <Text className={active ? 'floatbar-label floatbar-label-active' : 'floatbar-label'}>{t.text}</Text>
          </View>
        );
      })}
    </View>
  );
}
