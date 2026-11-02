import { useEffect, useState } from 'react';
import { View, Text, Input } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Solar } from 'lunar-javascript';
import { loadChart, loadInput, stemBranchLabel } from '../../lib/chart';
import { getDaXianIndexForYear } from '../../engine/yunxian-context';
import { getLiuNianSiHua, getLiuYueSiHua } from '../../engine/sihua';
import { detectPatterns } from '../../engine/patterns';
import { buildDimensions } from '../../lib/interpret';
import { goInterpret, setHomeQuestion } from '../../lib/nav';
import { hasLoginFlag } from '../../lib/session';
import type { ZiweiChart } from '../../engine/types';
import { Disclaimer } from '../../components/ui';
import { Icon, IconBadge } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import { BannerAd } from '../../components/ads';
import { callFn, cloudConfigured, type AppConfig, type MembershipStatus } from '../../lib/cloud';
import { adSlotLive } from '../../lib/ads';
import './index.scss';

// 首页第二步（2026-11-02 用户定）：在第一步复现稿的基础上改本站内容与元素。
// 复现稿的骨架与尺寸原样保留：圆球 86pt、标题 26pt/600、副标题 11pt、
// 输入框 52pt + 话筒标；改动只在内容与元素本身：标题副标题换本站文案、
// 输入框从底部挪到圆球下面（标题下方）、5 个健康芯片换成四块本站面板、
// 发送钮换成我们的 Gemini 蓝渐变（尺寸仍是复现稿 52pt）。
// 话筒标是输入框的原样 chrome（复现稿自带），不接点击——全产品都没接
// 语音输入，不给它假功能；上一轮擅自去掉话筒标是错的，本轮恢复。
// 旧首页原样复用的本地小工具（运限算法与命盘图页同一口径，不新编）。
const mod12 = (n: number) => ((n % 12) + 12) % 12;

