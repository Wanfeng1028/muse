import { View } from '@tarojs/components';
import './interactions.scss';

/**
 * HamburgerMorph：汉堡变叉。
 * 三条横线用 CSS transform 形变（上下两线旋转收拢、中线淡出），
 * 不是两张图硬切。走 iOS 曲线 cubic-bezier(0.32,0.72,0,1)。
 * 小程序里没有真实菜单：演示页里用它开关一个菜单面板，并诚实标注
 * 为组件演示；正式页面不挂假菜单。
 */
export function HamburgerMorph({ open, onToggle, id }: {
  open: boolean;
  onToggle: () => void;
  id?: string;
}) {
  return (
    <View id={id} className={'hamburger' + (open ? ' is-open' : '')} onClick={onToggle}>
      <View className='hamburger-bar bar-top' />
      <View className='hamburger-bar bar-mid' />
      <View className='hamburger-bar bar-bottom' />
    </View>
  );
}
