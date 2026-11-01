// Theme: light by default, dark kept as a settings toggle.
// Stored under 'zw-theme' (Taro storage; on H5 this is localStorage).
// getTheme() is the single source of truth; pages call useTheme() and
// re-read on show (tab switches remount pages without a shared store).
// Screenshot override (H5 only, never on weapp): the preview harness
// sets window.__ZW_THEME__ before page scripts run to force a theme
// for dark-mode comparison shots.
import { useState } from 'react';
import Taro, { useDidShow } from '@tarojs/taro';

export type Theme = 'light' | 'dark';
const KEY = 'zw-theme';

export function getTheme(): Theme {
  try {
    if (Taro.getEnv() === Taro.ENV_TYPE.WEB) {
      const forced = (window as unknown as { __ZW_THEME__?: string }).__ZW_THEME__;
      if (forced === 'dark' || forced === 'light') return forced;
    }
  } catch { /* fall through to storage */ }
  try {
    return Taro.getStorageSync(KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function setTheme(t: Theme): void {
  try { Taro.setStorageSync(KEY, t); } catch { /* storage unavailable: theme stays for this session only */ }
}

// Native tabBar style follows the theme (2026-11-02 rule 9: the custom
// floating pill is gone, so the native bar must carry both modes).
// Defensive: any platform without setTabBarStyle (or called on a
// non-tab page) just skips; the static app.config colors stay.
export function applyTabBarStyle(t: Theme): void {
  try {
    const p = Taro.setTabBarStyle(t === 'dark' ? {
      backgroundColor: '#1e1f23', borderStyle: 'black', color: '#9a9ba2', selectedColor: '#8db4ff',
    } : {
      backgroundColor: '#f5f6f8', borderStyle: 'white', color: '#9a9ba2', selectedColor: '#346bf0',
    }) as unknown as Promise<unknown> | undefined;
    if (p && typeof p.catch === 'function') p.catch(() => {});
  } catch { /* no tabBar on this page/platform */ }
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(getTheme());
  useDidShow(() => { setThemeState(getTheme()); applyTabBarStyle(getTheme()); });
  const apply = (t: Theme) => { setTheme(t); setThemeState(t); applyTabBarStyle(t); };
  return [theme, apply];
}
