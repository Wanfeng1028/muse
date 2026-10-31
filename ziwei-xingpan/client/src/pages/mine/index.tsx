import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { Card } from '../../components/ui';

const ROWS = ['会员中心', '积分中心', '邀请中心', '我的订单', '设置', '意见反馈', '关于（含数据来源）'];

export default function Mine() {
  function soon() {
    Taro.showToast({ title: '即将上线', icon: 'none' });
  }
  return (
    <View className='page'>
      <Card>
        <View style={{ display: 'flex', alignItems: 'center' }}>
          <View style={{ width: '56px', height: '56px', borderRadius: '28px', background: '#111214', color: '#fff', textAlign: 'center', lineHeight: '56px', fontSize: '24px' }}>盘</View>
          <View style={{ marginLeft: '12px' }}>
            <Text style={{ fontSize: '18px', fontWeight: 600, display: 'block' }}>紫微星盘用户</Text>
            <Text className='muted'>一期为静态壳：账号与会员功能在二期接入。</Text>
          </View>
        </View>
      </Card>
      <Card title='我的服务'>
        {ROWS.map((r) => (
          <View key={r} className='input-row' onClick={soon}>
            <Text className='input-label' style={{ color: '#17181c' }}>{r}</Text>
            <Text className='input-value'>›</Text>
          </View>
        ))}
      </Card>
      <Text className='caption'>
        数据来源：排盘引擎移植自 Renhuai123/ziwei-doushu（MIT，见引擎目录 LICENSE 与 SOURCE.md）。
        内容源自传统紫微斗数文化，仅供学习与娱乐参考，不构成人生决策建议。
      </Text>
    </View>
  );
}
