import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import { callFn, cloudConfigured, type SavedChart } from '../../lib/cloud';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import CompareView from '../../components/compare';

// 合盘报告页：与“我的 → 合盘对照”共用 CompareView（宫名已修正
// 为引擎原名）。合盘数据来自云端已保存的命盘；未配置时诚实空态。
export default function Compare() {
  const [theme] = useTheme();
  const [charts, setCharts] = useState<SavedChart[]>([]);
  const [aId, setAId] = useState('');
  const [bId, setBId] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    if (!cloudConfigured()) {
      setNote('云开发未配置：合盘对照需先保存命盘到云端，环境 ID 到位后开通；当前不展示虚假对照。');
      return;
    }
    callFn<{ charts: SavedChart[] }>('charts', { action: 'list' }).then((res) => {
      if (res.ok) setCharts(res.data.charts);
      else setNote('合盘数据加载失败：' + res.code);
    });
  }, []);

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='合盘报告'>
        {note ? <Text className='muted'>{note}</Text> : null}
        {!note ? <CompareView charts={charts} aId={aId} bId={bId} onA={setAId} onB={setBId} /> : null}
      </Card>
      <Disclaimer />
    </View>
  );
}
