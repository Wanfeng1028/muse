import { View } from '@tarojs/components';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import './interactions.scss';

type Particle = { id: number; angle: number; dist: number; size: number; color: string };

const COLORS = ['#8b5cf6', '#e3ac45', '#5ec8a7', '#8fb0d8', '#d98cb4', '#f5f5f7'];

/**
 * ParticleBurst：点击粒子爆发容器。
 * burstKey 每 +1 触发一次：14 个小点从容器中心沿随机方向飞散后淡出。
 * 飞散用 transform + opacity 两段式 transition 实现（小程序 WXSS 不支持
 * CSS 变量驱动 keyframes，故不用 var() 方案）。真实接入点：我的页积分中心
 * 每日签到成功时 burstKey +1（见 mine/index.tsx 的 earn('signin') 成功分支）。
 */
export function ParticleBurst({ children, burstKey, className }: {
  children: ReactNode;
  burstKey: number;
  className?: string;
}) {
  const [particles, setParticles] = useState<Particle[]>([]);
  const [flying, setFlying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (burstKey <= 0) return;
    const next: Particle[] = Array.from({ length: 14 }, (_, i) => ({
      id: Date.now() + i,
      angle: (Math.PI * 2 * i) / 14 + Math.random() * 0.45,
      dist: 58 + Math.random() * 52,
      size: 6 + Math.floor(Math.random() * 7),
      color: COLORS[i % COLORS.length],
    }));
    setParticles(next);
    setFlying(false);
    const kick = setTimeout(() => setFlying(true), 30);
    timerRef.current = setTimeout(() => { setParticles([]); setFlying(false); }, 850);
    return () => { clearTimeout(kick); if (timerRef.current) clearTimeout(timerRef.current); };
  }, [burstKey]);

  return (
    <View className={'burst-wrap ' + (className || '')}>
      {children}
      <View className='burst-layer'>
        {particles.map((p) => {
          const dx = Math.cos(p.angle) * p.dist;
          const dy = Math.sin(p.angle) * p.dist;
          return (
            <View
              key={p.id}
              className='burst-particle'
              style={{
                width: p.size + 'px',
                height: p.size + 'px',
                marginLeft: -p.size / 2 + 'px',
                marginTop: -p.size / 2 + 'px',
                background: p.color,
                opacity: flying ? 0 : 1,
                transform: flying ? `translate(${dx}px, ${dy}px) scale(0.4)` : 'translate(0px, 0px) scale(1)',
              }}
            />
          );
        })}
      </View>
    </View>
  );
}
