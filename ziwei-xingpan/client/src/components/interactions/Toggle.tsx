import { View } from '@tarojs/components';
import './interactions.scss';

/**
 * Toggle：自定义 iOS 风动画开关。
 * 滑块滑动 + 轨道变色，走 iOS 曲线 cubic-bezier(0.32,0.72,0,1)；
 * 替代我的页设置里原生的 <Switch>（原生开关无滑动变色动画）。
 */
export function Toggle({ checked, onChange, disabled, id }: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <View
      id={id}
      className={'ios-toggle' + (checked ? ' is-on' : '') + (disabled ? ' is-disabled' : '')}
      onClick={() => { if (!disabled) onChange(!checked); }}
    >
      <View className='ios-toggle-knob' />
    </View>
  );
}
