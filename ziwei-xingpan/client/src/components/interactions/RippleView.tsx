import { View } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import './interactions.scss';

let rippleCounter = 0;

type Ripple = { id: number; x: number; y: number; size: number; centered: boolean };

/**
 * RippleView：点击水波纹容器。
 * 波纹从触点扩散、松手后淡出。触点坐标：H5 鼠标用 currentTarget 的
 * getBoundingClientRect 同步算；小程序 touch 用 createSelectorQuery 量到的
 * 容器 rect 算；rect 未就绪时退化为容器中心扩散（不丢波纹）。
 * 另接 onClick 坐标路径，覆盖 H5 鼠标点击；touch 后 600ms 内的跟随 click
 * 会被去重，避免一次点按出两个波纹。
 */
export function RippleView({ children, className, rippleColor = 'rgba(255, 255, 255, 0.35)' }: {
  children: ReactNode;
  className?: string;
  rippleColor?: string;
}) {
  const [ripples, setRipples] = useState<Ripple[]>([]);
  const rectRef = useRef<{ left: number; top: number; width: number; height: number } | null>(null);
  const lastTouchRef = useRef(0);
  const idRef = useRef('');
  if (!idRef.current) { rippleCounter += 1; idRef.current = 'ripple-view-' + rippleCounter; }
  const viewId = idRef.current;

  useEffect(() => {
    const q = Taro.createSelectorQuery();
    q.select('#' + viewId).boundingClientRect((r: any) => {
      if (r && r.width) rectRef.current = { left: r.left, top: r.top, width: r.width, height: r.height };
    }).exec();
  }, [viewId]);

  const spawn = useCallback((clientX: number, clientY: number) => {
    const rect = rectRef.current;
    let ripple: Ripple;
    if (rect) {
      const size = Math.max(rect.width, rect.height) * 2.2;
      ripple = { id: Date.now() + Math.random(), x: clientX - rect.left, y: clientY - rect.top, size, centered: false };
    } else {
      ripple = { id: Date.now() + Math.random(), x: 0, y: 0, size: 320, centered: true };
    }
    setRipples((prev) => [...prev, ripple]);
    setTimeout(() => setRipples((prev) => prev.filter((r) => r.id !== ripple.id)), 700);
  }, []);

  const onTouchStart = useCallback((e: any) => {
    lastTouchRef.current = Date.now();
    const t = e.touches && e.touches[0];
    if (!t) return;
    // H5 上 currentTarget 就是 DOM 节点，可同步拿到 rect；小程序走缓存 rect。
    const el = e.currentTarget;
    if (el && typeof el.getBoundingClientRect === 'function') {
      const r = el.getBoundingClientRect();
      rectRef.current = { left: r.left, top: r.top, width: r.width, height: r.height };
    }
    spawn(t.clientX, t.clientY);
  }, [spawn]);

  const onClick = useCallback((e: any) => {
    if (Date.now() - lastTouchRef.current < 600) return;
    const el = e.currentTarget;
    if (el && typeof el.getBoundingClientRect === 'function') {
      const r = el.getBoundingClientRect();
      rectRef.current = { left: r.left, top: r.top, width: r.width, height: r.height };
    }
    if (typeof e.clientX === 'number') spawn(e.clientX, e.clientY);
  }, [spawn]);

  return (
    <View id={viewId} className={'ripple-view ' + (className || '')} onTouchStart={onTouchStart} onClick={onClick}>
      {children}
      {ripples.map((r) => (
        <View
          key={r.id}
          className='ripple-circle'
          style={{
            width: r.size + 'px',
            height: r.size + 'px',
            left: r.centered ? '50%' : r.x + 'px',
            top: r.centered ? '50%' : r.y + 'px',
            background: rippleColor,
          }}
        />
      ))}
    </View>
  );
}
