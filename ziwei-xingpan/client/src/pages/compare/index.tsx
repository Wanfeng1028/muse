// 合盘报告页：与“我的 → 合盘对照”共用 CompareView（宫名已修正
// 为引擎原名）。
// - 云端配置时：合盘数据来自云端已保存的命盘（既有行为）。
// - 未配置时：改走本地人物档案（各档案最新盘转 SavedChart 形），
//   并注明“本地档案对照，云端同步待 envId 后开通”。
// - 计费：合盘对照 60 积分/次，由 lib/use-compare-charge 的共享门禁
//   执行（两侧选定才扣费；结果在 locked 时不渲染，余额不足时清
//   除第二方选择并提示赚积分途径）。

import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { callFn, cloudConfigured, type SavedChart } from '../../lib/cloud';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import CompareView from '../../components/compare';
import { listProfiles, profileToSavedChart } from '../../lib/profiles';
import { useCompareCharge } from '../../lib/use-compare-charge';

export default function Compare() {
  const [theme] = useTheme();
  const [charts, setCharts] = useState<SavedChart[]>([]);
  const [aId, setAId] = useState('');
  const [bId, setBId] = useState('');
  const [loadNote, setLoadNote] = useState('');
  const { locked, note: chargeNote } = useCompareCharge(aId, bId, () => setBId(''));

  useEffect(() => {
    if (!cloudConfigured()) {
      const local = listProfiles()
        .map((p) => profileToSavedChart(p))
        .filter((c): c is SavedChart => !!c);
      setCharts(local);
      if (local.length < 2) {
        setLoadNote('本地档案对照：云端同步待 envId 后开通。当前本地档案不足两人，请先去人物档案新建至少两个档案。');
      } else {
        setLoadNote('本地档案对照：云端同步待 envId 后开通。');
      }
      return;
    }
    callFn<{ charts: SavedChart[] }>('charts', { action: 'list' }).then((res) => {
      if (res.ok) setCharts(res.data.charts);
      else setLoadNote('合盘数据加载失败：' + res.code);
    });
  }, []);

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='合盘报告'>
        {loadNote ? <Text className='muted'>{loadNote}</Text> : null}
        {chargeNote ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{chargeNote}</Text> : null}
        {charts.length === 0 ? (
          <View className='btn-medley btn-medley-dark' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/profiles/index' })}>去人物档案新建档案</View>
        ) : (
          <CompareView charts={charts} aId={aId} bId={bId} onA={setAId} onB={setBId} locked={locked} />
        )}
        {locked ? (
          <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>正在结算 60 积分，付费后显示对照结果。</Text>
        ) : null}
      </Card>
      <Disclaimer />
    </View>
  );
}
