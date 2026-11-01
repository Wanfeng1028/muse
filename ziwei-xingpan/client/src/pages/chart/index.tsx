import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { Solar } from 'lunar-javascript';
import { loadChart, loadInput, stemBranchLabel, branchLabel, formatDate } from '../../lib/chart';
import { callFn, cloudConfigured } from '../../lib/cloud';
import { getDaXianIndexForYear, getDaXianStartYear } from '../../engine/yunxian-context';
import { getLiuNianSiHua, getLiuYueSiHua } from '../../engine/sihua';
import { jiangQianShenName, suiQianShenName, boshiShenName } from '../../engine/shier-shen';
import { STEMS } from '../../engine/constants';
import type { Palace, ZiweiChart } from '../../engine/types';
import { Ambient, Card, Disclaimer } from '../../components/ui';
import './index.scss';
import './index.scss';

// 4x4 grid slots in reading order; null = center 2x2 area (handled as one cell).
const GRID: Array<number | null> = [5, 6, 7, 8, 4, null, null, 9, 3, null, null, 10, 2, 1, 0, 11];
const SIHUA_CLASS: Record<string, string> = { '禄': 'sihua-lu', '权': 'sihua-quan', '科': 'sihua-ke', '忌': 'sihua-ji' };

function PalaceCell({ p, chart }: { p: Palace; chart: ZiweiChart }) {
  const majors = p.stars.filter((s) => s.type === 'major');
  const minors = p.stars.filter((s) => s.type === 'minor');
  const luckies = p.stars.filter((s) => s.type === 'lucky');
  const shas = p.stars.filter((s) => s.type === 'sha');
  const rest = p.stars.filter((s) => s.type !== 'major' && s.type !== 'minor' && s.type !== 'lucky' && s.type !== 'sha');
  const yearBranch = chart.lunarInfo.yearBranch;
  const yearStem = chart.lunarInfo.yearStem;
  const gender = chart.birthInfo.gender;
  return (
    <View className={p.isCurrentDaXian ? 'palace current' : 'palace'}>
      <View className='palace-head'>
        <Text className='palace-branch'>{stemBranchLabel(p.stem, p.branch)}</Text>
        <Text className='palace-name'>{p.name}</Text>
      </View>
      {p.isMingGong ? <Text className='palace-tag'>命</Text> : null}
      {p.isShenGong ? <Text className='palace-tag'>身</Text> : null}
      {majors.map((s) => (
        <View key={s.name} className='star-major'>
          <Text>{s.name}</Text>
          {s.brightnessRaw ? <Text className='star-bright'>{s.brightnessRaw}</Text> : null}
          {s.siHua ? <Text className={SIHUA_CLASS[s.siHua] ?? ''}>化{s.siHua}</Text> : null}
        </View>
      ))}
      {minors.length > 0 ? (
        <View className='star-others star-minor'>{minors.map((s) => s.name).join(' ')}</View>
      ) : null}
      {luckies.length > 0 ? (
        <View className='star-others star-lucky'>{luckies.map((s) => s.name).join(' ')}</View>
      ) : null}
      {shas.length > 0 ? (
        <View className='star-others star-sha'>{shas.map((s) => s.name).join(' ')}</View>
      ) : null}
      {rest.length > 0 ? (
        <View className='star-others star-borrowed'>{rest.map((s) => s.name).join(' ')}</View>
      ) : null}
      {p.isEmpty && p.borrowedStars?.length ? (
        <View className='star-others star-borrowed'>借对宫：{p.borrowedStars.join(' ')}</View>
      ) : null}
      <View className='shensha'>
        {jiangQianShenName(yearBranch, p.branch)} · {suiQianShenName(yearBranch, p.branch)} · {boshiShenName(yearStem, gender, p.branch)}
      </View>
      {p.daXianAge ? <View className='daxian-age'>{p.daXianAge[0]}-{p.daXianAge[1]} 岁</View> : null}
    </View>
  );
}

