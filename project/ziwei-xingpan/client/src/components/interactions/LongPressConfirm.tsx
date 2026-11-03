import { View, Text } from '@tarojs/components';
import { useRef, useState } from 'react';
import type { ReactNode } from 'react';
import './interactions.scss';

/**
 * LongPressConfirm：长按确认。
 * 按住后底部进度条走满（默认 900ms）才触发 onConfirm；提前松手取消，
 * 进度条迅速回落。touch 为主路径（小程序真实路径），mouse 事件为 H5 增强。
 * 真实接入点：我的页命盘历史的删除按钮——长按本身即确认，替代原先的
 * showModal 二次确认框（不再弹框）。
 */
export function LongPressConfirm({ children, onConfirm, duration = 900, hint, id }: {
  children: ReactNode;
  onConfirm: () => void;
  duration?: number;
  hint?: string;
  id?: string;
}) {
  const [holding, setHolding] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setHolding(true);
    timerRef.current = setTimeout(() => {
      setHolding(false);
      timerRef.current = null;
      onConfirm();
    }, duration);
  };

  const cancel = () => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setHolding(false);
  };

  // mouse 事件 Taro 类型里没有，用 any 透传：H5 运行时会绑到 DOM 节点，
  // 小程序端走 touch，两条路互不干扰。
  const mouseProps = {
    onMouseDown: start,
    onMouseUp: cancel,
    onMouseLeave: cancel,
  } as any;

  return (
    <View
      id={id}
      className={'longpress-btn' + (holding ? ' is-holding' : '')}
      onTouchStart={start}
      onTouchEnd={cancel}
      onTouchCancel={cancel}
      {...mouseProps}
    >
      <Text className='longpress-label'>{children}</Text>
      {hint ? <Text className='longpress-hint'>{holding ? '按住别松手…' : hint}</Text> : null}
      <View
        className='longpress-progress'
        style={{
          transform: holding ? 'scaleX(1)' : 'scaleX(0)',
          transition: holding ? `transform ${duration}ms linear` : 'transform 0.15s ease-out',
        }}
      />
    </View>
  );
}
