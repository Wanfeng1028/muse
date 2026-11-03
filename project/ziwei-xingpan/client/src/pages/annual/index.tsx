// 年度运势页：今年流年 + 当前大限 + 格局，全部由本地引擎实算
// （流年支、四化、大限、格局检测），不编造分数与断言。
// 计费：Max 免费；其他档位 100 积分/次（每次查看扣一次，离页后
// 再次查看需重新付费）。云端走 points spend annualFortune（服务端
// 未成年人门禁与余额检查）；未配置时走本地账本。

import { useState, type ReactNode } from 'react';
import { View, Text } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import { loadChart, branchLabel } from '../../lib/chart';
import type { ZiweiChart } from '../../engine/types';
import { getLiuNianSiHua, getYearBranchIndex } from '../../engine/sihua';
import { getDaXianIndexForYear } from '../../engine/yunxian-context';
import { detectPatterns } from '../../engine/patterns';
import { callFn, cloudConfigured, type MembershipStatus } from '../../lib/cloud';
import { PRICING, resolvePricing, localSpend, localTier, EARN_GUIDE, annualFortuneCost, type Tier } from '../../lib/pricing';
import { LoadingButton } from '../../components/interactions/LoadingButton';
import './index.scss';

function starNames(chart: ZiweiChart, branchIndex: number): string {
  const palace = chart.palaces.find((p) => p.branch === branchIndex);
  if (!palace) return '未知';
  const majors = palace.stars.filter((s) => s.type === 'major').map((s) => s.name).join('、');
  if (majors) return majors;
  const borrowed = (palace.borrowedStars || []).join('、');
  return borrowed ? '借' + borrowed : '无主星';
}

export default function Annual() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  const [tier, setTier] = useState<Tier>('free');
  const [paid, setPaid] = useState(false);
  const [paying, setPaying] = useState(false);
  const [notice, setNotice] = useState('');
  const [pricing, setPricing] = useState(PRICING);

  useDidShow(() => {
    setChart(loadChart());
    setPaid(false);
    setNotice('');
    if (cloudConfigured()) {
      callFn<MembershipStatus>('membership', { action: 'status' }).then((res) => {
        if (res.ok && res.data && res.data.tier) setTier(res.data.tier as Tier);
      }).catch(() => { /* tier display is best-effort */ });
      callFn<any>('config', { action: 'get' }).then((res) => {
        if (res.ok && res.data) setPricing(resolvePricing(res.data));
      }).catch(() => { /* local pricing fallback */ });
    } else {
      setTier(localTier().tier);
    }
  });

  async function pay() {
    if (paying) return;
    setPaying(true);
    setNotice('');
    try {
      if (cloudConfigured()) {
        // Fresh tier + pricing read inside the payment (not the page-load
        // state) so a Max user is never charged while status is loading.
        let freshTier: Tier = tier;
        let freshPricing = pricing;
        const m = await callFn<MembershipStatus>('membership', { action: 'status' });
        if (m.ok && m.data && m.data.tier) freshTier = m.data.tier as Tier;
        const c = await callFn<any>('config', { action: 'get' });
        if (c.ok && c.data) freshPricing = resolvePricing(c.data);
        setTier(freshTier);
        setPricing(freshPricing);
        if (annualFortuneCost(freshTier, freshPricing) === 0) {
          setPaid(true);
          setNotice('Max 会员免费，年度运势已解锁。');
          return;
        }
        const res = await callFn<{ delta: number; balance: number }>('points', { action: 'spend', rule: 'annualFortune' });
        if (!res.ok) {
          setNotice('支付失败：' + res.message + ' ' + EARN_GUIDE);
          return;
        }
        setPaid(true);
        setNotice('已扣 100 积分，年度运势已解锁（本次查看有效）。');
      } else {
        const res = localSpend('annualFortune', pricing, tier);
        if (!res.ok) {
          setNotice('积分不足：年度运势需 100 积分，当前余额 ' + ('balance' in res ? res.balance : 0) + '。' + EARN_GUIDE);
          return;
        }
        setPaid(true);
        setNotice(res.charged === 0 ? 'Max 会员免费，年度运势已解锁。' : '已扣 ' + res.charged + ' 积分，年度运势已解锁（本次查看有效）。');
      }
    } catch {
      setNotice('支付失败：网络或服务异常（未扣费），请稍后重试。');
    } finally {
      setPaying(false);
    }
  }

  const year = new Date().getFullYear();
  const cost = annualFortuneCost(tier, pricing);
  let body: ReactNode = null;
  if (chart && paid) {
    const liuNian = getLiuNianSiHua(year);
    const yearBranch = getYearBranchIndex(year);
    const daXianIndex = getDaXianIndexForYear(chart, year);
    const daXian = daXianIndex >= 0 && chart.daXians[daXianIndex] ? chart.daXians[daXianIndex] : null;
    const patterns = detectPatterns(chart);
    body = (
      <View>
        <Text className='annual-line'>今年（{year}年）：流年宫为{branchLabel(yearBranch)}宫，主星{starNames(chart, yearBranch)}；年干{liuNian.stemName}，四化：禄{liuNian.transforms['禄'] || ''}、权{liuNian.transforms['权'] || ''}、科{liuNian.transforms['科'] || ''}、忌{liuNian.transforms['忌'] || ''}。</Text>
        <Text className='annual-line' style={{ display: 'block', marginTop: '8px' }}>当前大限：{daXian ? '第 ' + (daXianIndex + 1) + ' 限，' + daXian.palaceName + '宫，' + daXian.startAge + '–' + daXian.endAge + '岁' : '未知'}。</Text>
        <Text className='annual-line' style={{ display: 'block', marginTop: '8px' }}>格局：{patterns.length > 0 ? patterns.map((p) => p.name).join('、') : '无入格格局'}。</Text>
        <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>以上内容由排盘引擎实算，仅供学习与娱乐参考，不构成人生决策建议。</Text>
      </View>
    );
  }

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='年度运势'>
        {!chart ? (
          <Text className='muted'>需先排盘：年度运势围绕本盘展开，请先去排盘页排一盘。</Text>
        ) : !paid ? (
          <View>
            <Text className='muted'>{year}年年度运势：流年宫、流年四化、当前大限与格局，由引擎实算。{cost === 0 ? 'Max 会员免费。' : '100 积分/次（每次查看扣一次）。'}</Text>
            <View style={{ marginTop: '12px' }}>
              <LoadingButton loading={paying} onClick={pay}>{cost === 0 ? '免费查看' : '查看年度运势 100 积分'}</LoadingButton>
            </View>
          </View>
        ) : body}
        {notice ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{notice}</Text> : null}
      </Card>
      <Disclaimer />
    </View>
  );
}
