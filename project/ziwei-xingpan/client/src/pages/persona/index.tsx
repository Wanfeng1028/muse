// 人格形象页：当前盘人格（loadChart，或 ?profileId= 指定档案最新盘）。
// - 基础款：按命宫主星预设，本地出图，免费，永不依赖云端。
// - AI 定制：云端 aiImage kind 'persona'，100 积分/次（缓存命中
//   免费复用）；未配置时诚实未配置态并明示价格与前置条件。
// 形象仅为装饰，不作命运断言。

import { useState } from 'react';
import { View, Text, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import PersonaCard from '../../components/persona';
import { useTheme } from '../../lib/theme';
import { loadChart } from '../../lib/chart';
import { getProfile, latestChart } from '../../lib/profiles';
import { personaForChart, type PersonaPreset } from '../../lib/persona';
import { callFn, cloudConfigured } from '../../lib/cloud';
import { LoadingButton } from '../../components/interactions/LoadingButton';
import './index.scss';

export default function Persona() {
  const [theme] = useTheme();
  const [preset, setPreset] = useState<PersonaPreset | null>(null);
  const [chartName, setChartName] = useState('');
  const [customFileID, setCustomFileID] = useState('');
  const [notice, setNotice] = useState('');
  const [customizing, setCustomizing] = useState(false);

  useDidShow(() => {
    const params = (Taro.getCurrentInstance().router?.params as any) || {};
    let chart = loadChart();
    let name = '';
    if (params.profileId) {
      const p = getProfile(params.profileId);
      const latest = p ? latestChart(p) : null;
      if (latest) {
        chart = latest.chart;
        name = p.name;
      }
    }
    if (!chart) {
      setPreset(null);
      setChartName('');
      return;
    }
    setPreset(personaForChart(chart));
    setChartName(name || '当前命盘');
    setCustomFileID('');
    setNotice('');
  });

  async function customize() {
    if (!preset || customizing) return;
    if (!cloudConfigured()) {
      setNotice('AI 定制形象需要云开发：环境 ID 到位后开通，100 积分/次；基础款（上方）免费，无需云端。');
      return;
    }
    setCustomizing(true);
    setNotice('');
    try {
      const prompt = '紫微斗数人格形象插画：主星' + preset.star + '，称号' + preset.title + '，意象' + preset.motif + '，中国风，简洁留白，方形头像。';
      const res = await callFn<{ fileID: string; chargedPoints: number; cached: boolean }>('aiImage', {
        kind: 'persona', prompt: prompt,
      });
      if (!res.ok) {
        setNotice('AI 定制失败：' + res.message);
        return;
      }
      setCustomFileID(res.data.fileID);
      setNotice(res.data.cached ? '已复用缓存形象，未扣积分。' : 'AI 定制完成，扣 ' + res.data.chargedPoints + ' 积分。');
    } catch {
      setNotice('AI 定制失败：网络或服务异常（未扣费），请稍后重试。');
    } finally {
      setCustomizing(false);
    }
  }

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='人格形象'>
        {!preset ? (
          <Text className='muted'>需先排盘：人格形象按命宫主星生成，请先去排盘页排一盘，或从档案里选一个人。</Text>
        ) : (
          <View>
            <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>{chartName} · 基础款免费（本地出图）</Text>
            <PersonaCard preset={preset} />
          </View>
        )}
        {notice ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{notice}</Text> : null}
      </Card>
      {preset ? (
        <Card light title='AI 定制形象'>
          <Text className='muted'>按主星意象生成专属插画，100 积分/次；缓存命中免费复用，失败不扣费。</Text>
          <View style={{ marginTop: '12px' }}>
            <LoadingButton loading={customizing} onClick={customize}>AI 定制 100 积分</LoadingButton>
          </View>
          {customFileID ? (
            <Image className='persona-custom' src={customFileID} mode='widthFix' />
          ) : null}
        </Card>
      ) : null}
      <Disclaimer />
    </View>
  );
}
