import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import './interactions.scss';

/**
 * LoadingButton：按钮内加载态。
 * loading 时按钮内出现转圈、文字变淡、点击被忽略（防重复提交）。
 * 真实接入点：解读页 AI 解盘按钮（busy === 'interpret' 的真实耗时场景），
 * 原先的“生成中…”文字替换改为转圈 + 原文变淡。
 */
export function LoadingButton({ children, loading, onClick, className, disabled, id }: {
  children: ReactNode;
  loading: boolean;
  onClick: () => void;
  className?: string;
  disabled?: boolean;
  id?: string;
}) {
  const blocked = loading || disabled;
  return (
    <View
      id={id}
      className={'loading-btn ' + (className || '') + (loading ? ' is-loading' : '') + (disabled ? ' is-disabled' : '')}
      onClick={() => { if (!blocked) onClick(); }}
    >
      {loading ? <View className='loading-spinner' /> : null}
      <Text className='loading-label'>{children}</Text>
    </View>
  );
}
