import { useEffect, useState } from 'react';
import { View, Text, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { loadChart, loadInput } from '../../lib/chart';
import { goInterpret } from '../../lib/nav';
import { fortuneToday, todayHeader } from '../../lib/fortune';
import { PERSONAS } from '../../lib/tools';
import type { ZiweiChart } from '../../engine/types';
import { Ambient, AmbientLight, Card, ComposerBar, Disclaimer } from '../../components/ui';
import { Icon, IconBadge, type IconName } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import starMark from '../../assets/logo/star-mark.png';
import { BannerAd } from '../../components/ads';
import { callFn, cloudConfigured, type AppConfig, type MembershipStatus } from '../../lib/cloud';
import { adSlotLive } from '../../lib/ads';
import CustomTabBar from '../../custom-tab-bar';
import './index.scss';

// 门户首页：结构借参照小程序的门户布局（日期行 → 今日运势 →
// 热门功能 → 三卡 → 六卡阵 → 报告列），美术、文案、头像一律本站
// 原创；分数全部由排盘引擎实算（公式见 lib/fortune.ts 与 PORTAL.md），
// 不编“多少人觉得准”类营销数字；紫微仍为核心，不做西洋轮盘。
const HOT_FUNCS: Array<{ label: string; icon: IconName; url: string }> = [
  { label: '星座骰子', icon: 'dices', url: '/pages/dice/index' },
  { label: '塔罗牌', icon: 'layers', url: '/pages/tarot/index' },
  { label: '六爻卜卦', icon: 'coins', url: '/pages/liuyao/index' },
  { label: 'AI解梦', icon: 'moon', url: '/pages/dream/index' },
];

const THREE_CARDS: Array<{ label: string; sub: string; icon: IconName; url: string }> = [
  { label: '八字运势', sub: '四柱与五行分布', icon: 'scroll', url: '/pages/bazi/index' },
  { label: '紫微斗数', sub: '十二宫命盘图', icon: 'star', url: '/pages/chart/index' },
  { label: '星象日历', sub: '节气与当日星宿', icon: 'calendar', url: '/pages/calendar/index' },
];

const SIX_GRID: Array<{ label: string; icon: IconName; url: string }> = [
  { label: '许愿', icon: 'gift', url: '/pages/wish/index?tab=wish' },
  { label: '祈福', icon: 'hand-heart', url: '/pages/wish/index?tab=prayer' },
  { label: '万年历', icon: 'calendar', url: '/pages/calendar/index?tab=calendar' },
  { label: '老黄历', icon: 'book-open', url: '/pages/calendar/index?tab=huangli' },
  { label: '星宿', icon: 'star', url: '/pages/calendar/index?tab=xingsu' },
  { label: 'MBTI', icon: 'brain', url: '/pages/mbti/index' },
];

// 报告列 → 解读维度映射：学业取父母宫（文星与学习节奏），婚姻与
// 爱情同取夫妻宫；综合取解读页顶部的格局判断；合盘取对照页。
// 注意：解读页是 Tab 页，不能 navigateTo（微信会报错），一律走
// lib/nav.ts 的 goInterpret（switchTab + 存储中转 ?dim=）。
const REPORTS: Array<{ label: string; sub: string; icon: IconName; grad: string; dim?: string; url?: string }> = [
  { label: '综合报告', sub: '命宫与格局总览，先看全盘再谈细节', icon: 'layers', grad: 'report-grad-1' },
  { label: '爱情报告', sub: '夫妻宫主星与相处倾向', icon: 'heart', grad: 'report-grad-2', dim: 'ganqing' },
  { label: '财富报告', sub: '财帛宫主星与收支倾向', icon: 'coins', grad: 'report-grad-3', dim: 'cai' },
  { label: '事业报告', sub: '官禄宫主星与职业发展倾向', icon: 'briefcase', grad: 'report-grad-4', dim: 'shiye' },
  { label: '学业报告', sub: '父母宫与文星，兼看学习节奏', icon: 'graduation-cap', grad: 'report-grad-5', dim: 'fumu' },
  { label: '婚姻报告', sub: '夫妻宫主星与婚姻相处倾向', icon: 'heart', grad: 'report-grad-6', dim: 'ganqing' },
  { label: '合盘报告', sub: '双方六宫主星对照，不作关系断言', icon: 'users', grad: 'report-grad-7', url: '/pages/compare/index' },
];

export default function Home() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  const [adConfig, setAdConfig] = useState<AppConfig | null>(null);
  const [adTier, setAdTier] = useState<string | null>(null);

  // Tab pages are NOT remounted on tab switch (Taro keeps them alive),
  // so a mount-only load would keep showing the pre-chart state after
  // the user computes a chart and switches back to Home. Reload the
  // local chart on every show (same pattern as lib/theme useTheme).
  useDidShow(() => setChart(loadChart()));

  useEffect(() => {
    if (!cloudConfigured()) return;
    callFn<AppConfig>('config', { action: 'get' }).then((c) => { if (c.ok && c.data) setAdConfig(c.data); });
    callFn<MembershipStatus>('membership', { action: 'status' }).then((m) => { if (m.ok && m.data) setAdTier(m.data.tier); });
  }, []);

  const header = todayHeader(new Date());
  const fortune = chart ? fortuneToday(chart) : null;
  const hasStored = !!loadInput();
  const ming = chart?.palaces.find((p) => p.isMingGong);
  const mingMajors = ming ? ming.stars.filter((s) => s.type === 'major').map((s) => s.name).join(' ') : '';
  const dark = theme === 'dark';
  const ringTrack = dark ? '#2f3034' : '#e6e7ea';
  const ringInner = dark ? '#1e1f23' : '#ffffff';

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient welcome />}
      <View className='hero'>
        <View className='hero-brand'>
          <Image className='brand-mark' src={starMark} mode='aspectFit' />
          <Text className='brand-name'>紫微星盘</Text>
        </View>
        <Text className='portal-date'>{header.dateLabel} {header.weekday} · {header.lunarLabel}</Text>
        <View className='hero-title-row'>
          <Text className='hero-title'>你的命盘，一眼看懂</Text>
          <View className='hero-cursor' />
        </View>
        <Text className='hero-sub'>紫微斗数为核心，排盘在本地完成，不走服务器。</Text>
      </View>

      <Card title='我的命盘'>
        {chart ? (
          <View>
            <Text className='muted'>
              {chart.birthInfo.name || '未具名'} · {chart.birthInfo.gender === 'male' ? '男' : '女'} · 命宫{mingMajors ? `主星 ${mingMajors}` : '无主星'}
            </Text>
            <View className='btn-row' style={{ marginTop: '12px' }}>
              <View className='btn-medley btn-medley-dark' hoverClass='btn-press' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看我的命盘</View>
              <View className='btn-medley btn-medley-outline-light' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>重新排盘</View>
            </View>
          </View>
        ) : (
          <View>
            <Text className='muted'>还没有命盘。填好出生信息，本地即可排盘，随后首页会显示你的今日运势。</Text>
            <View style={{ marginTop: '12px' }}><ComposerBar label='开始排盘' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })} /></View>
            {hasStored ? (
              <View className='btn-medley btn-medley-outline-light home-secondary' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看上次命盘</View>
            ) : null}
          </View>
        )}
      </Card>

      <Card title='今日运势'>
        {fortune ? (
          <View>
            <View className='fortune-top'>
              <View className='fortune-ring' style={{ background: `conic-gradient(#346bf0 0 ${fortune.total}%, ${ringTrack} ${fortune.total}% 100%)` }}>
                <View className='fortune-ring-inner' style={{ background: ringInner }}>
                  <Text className='fortune-total'>{fortune.total}</Text>
                  <Text className='fortune-total-label'>综合</Text>
                </View>
              </View>
              <View className='fortune-bars'>
                {[
                  { label: '爱情', v: fortune.love },
                  { label: '财富', v: fortune.wealth },
                  { label: '事业', v: fortune.career },
                  { label: '学习', v: fortune.study },
                ].map((b) => (
                  <View key={b.label} className='fortune-bar-col'>
                    <View className='fortune-bar-track'>
                      <View className='fortune-bar-fill' style={{ height: b.v + '%' }} />
                    </View>
                    <Text className='fortune-bar-val'>{b.v}</Text>
                    <Text className='fortune-bar-label'>{b.label}</Text>
                  </View>
                ))}
              </View>
            </View>
            <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>{fortune.oneLiner}</Text>
            <Text className='caption' style={{ display: 'block', marginTop: '6px' }}>
              分数由本盘星曜亮度、吉煞与四化按公开公式换算（见运势页公式说明），仅供娱乐参考。
              今日地支落{fortune.dayPalaceName}宫，日支修正 {fortune.dayAdj > 0 ? '+' + fortune.dayAdj : fortune.dayAdj}。
            </Text>
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/fortune/index' })}>更多</View>
          </View>
        ) : (
          <View>
            <Text className='muted'>排盘后查看今日运势：综合分与爱情、财富、事业、学习四项均由你的命盘实算。</Text>
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
          </View>
        )}
      </Card>

      <Text className='portal-section-title'>热门功能</Text>
      <View className='portal-grid-4'>
        {HOT_FUNCS.map((f) => (
          <View key={f.label} className='hot-card' onClick={() => Taro.navigateTo({ url: f.url })}>
            <View className='hot-badge'><Text>HOT</Text></View>
            <IconBadge name={f.icon} dark={dark} />
            <Text className='hot-label'>{f.label}</Text>
          </View>
        ))}
      </View>

      <View className='portal-grid-3'>
        {THREE_CARDS.map((c) => (
          <View key={c.label} className='portal-tri-card' onClick={() => Taro.navigateTo({ url: c.url })}>
            <IconBadge name={c.icon} dark={dark} />
            <Text className='portal-tri-title'>{c.label}</Text>
            <Text className='portal-tri-sub'>{c.sub}</Text>
          </View>
        ))}
      </View>

      <View className='portal-grid-3'>
        {SIX_GRID.map((c) => (
          <View key={c.label} className='portal-mini-card' onClick={() => Taro.navigateTo({ url: c.url })}>
            <Icon name={c.icon} tone={dark ? 'sky' : 'blue'} size='40px' />
            <Text className='portal-mini-label'>{c.label}</Text>
          </View>
        ))}
      </View>

      <Text className='portal-section-title'>为你推荐</Text>
      {!chart ? <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>报告基于你的命盘生成，未排盘时点进去会先提示去排盘。</Text> : null}
      <View className='report-list'>
        {REPORTS.map((r) => (
          <View key={r.label} className='report-row' onClick={() => { if (r.url) Taro.navigateTo({ url: r.url }); else goInterpret(r.dim); }}>
            <View className={'report-cover ' + r.grad}>
              <Icon name={r.icon} tone='white' size='44px' />
            </View>
            <View className='report-body'>
              <Text className='report-title'>{r.label}</Text>
              <Text className='report-sub'>{r.sub}</Text>
            </View>
            <View className='svc-arrow-img'><Icon name='chevron-right' tone={dark ? 'sky' : 'blue'} size='38px' /></View>
          </View>
        ))}
      </View>

      <Card title='AI 占星师'>
        <Text className='muted'>四位原创人格，私聊打开解盘对话（本地 13 维解读；AI 生成需云开发配置）。</Text>
        <View style={{ display: 'flex', flexWrap: 'wrap', marginTop: '12px' }}>
          {PERSONAS.map((p) => (
            <Text key={p.id} className='chip chip-accent' style={{ marginRight: '8px', marginBottom: '8px' }}>{p.name}</Text>
          ))}
        </View>
        <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/astrologers/index' })}>认识四位占星师</View>
      </Card>

      <Disclaimer />
      {adTier === 'free' ? <BannerAd unitId={adSlotLive(adConfig, 'bannerHome')} /> : null}
      {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
    </View>
  );
}
