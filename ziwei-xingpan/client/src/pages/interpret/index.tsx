import { useEffect, useState } from 'react';
import { View, Text, Input, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { loadChart } from '../../lib/chart';
import { buildDimensions } from '../../lib/interpret';
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
import CustomTabBar from '../../custom-tab-bar';
import './index.scss';

export default function Interpret() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
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

  useEffect(() => {
    setChart(loadChart());
    async function boot() {
      if (!cloudConfigured()) return;
      const c = await callFn<AppConfig>('config', { action: 'get' });
      if (c.ok && c.data) {
        setConfig(c.data);
        showInterstitialOnce(c.data);
      }
      const m = await callFn<MembershipStatus>('membership', { action: 'status' });
      if (m.ok && m.data) setTier(m.data.tier);
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

  if (!chart) {
    return (
      <View className={'page theme-' + theme}>
        {theme === 'light' ? <AmbientLight /> : <Ambient />}
        <Card title='还没有命盘'>
          <Text className='muted'>请先在首页排盘，解读会基于该盘生成。AI 解读还需先在命盘图页把当前盘保存到命盘历史。</Text>
          <View className='btn-medley btn-medley-white' style={{ marginTop: '12px' }} onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>去首页排盘</View>
        </Card>
      </View>
    );
  }
  const dims = buildDimensions(chart);
  const patterns = detectPatterns(chart);
  return (
    <View className={'page theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <View className='chat-msg'>
        <View className='chat-meta'><View className='chat-dot' /><Text>格局判断</Text></View>
        {patterns.length === 0 ? (
          <View className='chat-bubble'><Text>本盘未触发格局库中的常见组合，仍宜以各宫主星与三方四正综合看。</Text></View>
        ) : patterns.map((p) => (
          <View key={p.name} className='pattern-card' style={{ marginBottom: '10px', paddingLeft: '10px' }}>
            <Text className='pattern-name'>{p.name}</Text>
            <Text className='muted' style={{ display: 'block', marginTop: '4px' }}>{p.description}</Text>
            <Text className='caption' style={{ display: 'block' }}>涉及：{p.palaces.join('、')}</Text>
          </View>
        ))}
        <Disclaimer />
      </View>
      {dims.map((d) => (
        <View key={d.id} className='chat-msg'>
          <View className='chat-meta'><View className='chat-dot' /><Text>{d.title} · {d.palaceName}</Text></View>
          <View className='chat-bubble'><Text>{d.body}</Text></View>
          <Disclaimer />
        </View>
      ))}
      <View className='chat-msg'>
        <View className='chat-meta'><View className='chat-dot' /><Text>AI 解盘</Text></View>
        <Text className='muted'>云开发对话 token 主力，额度不足时切换 BotsRouter 备用</Text>
        {!cloudConfigured() ? (
          <Text className='muted'>云开发未配置：AI 解读需环境 ID 后开通，当前不展示虚假解读。</Text>
        ) : !defaultChartId ? (
          <Text className='muted'>请先在命盘图页点“保存到我的命盘”，AI 解读基于已保存的命盘进行（同一命盘按盘 hash 缓存，命中不扣费）。</Text>
        ) : (
          <View>
            <LoadingButton loading={busy === 'interpret'} onClick={aiInterpret} className='btn-medley btn-medley-white'>AI 解盘（本盘）</LoadingButton>
            {aiText ? <View className='chat-msg'><View className='chat-bubble'><Text>{aiText}</Text></View></View> : null}
            {aiMeta ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{aiMeta}</Text> : null}
            {aiError ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{aiError}</Text> : null}
            <Disclaimer />
          </View>
        )}
      </View>
      <View className='chat-msg'>
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
            {askAnswer ? <View className='chat-msg'><View className='chat-bubble'><Text>{askAnswer}</Text></View></View> : null}
            <Disclaimer />
          </View>
        )}
      </View>
      <View className='chat-msg'>
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
      {tier === 'free' ? <BannerAd unitId={adSlotLive(config, 'bannerInterpret')} /> : null}
      {/* H5 fallback mount (weapp injects the custom tabBar natively). */}
      {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
    </View>
  );
}
