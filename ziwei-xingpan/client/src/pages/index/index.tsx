import { useEffect, useState } from 'react';
import { View, Text, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Solar } from 'lunar-javascript';
import { loadChart, loadInput, stemBranchLabel } from '../../lib/chart';
import { getDaXianIndexForYear } from '../../engine/yunxian-context';
import { getLiuNianSiHua, getLiuYueSiHua } from '../../engine/sihua';
import { detectPatterns } from '../../engine/patterns';
import { buildDimensions } from '../../lib/interpret';
import { goInterpret, goKnowledge } from '../../lib/nav';
import type { ZiweiChart } from '../../engine/types';
import { Ambient, AmbientLight, Card, ComposerBar, Disclaimer } from '../../components/ui';
import { IconBadge } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import starMark from '../../assets/logo/star-mark.png';
import { BannerAd } from '../../components/ads';
import { callFn, cloudConfigured, type AppConfig, type MembershipStatus } from '../../lib/cloud';
import { adSlotLive } from '../../lib/ads';
import './index.scss';

// 首页版式（2026-11-01 纠正后重做，自有版式）：
// hero 文本区 → 命盘锚点深色卡 → 流年·流月双卡 → 解读卡（13 维 chips）
// → 双入口 tiles（星曜知识 / 合盘对照）。只借“信息分层、核心功能
// 前置”这一门户式首页的通用做法，不照搬任何参照的版式顺序、组件
// 形态、功能清单、文案、配色。首页只放本站自有模块：排盘、命盘图、
// 运限（大运/流年/流月，引擎实算）、解读、知识、合盘——全部以
// Renhuai123/ziwei-doushu 源码功能为准，无评分、无圆环、无四项分。
const mod12 = (n: number) => ((n % 12) + 12) % 12;

const WEEKDAYS = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
const LUNAR_MONTHS = ['正月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '冬月', '腊月'];
const LUNAR_DAYS = [
  '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
  '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
  '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十',
];

function lunarMonthName(month: number): string {
  const leap = month < 0;
  const base = LUNAR_MONTHS[Math.abs(month) - 1] ?? '';
  return leap ? '闰' + base : base;
}

function dateHeader(date: Date): { dateLabel: string; weekday: string; lunarLabel: string } {
  const lunar = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate()).getLunar();
  return {
    dateLabel: `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`,
    weekday: WEEKDAYS[date.getDay()] ?? '',
    lunarLabel: `农历${lunarMonthName(lunar.getMonth())}${LUNAR_DAYS[lunar.getDay() - 1] ?? ''}`,
  };
}

function majorsLine(palace: ZiweiChart['palaces'][number] | undefined): string {
  if (!palace) return '—';
  const majors = palace.stars.filter((s) => s.type === 'major');
  if (majors.length === 0) {
    return palace.isEmpty && palace.borrowedStars?.length
      ? `无主星（借对宫：${palace.borrowedStars.join(' ')}）`
      : '无主星';
  }
  return majors.map((s) => `${s.name}${s.brightnessRaw ?? ''}${s.siHua ? `化${s.siHua}` : ''}`).join(' ');
}

