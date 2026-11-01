import { View, Text } from '@tarojs/components';
import { useEffect, useRef, useState } from 'react';
import { Card } from '../../components/ui';
import { RippleView, Toggle, ParticleBurst, LongPressConfirm, LoadingButton, HamburgerMorph } from '../../components/interactions';
import './index.scss';

// 演示页：非 tab 页，只在 app.config.ts 的 pages 列表里加一项，不动 tabBar。
// 以下 6 项均为交互组件演示，非正式功能入口；正式页面的真实接入点见各组件
// 文件头的注释（Toggle→我的页设置、ParticleBurst→积分签到成功、
// LongPressConfirm→命盘历史删除、LoadingButton→解读页 AI 解盘按钮）。
const MENU_ROWS = ['水波纹点击', '开关切换', '粒子爆发', '长按确认', '按钮内加载', '汉堡变叉'];

export default function Demo() {
  const [toggleOn, setToggleOn] = useState(false);
  const [burstKey, setBurstKey] = useState(0);
  const [lpDeleted, setLpDeleted] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoDone, setDemoDone] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  function fakeAsync() {
    if (demoLoading) return;
    setDemoLoading(true);
    setDemoDone(false);
    timerRef.current = setTimeout(() => { setDemoLoading(false); setDemoDone(true); }, 1500);
  }

  return (
    <View className='page'>
      <Card title='组件演示'>
        <Text className='muted'>以下 6 项均为交互组件演示，非正式功能入口。正式页面里的真实接入点见各组件文件头的注释。</Text>
      </Card>

      <Card title='1 · 水波纹点击'>
        <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>点按钮任意位置，波纹从触点扩散。</Text>
        <RippleView>
          <View id='demo-ripple-btn' className='btn-medley btn-medley-outline'>点我，看水波纹</View>
        </RippleView>
      </Card>

      <Card title='2 · 开关切换'>
        <View className='demo-row'>
          <Text>自定义 iOS 风动画开关</Text>
          <Toggle id='demo-toggle' checked={toggleOn} onChange={setToggleOn} />
        </View>
        <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>当前状态：{toggleOn ? '开' : '关'}</Text>
      </Card>

      <Card title='3 · 粒子爆发'>
        <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>点按钮，14 个小点从按钮中心飞散。</Text>
        <ParticleBurst burstKey={burstKey}>
          <View id='demo-burst-btn' className='btn-medley btn-medley-outline' onClick={() => setBurstKey((n) => n + 1)}>点我，粒子爆发</View>
        </ParticleBurst>
      </Card>

      <Card title='4 · 长按确认'>
        <View className='demo-row'>
          <Text>{lpDeleted ? '演示项 A（已确认，演示状态）' : '演示项 A'}</Text>
        </View>
        <Text className='muted' style={{ display: 'block', marginTop: '8px', marginBottom: '12px' }}>按住下方按钮走满进度才确认；提前松手取消，不删任何真实数据。</Text>
        <LongPressConfirm
          id='demo-longpress'
          hint='长按删除'
          onConfirm={() => setLpDeleted(true)}
        >长按删除</LongPressConfirm>
        <Text id='demo-longpress-status' className='muted' style={{ display: 'block', marginTop: '12px' }}>
          {lpDeleted ? '已确认（演示）' : '未确认'}
        </Text>
      </Card>

      <Card title='5 · 按钮内加载'>
        <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>点按钮模拟一次 1.5 秒异步请求：转圈 + 文字变淡，加载中再点无效。</Text>
        <LoadingButton id='demo-loading-btn' loading={demoLoading} onClick={fakeAsync} className='btn-medley btn-medley-white'>
          模拟异步请求
        </LoadingButton>
        {demoDone ? <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>完成（演示）</Text> : null}
      </Card>

      <Card title='6 · 汉堡变叉'>
        <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>点汉堡图标：三线用 transform 形变为叉，同时开关下方菜单面板。</Text>
        <View className='demo-row'>
          <Text>菜单</Text>
          <HamburgerMorph id='demo-hamburger' open={menuOpen} onToggle={() => setMenuOpen((v) => !v)} />
        </View>
        {menuOpen ? (
          <View id='demo-menu-panel' className='demo-panel'>
            {MENU_ROWS.map((r) => (
              <View key={r} className='demo-panel-row' onClick={() => setMenuOpen(false)}>
                <Text>{r}</Text>
              </View>
            ))}
            <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>此菜单面板仅为组件演示，小程序正式页面无此菜单。</Text>
          </View>
        ) : null}
      </Card>
    </View>
  );
}