export default function ChartPage() {
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  const [input, setInput] = useState(loadInput());
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setChart(loadChart()); setInput(loadInput()); }, []);

  async function saveChart() {
    if (!chart || !input) return;
    if (!cloudConfigured()) {
      Taro.showToast({ title: '云开发未配置，命盘历史需环境 ID 后开通', icon: 'none' });
      return;
    }
    setSaving(true);
    const res = await callFn<{ chartId: string }>('charts', {
      action: 'create',
      name: chart.birthInfo.name || '我的命盘',
      birthParams: input,
      chartData: chart,
    });
    setSaving(false);
    if (res.ok) {
      setSaved(true);
      Taro.showToast({ title: '已保存到我的命盘', icon: 'none' });
    } else {
      Taro.showToast({ title: '保存失败：' + res.code, icon: 'none' });
    }
  }

  if (!chart) {
    return (
      <View className='page'>
        <Ambient />
        <Card title='还没有命盘'>
          <Text className='muted'>请先在首页填写出生信息并排盘。</Text>
          <View className='btn-medley btn-medley-white' style={{ marginTop: '12px' }} onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>去首页排盘</View>
        </Card>
      </View>
    );
  }

  const byBranch = (b: number) => chart.palaces.find((p) => p.branch === b)!;
  const now = new Date();
  const todayLunar = Solar.fromYmd(now.getFullYear(), now.getMonth() + 1, now.getDate()).getLunar();
  const liunianYear = todayLunar.getYear();
  const liunianAge = liunianYear - chart.lunarInfo.lunarYear + 1;
  const dxIdx = getDaXianIndexForYear(chart, liunianYear);
  const dx = dxIdx >= 0 ? chart.daXians[dxIdx] : null;
  const liunianSihua = getLiuNianSiHua(liunianYear);
  const liuyue = Array.from({ length: 12 }, (_, i) => getLiuYueSiHua(liunianSihua.stemIndex, i + 1));

  return (
    <View className='page'>
      <Ambient />
      <View className='chart-plate'>
      <View className='chart-grid'>
        {GRID.map((b, i) => {
          if (b === null) {
            if (i === 5) {
              return (
                <View key='center' className='chart-center'>
                  <View className='brand-dots center-dots'>
                    <View className='brand-dot brand-dot-green' />
                    <View className='brand-dot brand-dot-blue' />
                    <View className='brand-dot brand-dot-pink' />
                  </View>
                  <Text className='center-name'>{chart.birthInfo.name || '未具名'} · {chart.birthInfo.gender === 'male' ? '男' : '女'}</Text>
                  <Text className='center-line'>农历 {chart.lunarInfo.lunarYear} 年 {Math.abs(chart.lunarInfo.lunarMonth)} 月 {chart.lunarInfo.lunarDay} 日{chart.lunarInfo.isLeapMonth ? '（闰月）' : ''}</Text>
                  <Text className='center-line'>{chart.wuxingJuName} · 命主 {chart.mingZhu} · 身主 {chart.shenZhu}</Text>
                  <Text className='center-line'>{chart.yinYangGender} · 虚岁 {chart.currentAge} 岁</Text>
                  <Text className='center-line'>命宫 {branchLabel(chart.mingGongBranch)} · 身宫 {branchLabel(chart.shenGongBranch)}</Text>
                  {input?.corrections?.length ? <Text className='center-line'>已应用：{input.corrections.join('、')}</Text> : null}
                </View>
              );
            }
            return null;
          }
          return <PalaceCell key={b} p={byBranch(b)} chart={chart} />;
        })}
      </View>
      </View>

      <View className='btn-row chart-actions'>
        <View className='btn-medley btn-medley-white' onClick={saveChart}>
          {saving ? '保存中…' : saved ? '已保存，去“我的 → 命盘历史”查看' : '保存到我的命盘'}
        </View>
        {saved ? (
          <View className='btn-medley btn-medley-outline' onClick={() => Taro.switchTab({ url: '/pages/mine/index' })}>去我的页查看命盘历史</View>
        ) : null}
      </View>

      <Card title='大运'>
        {chart.daXians.map((d, i) => (
          <View key={`${d.startAge}-${d.palaceBranch}`} className='daxian-row'>
            <Text>{d.startAge}-{d.endAge} 岁 · {d.palaceName}（{branchLabel(d.palaceBranch)}）</Text>
            {i === chart.currentDaXianIndex ? <Text className='chip chip-accent'>当前</Text> : null}
            {dxIdx === i ? <Text className='chip'>本年所属</Text> : null}
            {getDaXianStartYear(chart, i) != null ? <Text className='muted'> 约 {getDaXianStartYear(chart, i)} 农历年起</Text> : null}
          </View>
        ))}
      </Card>

      <Card title={`流年 / 流月（今年农历 ${liunianYear} 年，虚岁 ${liunianAge} 岁）`}>
        <Text className='muted'>
          所属大限：{dx ? `${dx.palaceName}（${dx.startAge}-${dx.endAge} 岁）` : '童限或超出范围'}；
          流年干 {liunianSihua.stemName}：化禄 {liunianSihua.transforms['禄']}、化权 {liunianSihua.transforms['权']}、
          化科 {liunianSihua.transforms['科']}、化忌 {liunianSihua.transforms['忌']}。
        </Text>
        <View style={{ marginTop: '10px' }}>
          {liuyue.map((m) => (
            <View key={m.month} className='liuyue-row'>
              <Text>{m.month} 月（{STEMS[m.stemIndex]}）</Text>
              <Text className='muted'> 禄 {m.transforms['禄']} · 权 {m.transforms['权']} · 科 {m.transforms['科']} · 忌 {m.transforms['忌']}</Text>
            </View>
          ))}
        </View>
        <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>流月按农历月序排列，月份天干用五虎遁推算。</Text>
      </Card>
      <Disclaimer />
    </View>
  );
}