const LUNAR_MONTHS = ['正月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '冬月', '腊月'];

function lunarMonthName(month: number): string {
  const leap = month < 0;
  const base = LUNAR_MONTHS[Math.abs(month) - 1] ?? '';
  return leap ? '闰' + base : base;
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
  const [question, setQuestion] = useState('');
  const [adConfig, setAdConfig] = useState<AppConfig | null>(null);
  const [adTier, setAdTier] = useState<string | null>(null);

  // 登录守夜（2026-11-02 用户定：登录后进首页）:只有未登录才推欢迎页，
  // 已登录直接留首页。mount-only：tab 页常驻，切换 tab 不重挂载，
  // 不会反复推欢迎页。原生 tabBar 本页可见。
  useEffect(() => {
    if (!hasLoginFlag()) {
      Taro.navigateTo({ url: '/pages/welcome/index' }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (!cloudConfigured()) return;
    callFn<AppConfig>('config', { action: 'get' }).then((c) => { if (c.ok && c.data) setAdConfig(c.data); });
    callFn<MembershipStatus>('membership', { action: 'status' }).then((m) => { if (m.ok && m.data) setAdTier(m.data.tier); });
  }, []);

  // Tab 页常驻不重挂载，每次显示重读本地命盘（旧首页同款做法）。
  useDidShow(() => setChart(loadChart()));

  const hasStored = !!loadInput();
  const ming = chart?.palaces.find((p) => p.isMingGong);
  const patterns = chart ? detectPatterns(chart) : [];

  // 运限（旧首页算法原样：流年支 = 农历年 −4 取余；大限按年取段；
  // 流年四化取年干；流月按农历月序、月份天干五虎遁）。
  const dims = chart ? buildDimensions(chart) : [];
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

  // 首页输入框是真输入框：点发送（或键盘发送）把问题带到对话页预填；
  // 不输问题直接点发送也进对话页（不在首页假装对话）。
  function ask() {
    setHomeQuestion(question.trim());
    setQuestion('');
    Taro.navigateTo({ url: '/pages/chat/index' });
  }

  return (
    <View className={'page home-root theme-' + theme}>
      <View className='hl-chat__sky' />
      <View className='hl-chat__body'>
        <View className='hl-orb'>
          <View className='hl-orb-ring' />
        </View>
        <View className='hl-chat__title'>
          <Text className='hl-title-line'>你好</Text>
          <Text className='hl-title-line'>有什么可以帮你？</Text>
        </View>
        <Text className='hl-chat__sub'>本地排盘，十三维解读，对话随时问。</Text>

        <View className='hl-composer-flow'>
          <View className='hl-input'>
            <Input className='hl-input-field' value={question} onInput={(e) => setQuestion(e.detail.value)} placeholder='问问你的命盘…' placeholderClass='hl-input-ph' confirmType='send' onConfirm={ask} />
            <Icon name='mic' tone='gray' size='17px' />
          </View>
          <View className='hl-send-gemini' hoverClass='btn-press' onClick={ask}>
            <Icon name='arrow-up' tone='white' size='18px' />
          </View>
        </View>

        <View className='home-panel'>
          <Text className='home-panel-title'>命盘锚点</Text>
          {chart ? (
            <View>
              <Text className='home-ming-kicker'>命宫 · {ming ? stemBranchLabel(ming.stem, ming.branch) : ''}</Text>
              <Text className='home-ming-majors'>{ming ? majorsLine(ming) : '—'}</Text>
              <Text className='home-ming-meta'>
                {chart.birthInfo.name || '未具名'} · {chart.birthInfo.gender === 'male' ? '男' : '女'}
                {patterns.length > 0 ? ` · 格局：${patterns.slice(0, 2).map((p) => p.name).join('、')}` : ''}
              </Text>
              <View className='btn-row home-panel-btns'>
                <View className='btn-medley btn-medley-dark' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看我的命盘</View>
                <View className='btn-medley btn-medley-outline-light' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>重新排盘</View>
              </View>
            </View>
          ) : (
            <View>
              <Text className='home-ming-kicker'>还没有命盘</Text>
              <Text className='home-ming-majors'>填好出生信息，本地即可排盘</Text>
              <Text className='home-ming-meta'>排盘后首页会显示你的命宫、格局与今年运限。</Text>
              <View className='btn-row home-panel-btns'>
                <View className='btn-medley btn-medley-dark' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>开始排盘</View>
                {hasStored ? (
                  <View className='btn-medley btn-medley-outline-light' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看上次命盘</View>
                ) : null}
              </View>
            </View>
          )}
        </View>

        <View className='home-panel'>
          <Text className='home-panel-title'>今年运限</Text>
          {chart ? (
            <View>
              <View className='home-mini-row'>
                <View className='home-mini' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>
                  <Text className='home-mini-kicker'>今年流年</Text>
                  <Text className='home-mini-palace'>{liunianPalace ? liunianPalace.name : '—'}</Text>
                  <Text className='home-mini-stars'>{majorsLine(liunianPalace)}</Text>
                  <Text className='home-mini-sihua'>流年干 {liunianSihua.stemName}：{sihuaLine(liunianSihua.transforms)}</Text>
                </View>
                <View className='home-mini' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>
                  <Text className='home-mini-kicker'>本月流月</Text>
                  <Text className='home-mini-palace'>{lunarMonthName(todayLunar.getMonth())}（{liuyueCur.stemName}）</Text>
                  <Text className='home-mini-stars'>流月四化</Text>
                  <Text className='home-mini-sihua'>{sihuaLine(liuyueCur.transforms)}</Text>
                </View>
              </View>
              <Text className='muted home-footnote'>
                所属大限：{dx ? `${dx.palaceName}（${dx.startAge}-${dx.endAge} 岁）` : '童限或超出范围'}；虚岁 {liunianAge} 岁。
                数据与命盘图页流年 / 流月卡同一算法，点卡片可到命盘图页查看完整运限。
              </Text>
            </View>
          ) : (
            <View>
              <Text className='muted'>排盘后，这里会显示今年流年落宫、四化与本月流月四化（与命盘图页同一算法）。</Text>
              <View className='btn-row home-panel-btns'>
                <View className='btn-medley btn-medley-outline-light' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
              </View>
            </View>
          )}
        </View>

        <View className='home-panel'>
          <Text className='home-panel-title'>十三维解读</Text>
          {chart ? (
            <View>
              <Text className='muted'>按宫位展开，点维度直达解读页对应位置；解读文本为本站新写，不作命运断言。</Text>
              <View className='home-chips'>
                {dims.map((d) => (
                  <Text key={d.id} className='chip chip-accent home-chip' onClick={() => goInterpret(d.id)}>{d.title}</Text>
                ))}
              </View>
            </View>
          ) : (
            <View>
              <Text className='muted'>排盘后可按维度直达解读页：命宫、财帛、事业、感情、健康、子女、手足、迁移、田宅、福德、父母、交友、身宫。</Text>
              <View className='btn-row home-panel-btns'>
                <View className='btn-medley btn-medley-outline-light' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
              </View>
            </View>
          )}
        </View>

        <View className='home-panel'>
          <Text className='home-panel-title'>快捷入口</Text>
          <View className='home-tile-row'>
            <View className='home-tile' onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>
              <IconBadge name='star' dark={theme === 'dark'} />
              <Text className='home-tile-title'>排盘</Text>
              <Text className='home-tile-sub'>填出生信息，本地出盘</Text>
            </View>
            <View className='home-tile' onClick={() => Taro.navigateTo({ url: '/pages/chat/index' })}>
              <IconBadge name='message-square' dark={theme === 'dark'} />
              <Text className='home-tile-title'>对话</Text>
              <Text className='home-tile-sub'>结合本盘问点什么</Text>
            </View>
          </View>
        </View>

        <Disclaimer />
        {adTier === 'free' ? <BannerAd unitId={adSlotLive(adConfig, 'bannerHome')} /> : null}
      </View>
    </View>
  );
}