function sihuaLine(t: Record<string, string>): string {
  return `化禄 ${t['禄']} · 化权 ${t['权']} · 化科 ${t['科']} · 化忌 ${t['忌']}`;
}

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

  // Welcome entry rule (2026-11-02 user order): no local login state
  // means show the welcome page first; logged-in users go straight
  // home. There is NO local login marker yet — loginFlow stores
  // nothing locally — so until cloud联调 adds one, this defaults to
  // showing welcome. Mount-only on purpose (never useDidShow): tab
  // pages stay mounted, so pressing back from welcome lands on this
  // already-mounted home and never re-bounces into a loop.
  useEffect(() => {
    // Automatic (not user-tapped) navigation: if the stack cannot take
    // it, stay on home instead of surfacing an unhandled rejection.
    Taro.navigateTo({ url: '/pages/welcome/index' }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!cloudConfigured()) return;
    callFn<AppConfig>('config', { action: 'get' }).then((c) => { if (c.ok && c.data) setAdConfig(c.data); });
    callFn<MembershipStatus>('membership', { action: 'status' }).then((m) => { if (m.ok && m.data) setAdTier(m.data.tier); });
  }, []);

  const dark = theme === 'dark';
  const header = dateHeader(new Date());
  const hasStored = !!loadInput();
  const ming = chart?.palaces.find((p) => p.isMingGong);
  const patterns = chart ? detectPatterns(chart) : [];
  const dims = chart ? buildDimensions(chart) : [];

  // 运限（与命盘图页同一算法，不新编口径）：流年支 = 农历年 −4 取余；
  // 大限按年取段；流年四化取年干；流月按农历月序、月份天干五虎遁。
  const now = new Date();
  const todayLunar = Solar.fromYmd(now.getFullYear(), now.getMonth() + 1, now.getDate()).getLunar();
  const liunianYear = todayLunar.getYear();
  const liunianAge = chart ? liunianYear - chart.lunarInfo.lunarYear + 1 : 0;
  const dxIdx = chart ? getDaXianIndexForYear(chart, liunianYear) : -1;
  const dx = dxIdx >= 0 && chart ? chart.daXians[dxIdx] : null;
  const liunianSihua = getLiuNianSiHua(liunianYear);
  const liunianBranch = mod12(liunianYear - 4);
  const liunianPalace = chart?.palaces.find((p) => p.branch === liunianBranch);
  const curMonthIdx = Math.abs(todayLunar.getMonth());
  const liuyueCur = getLiuYueSiHua(liunianSihua.stemIndex, curMonthIdx);

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient welcome />}
      <View className='hero'>
        <View className='hero-brand'>
          <Image className='brand-mark' src={starMark} mode='aspectFit' />
          <Text className='brand-name'>星命盘</Text>
        </View>
        <Text className='home-date'>{header.dateLabel} {header.weekday} · {header.lunarLabel}</Text>
        <View className='hero-title-row'>
          <Text className='hero-title'>你的命盘，一眼看懂</Text>
          <View className='hero-cursor' />
        </View>
        <Text className='hero-sub'>紫微斗数为核心，排盘在本地完成，不走服务器。</Text>
      </View>

      <View className='home-ming-card'>
        {chart ? (
          <View>
            <Text className='home-ming-kicker'>命宫 · {ming ? stemBranchLabel(ming.stem, ming.branch) : ''}</Text>
            <Text className='home-ming-majors'>{ming ? majorsLine(ming) : '—'}</Text>
            <Text className='home-ming-meta'>
              {chart.birthInfo.name || '未具名'} · {chart.birthInfo.gender === 'male' ? '男' : '女'}
              {patterns.length > 0 ? ` · 格局：${patterns.slice(0, 2).map((p) => p.name).join('、')}` : ''}
            </Text>
            <View className='btn-row' style={{ marginTop: '12px' }}>
              <View className='btn-medley btn-medley-white' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看我的命盘</View>
              <View className='btn-medley home-ming-btn' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>重新排盘</View>
            </View>
          </View>
        ) : (
          <View>
            <Text className='home-ming-kicker'>还没有命盘</Text>
            <Text className='home-ming-majors'>填好出生信息，本地即可排盘</Text>
            <Text className='home-ming-meta'>排盘后首页会显示你的命宫、格局与今年运限。</Text>
            <View style={{ marginTop: '12px' }}><ComposerBar light label='开始排盘' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })} /></View>
            {hasStored ? (
              <View className='btn-medley home-ming-btn home-secondary' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看上次命盘</View>
            ) : null}
          </View>
        )}
      </View>

      <View className='home-sec-head'>
        <Text className='sec-eyebrow'>01 · Fortune</Text>
        <Text className='home-section-title'>今年运限</Text>
      </View>
      {chart ? (
        <View>
          <View className='home-yun-row'>
            <View className='home-yun-card' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>
              <Text className='home-yun-kicker'>今年流年</Text>
              <Text className='home-yun-palace'>{liunianPalace ? liunianPalace.name : '—'}</Text>
              <Text className='home-yun-stars'>{majorsLine(liunianPalace)}</Text>
              <Text className='home-yun-sihua'>流年干 {liunianSihua.stemName}：{sihuaLine(liunianSihua.transforms)}</Text>
            </View>
            <View className='home-yun-card' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>
              <Text className='home-yun-kicker'>本月流月</Text>
              <Text className='home-yun-palace'>{lunarMonthName(todayLunar.getMonth())}（{liuyueCur.stemName}）</Text>
              <Text className='home-yun-stars'>流月四化</Text>
              <Text className='home-yun-sihua'>{sihuaLine(liuyueCur.transforms)}</Text>
            </View>
          </View>
          <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>
            所属大限：{dx ? `${dx.palaceName}（${dx.startAge}-${dx.endAge} 岁）` : '童限或超出范围'}；虚岁 {liunianAge} 岁。
            数据与命盘图页流年 / 流月卡同一算法，点卡片可到命盘图页查看完整运限。
          </Text>
        </View>
      ) : (
        <Card title='今年运限'>
          <Text className='muted'>排盘后，这里会显示今年流年落宫、四化与本月流月四化（与命盘图页同一算法）。</Text>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
        </Card>
      )}

      <View className='home-sec-head'>
        <Text className='sec-eyebrow'>02 · Reading</Text>
        <Text className='home-section-title'>解读</Text>
      </View>
      <Card title='13 维本地解读'>
        {chart ? (
          <View>
            <Text className='muted'>按宫位展开，点维度直达解读页对应位置；解读文本为本站新写，不作命运断言。</Text>
            <View style={{ display: 'flex', flexWrap: 'wrap', marginTop: '12px' }}>
              {dims.map((d) => (
                <Text key={d.id} className='chip chip-accent' style={{ marginRight: '8px', marginBottom: '8px' }} onClick={() => goInterpret(d.id)}>{d.title}</Text>
              ))}
            </View>
          </View>
        ) : (
          <View>
            <Text className='muted'>排盘后可按维度直达解读页：命宫、财帛、事业、感情、健康、子女、手足、迁移、田宅、福德、父母、交友、身宫。</Text>
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
          </View>
        )}
      </Card>

      <View className='home-sec-head'>
        <Text className='sec-eyebrow'>03 · Tools</Text>
        <Text className='home-section-title'>功能</Text>
      </View>
      <View className='home-tile-row'>
        <View className='home-tile' onClick={() => goKnowledge()}>
          <IconBadge name='book-open' dark={dark} />
          <Text className='home-tile-title'>星曜知识</Text>
          <Text className='home-tile-sub'>十四主星与辅星煞星详解</Text>
        </View>
        <View className='home-tile' onClick={() => Taro.navigateTo({ url: '/pages/compare/index' })}>
          <IconBadge name='users' dark={dark} />
          <Text className='home-tile-title'>合盘对照</Text>
          <Text className='home-tile-sub'>两张命盘六宫主星对照</Text>
        </View>
      </View>

      <Disclaimer />
      {adTier === 'free' ? <BannerAd unitId={adSlotLive(adConfig, 'bannerHome')} /> : null}
    </View>
  );
}
