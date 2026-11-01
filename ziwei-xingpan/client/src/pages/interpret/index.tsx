import { useEffect, useState } from 'react';
import { View, Text, Input, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { loadChart, loadInput, type BirthFormInput } from '../../lib/chart';
import { buildDimensions } from '../../lib/interpret';
import { profileChartKey } from '../../lib/profiles';
import {
  resolvePricing, localSpend, isDimUnlocked, unlockDimLocal,
  isAllUnlocked, unlockAllLocal, hideBanner, hideInterstitial,
  EARN_GUIDE, type Tier,
} from '../../lib/pricing';
import { recordReport } from '../../lib/reports';
import { takeDimTarget } from '../../lib/nav';
import { detectPatterns } from '../../engine/patterns';
import type { ZiweiChart } from '../../engine/types';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { Icon } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import { LoadingButton } from '../../components/interactions';
import { BannerAd } from '../../components/ads';
import {
  callFn, cloudConfigured, tempFileURL,
  type AppConfig, type MembershipStatus, type SavedChart,
  type AiResult, type AiImageResult,
} from '../../lib/cloud';
import { adSlotLive, showInterstitialOnce } from '../../lib/ads';
import './index.scss';

export default function Interpret() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  const [input, setInput] = useState<BirthFormInput | null>(null);
  const [, setUnlockTick] = useState(0);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [tier, setTier] = useState<string | null>(null);
  const [defaultChartId, setDefaultChartId] = useState('');
  const [aiText, setAiText] = useState('');
  const [aiMeta, setAiMeta] = useState('');
  const [aiError, setAiError] = useState('');
  const [question, setQuestion] = useState('');
  const [askAnswer, setAskAnswer] = useState('');
  const [dailyUrl, setDailyUrl] = useState('');
  const [busy, setBusy] = useState('');

  // Same tab-staleness rule as Home: 解读 is a tab page, so the local
  // chart must reload on every show, not just on mount. recordReport
  // is day-deduped, so re-showing on the same day records nothing new.
  useDidShow(() => {
    const c = loadChart();
    setChart(c);
    setInput(loadInput());
    if (c) recordReport();
  });

  useEffect(() => {
    async function boot() {
      if (!cloudConfigured()) return;
      // Membership first: the interstitial suppress flag depends on tier.
      const m = await callFn<MembershipStatus>('membership', { action: 'status' });
      const tierValue = (m.ok && m.data ? m.data.tier : 'free') as Tier;
      if (m.ok && m.data) setTier(m.data.tier);
      const c = await callFn<AppConfig>('config', { action: 'get' });
      if (c.ok && c.data) {
        setConfig(c.data);
        showInterstitialOnce(c.data, hideInterstitial(tierValue, resolvePricing(c.data)));
      }
      const list = await callFn<{ charts: SavedChart[] }>('charts', { action: 'list' });
      if (list.ok && list.data) {
        const d = list.data.charts.find((x) => x.isDefault) || list.data.charts[0];
        if (d) setDefaultChartId(d._id);
      }
    }
    boot();
  }, []);

  function toast(title: string) {
    Taro.showToast({ title, icon: 'none' });
  }

  // Dimension unlocks (pure-points model: no tier exempts dimension
  // fees; Pro/Max only remove ads / grant free HD export / annual).
  // Cloud has no dimension-unlock set yet, so a successful cloud
  // spend is mirrored into the local unlock set (pending-17 migrates
  // it server-side); the unlock CHECK reads the local set in both
  // modes, so a paid unlock is never charged twice.
  const chartKey = input ? profileChartKey(input) : '';
  function dimUnlocked(dimId: string): boolean {
    if (!chartKey) return false;
    return isDimUnlocked(chartKey, dimId) || isAllUnlocked(chartKey);
  }
  async function unlockDim(dimId: string) {
    if (!chartKey || dimUnlocked(dimId)) return;
    setBusy('unlock-' + dimId);
    try {
      if (cloudConfigured()) {
        const r = await callFn<{ delta: number; balance: number }>('points', { action: 'spend', rule: 'dimInterpret' });
        if (!r.ok) { toast('积分不足：单维解读需 20 积分。' + EARN_GUIDE); return; }
        unlockDimLocal(chartKey, dimId);
      } else {
        const r = localSpend('dimInterpret');
        if (!r.ok) { toast('积分不足：单维解读需 20 积分，当前 ' + ('balance' in r ? r.balance : 0) + '。' + EARN_GUIDE); return; }
        unlockDimLocal(chartKey, dimId);
      }
      setUnlockTick((t) => t + 1);
      toast('已解锁本维（同盘同维永久免费）。');
    } finally {
      setBusy('');
    }
  }
  async function unlockAll() {
    if (!chartKey || isAllUnlocked(chartKey)) return;
    setBusy('unlock-all');
    try {
      if (cloudConfigured()) {
        const r = await callFn<{ delta: number; balance: number }>('points', { action: 'spend', rule: 'advancedInterpret' });
        if (!r.ok) { toast('积分不足：全量解读需 100 积分。' + EARN_GUIDE); return; }
        unlockAllLocal(chartKey);
      } else {
        const r = localSpend('advancedInterpret');
        if (!r.ok) { toast('积分不足：全量解读需 100 积分，当前 ' + ('balance' in r ? r.balance : 0) + '。' + EARN_GUIDE); return; }
        unlockAllLocal(chartKey);
      }
      setUnlockTick((t) => t + 1);
      toast('已解锁全部 13 维。');
    } finally {
      setBusy('');
    }
  }

  function explainAiError(code: string): string {
    if (code === 'MINOR_AI_BLOCKED') return '未成年人不可使用 AI 解读（含会员免费额度），基础解读与知识科普仍可免费使用。';
    if (code === 'INSUFFICIENT_POINTS') return '积分不足：AI 解读需 30 积分（Max 不限次、Pro 每月 20 次免费），请到“我的 → 积分中心”领取或兑换。';
    if (code === 'AI_UNAVAILABLE') return 'AI 服务暂不可用（主备通道均失败），请稍后重试；未扣积分、未返回伪造文本。';
    if (code === 'CHART_NOT_FOUND') return '命盘不存在或不属于当前用户，请先在命盘图页保存当前命盘。';
    return 'AI 调用失败：' + code;
  }

  async function aiInterpret() {
    if (!defaultChartId) { toast('请先在命盘图页保存当前命盘'); return; }
    setBusy('interpret');
    setAiError('');
    const res = await callFn<AiResult>('ai', { action: 'interpret', chartId: defaultChartId, interpretType: 'full' });
    setBusy('');
    if (!res.ok) { setAiError(explainAiError(res.code)); return; }
    setAiText(res.data.text);
    setAiMeta('通道：' + res.data.provider + (res.data.cached ? '（缓存命中，未扣费、未重复调模型）' : '')
      + (res.data.degraded ? '（已降级到备用通道：' + (res.data.degradedReason || '') + '）' : '')
      + '；本次扣积分：' + (res.data.chargedPoints || 0));
  }

  async function aiAsk() {
    if (!defaultChartId) { toast('请先在命盘图页保存当前命盘'); return; }
    if (!question.trim()) { toast('请先填写问题'); return; }
    setBusy('ask');
    setAiError('');
    const res = await callFn<AiResult>('ai', { action: 'ask', chartId: defaultChartId, question: question.trim() });
    setBusy('');
    if (!res.ok) { setAiError(explainAiError(res.code)); return; }
    setAskAnswer(res.data.text);
  }

  async function dailyImage() {
    if (!defaultChartId) { toast('请先在命盘图页保存当前命盘'); return; }
    setBusy('daily');
    const res = await callFn<AiImageResult>('aiImage', { chartId: defaultChartId, kind: 'daily' });
    setBusy('');
    if (!res.ok) { toast('今日运势配图失败：' + res.code); return; }
    const url = await tempFileURL(res.data.fileID);
    if (url) setDailyUrl(url);
    else toast('配图链接获取失败');
  }

  // 首页维度 chips 带 ?dim= 进来时，滚动到对应维度（本地 13 维解读，
  // 无需云端）。锚点在下方每个维度气泡的 id 上。深链有两路：H5
  // 直链的 router 参数，以及 Tab 切页（switchTab 不带参数）经
  // lib/nav.ts 存储中转的落点；chart 为空时不取存储（不提前消费）。
  useEffect(() => {
    if (!chart) return;
    const dim = (Taro.getCurrentInstance().router?.params as any)?.dim as string | undefined || takeDimTarget();
    if (!dim) return;
    const t = setTimeout(() => {
      const q = Taro.createSelectorQuery();
      q.selectViewport().scrollOffset();
      q.select('#dim-' + dim).boundingClientRect();
      q.exec((res: any[]) => {
        const off = res?.[0];
        const r = res?.[1];
        if (r) Taro.pageScrollTo({ scrollTop: (off?.scrollTop ?? 0) + r.top - 12, duration: 300 });
      });
    }, 500);
    return () => clearTimeout(t);
  }, [chart]);

  if (!chart) {
    return (
      <View className={'page theme-' + theme}>
        {theme === 'light' ? <AmbientLight /> : <Ambient />}
        <Card title='还没有命盘'>
          <Text className='muted'>请先排盘，解读会基于该盘生成。AI 解读还需先在命盘图页把当前盘保存到档案管理。</Text>
          <View className='btn-medley btn-medley-white' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
        </Card>
      </View>
    );
  }
  const dims = buildDimensions(chart);
  const patterns = detectPatterns(chart);
  return (
    <View className={'page theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <View className='interp-msg'>
        <View className='chat-meta'><View className='chat-dot' /><Text>格局判断</Text></View>
        {patterns.length === 0 ? (
          <View className='interp-bubble'><Text>本盘未触发格局库中的常见组合，仍宜以各宫主星与三方四正综合看。</Text></View>
        ) : patterns.map((p) => (
          <View key={p.name} className='pattern-card' style={{ marginBottom: '10px', paddingLeft: '10px' }}>
            <Text className='pattern-name'>{p.name}</Text>
            <Text className='muted' style={{ display: 'block', marginTop: '4px' }}>{p.description}</Text>
            <Text className='caption' style={{ display: 'block' }}>涉及：{p.palaces.join('、')}</Text>
          </View>
        ))}
        <Disclaimer />
      </View>
      {dims.map((d) => {
        const unlocked = dimUnlocked(d.id);
        return (
          <View key={d.id} id={'dim-' + d.id} className='interp-msg'>
            <View className='chat-meta'><View className='chat-dot' /><Text>{d.title} · {d.palaceName}</Text></View>
            <View className='interp-bubble'><Text>{d.brief}</Text></View>
            {unlocked ? (
              <View className='interp-bubble' style={{ marginTop: '8px' }}><Text>{d.body}</Text></View>
            ) : (
              <View style={{ marginTop: '8px' }}>
                <Text className='muted'>完整解读需解锁（同盘同维永久免费；全量 100 积分解锁全部 13 维）。</Text>
                <View style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                  <LoadingButton loading={busy === 'unlock-' + d.id} onClick={() => unlockDim(d.id)} className='btn-medley btn-medley-white'>解锁本维（20 积分）</LoadingButton>
                  <LoadingButton loading={busy === 'unlock-all'} onClick={unlockAll} className='btn-medley btn-medley-outline'>解锁全部（100 积分）</LoadingButton>
                </View>
              </View>
            )}
            <Disclaimer />
          </View>
        );
      })}
      <View className='interp-msg'>
        <View className='chat-meta'><View className='chat-dot' /><Text>AI 解盘</Text></View>
        <Text className='muted'>云开发对话 token 主力，额度不足时切换 BotsRouter 备用</Text>
        {!cloudConfigured() ? (
          <Text className='muted'>云开发未配置：AI 解读需环境 ID 后开通，当前不展示虚假解读。</Text>
        ) : !defaultChartId ? (
          <Text className='muted'>请先在命盘图页点“保存到我的命盘”，AI 解读基于已保存的命盘进行（同一命盘按盘 hash 缓存，命中不扣费）。</Text>
        ) : (
          <View>
            <LoadingButton loading={busy === 'interpret'} onClick={aiInterpret} className='btn-medley btn-medley-white'>AI 解盘（本盘）</LoadingButton>
            {aiText ? <View className='interp-msg'><View className='interp-bubble'><Text>{aiText}</Text></View></View> : null}
            {aiMeta ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{aiMeta}</Text> : null}
            {aiError ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{aiError}</Text> : null}
            <Disclaimer />
          </View>
        )}
      </View>
      <View className='interp-msg'>
        <View className='chat-meta'><View className='chat-dot' /><Text>AI 问答</Text></View>
        <Text className='muted'>就本盘提问，不缓存</Text>
        {!cloudConfigured() ? (
          <Text className='muted'>云开发未配置，AI 问答暂不可用。</Text>
        ) : !defaultChartId ? (
          <Text className='muted'>请先在命盘图页保存当前命盘。</Text>
        ) : (
          <View>
            <View className='composer ask-composer'>
              <Input className='composer-input' placeholder='例如：今年财帛方面宜注意什么' value={question} onInput={(e) => setQuestion(e.detail.value)} />
              <View className='composer-send' hoverClass='btn-press' onClick={aiAsk}>
                <Icon name='arrow-up' tone='white' size='38px' />
              </View>
            </View>
            {busy === 'ask' ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>思考中…</Text> : null}
            {askAnswer ? <View className='interp-msg'><View className='interp-bubble'><Text>{askAnswer}</Text></View></View> : null}
            <Disclaimer />
          </View>
        )}
      </View>
      <View className='interp-msg'>
        <View className='chat-meta'><View className='chat-dot' /><Text>今日运势配图</Text></View>
        <Text className='muted'>AI 生图，按日期 + 盘 hash 缓存</Text>
        {!cloudConfigured() ? (
          <Text className='muted'>云开发未配置，生图暂不可用。</Text>
        ) : !defaultChartId ? (
          <Text className='muted'>请先在命盘图页保存当前命盘。</Text>
        ) : (
          <View>
            <View className='btn-medley btn-medley-outline' onClick={dailyImage}>{busy === 'daily' ? '生成中…' : '生成今日运势配图'}</View>
            {dailyUrl ? <Image src={dailyUrl} style={{ width: '100%', height: '220px', marginTop: '12px', borderRadius: '16px' }} /> : null}
          </View>
        )}
      </View>
      {tier && !hideBanner(tier as Tier, resolvePricing(config)) ? <BannerAd unitId={adSlotLive(config, 'bannerInterpret')} /> : null}
      {/* H5 fallback mount (weapp injects the custom tabBar natively). */}
    </View>
  );
}
