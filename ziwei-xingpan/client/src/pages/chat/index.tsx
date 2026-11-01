// 对话页：轻量纯对话。云端配置时每轮打包上下文（本盘关键数据
// 摘要 + 会话历史 + 用户问题）发 chat-agent 云函数，返回文本或
// 生图；未配置时本地模板回答（仅复述本盘数据，不耗积分）。
// 计费（云端）：对话文本每日 2M tokens 免费额度，超出按每百万
// tokens 10 积分结算；对话内生图 40 积分/张（失败不扣）。
// 余额不足时显示赚积分途径，不静默失败。注入类问题客户端先拦截
// 提示，云函数会再次检测并以云端结论为准。

import { useState } from 'react';
import { View, Text, Input, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import { loadChart, loadInput } from '../../lib/chart';
import { buildChartSummary, localTemplateAnswer, loadHistory, appendHistory, clearHistory, clientInjectionCheck, type ChatMessage } from '../../lib/chat-agent';
import { profileChartKey } from '../../lib/profiles';
import { callFn, cloudConfigured } from '../../lib/cloud';
import { PRICING, localBalance, EARN_GUIDE } from '../../lib/pricing';
import { LoadingButton } from '../../components/interactions/LoadingButton';
import './index.scss';

interface ChatAgentOk {
  text: string;
  chargedPoints: number;
  tokensUsed: number;
  quotaCoveredTokens: number;
  degraded: boolean;
  truncated: boolean;
  disclaimer: string;
}

export default function Chat() {
  const [theme] = useTheme();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [imagePrompt, setImagePrompt] = useState('');
  const [sending, setSending] = useState(false);
  const [imaging, setImaging] = useState(false);
  const [notice, setNotice] = useState('');
  const [balance, setBalance] = useState<number | null>(null);
  const [chartKey, setChartKey] = useState('');
  const [chartName, setChartName] = useState('');

  useDidShow(() => {
    const input = loadInput();
    const chart = loadChart();
    if (!input || !chart) {
      setChartKey('');
      setChartName('');
      setMessages([]);
      return;
    }
    const key = profileChartKey(input);
    setChartKey(key);
    setChartName(input.name || '当前命盘');
    setMessages(loadHistory(key, PRICING.chat.historyRounds));
    if (cloudConfigured()) {
      callFn<{ balance: number }>('points', { action: 'balance' }).then((res) => {
        if (res.ok) setBalance(res.data.balance);
      }).catch(() => { /* balance display is best-effort */ });
    } else {
      setBalance(localBalance());
    }
  });

  function push(role: 'user' | 'assistant', text: string) {
    const msg: ChatMessage = { role: role, text: text, at: Date.now() };
    setMessages((prev) => [...prev, msg]);
    if (chartKey) appendHistory(chartKey, msg, PRICING.chat.historyRounds);
  }

  async function send() {
    const q = question.trim();
    if (!q || sending) return;
    const chart = loadChart();
    const input = loadInput();
    if (!chart || !input) {
      setNotice('需先排盘：对话需要本盘数据，请先去排盘页排一盘。');
      return;
    }
    const check = clientInjectionCheck(q);
    if (check.blocked) {
      setNotice('这个问题包含指令劫持内容，已拒绝（' + check.categories.join('、') + '）。请换一个与本盘有关的问题。');
      return;
    }
    setQuestion('');
    push('user', q);
    setSending(true);
    setNotice('');
    try {
      if (!cloudConfigured()) {
        const answer = localTemplateAnswer(chart, q);
        push('assistant', answer);
        return;
      }
      const summary = buildChartSummary(chart);
      const history = loadHistory(chartKey, PRICING.chat.historyRounds)
        .filter((m) => m.text.indexOf('__IMAGE__') !== 0)
        .map((m) => ({ role: m.role, text: m.text }));
      const res = await callFn<ChatAgentOk>('chat-agent', {
        action: 'chat', summary: summary, history: history, question: q,
      });
      if (!res.ok) {
        if (res.code === 'INSUFFICIENT_POINTS' || res.code === 'MINOR_QUOTA_EXHAUSTED') {
          push('assistant', '余额不足：' + res.message + ' ' + EARN_GUIDE);
        } else {
          push('assistant', '对话失败：' + res.message + '（未扣费）');
        }
        return;
      }
      const d = res.data;
      let text = d.text;
      if (d.chargedPoints > 0) text += '\n（本轮超出免费额度，扣 ' + d.chargedPoints + ' 积分；共用 ' + d.tokensUsed + ' tokens，其中免费额度覆盖 ' + d.quotaCoveredTokens + ' tokens。）';
      else if (d.tokensUsed > 0) text += '\n（本轮在免费额度内，未扣积分；共用 ' + d.tokensUsed + ' tokens。）';
      if (d.degraded) text += '\n（云端为降级/模板回退，未调用主模型。）';
      push('assistant', text);
      callFn<{ balance: number }>('points', { action: 'balance' }).then((r) => {
        if (r.ok) setBalance(r.data.balance);
      }).catch(() => { /* best-effort */ });
    } catch (e) {
      push('assistant', '对话失败：网络或服务异常（未扣费），请稍后重试。');
    } finally {
      setSending(false);
    }
  }

  async function sendImage() {
    const prompt = imagePrompt.trim();
    if (!prompt || imaging) return;
    if (!cloudConfigured()) {
      setNotice('生图需要云开发：环境 ID 到位后开通，对话内生图 40 积分/张。');
      return;
    }
    setImaging(true);
    setNotice('');
    try {
      const res = await callFn<{ fileID: string; chargedPoints: number }>('chat-agent', {
        action: 'image', prompt: prompt,
      });
      if (!res.ok) {
        setNotice('生图失败：' + res.message);
        return;
      }
      push('assistant', '生图完成（扣 ' + res.data.chargedPoints + ' 积分）：');
      const imgMsg: ChatMessage = { role: 'assistant', text: '__IMAGE__' + res.data.fileID, at: Date.now() };
      setMessages((prev) => [...prev, imgMsg]);
      if (chartKey) appendHistory(chartKey, imgMsg, PRICING.chat.historyRounds);
      setImagePrompt('');
    } catch {
      setNotice('生图失败：网络或服务异常（未扣费），请稍后重试。');
    } finally {
      setImaging(false);
    }
  }

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='AI 对话'>
        {!chartKey ? (
          <Text className='muted'>需先排盘：对话围绕本盘展开，请先去排盘页排一盘，或从档案里选一个人。</Text>
        ) : (
          <View>
            <Text className='muted' style={{ display: 'block' }}>当前盘：{chartName} · {cloudConfigured() ? '云端对话' : '本地模板（未配置云开发，不耗积分）'}</Text>
            {balance !== null ? <Text className='muted' style={{ display: 'block' }}>积分余额：{balance}（对话文本每日 2M tokens 免费，超出每百万 tokens 10 积分）</Text> : null}
          </View>
        )}
        {notice ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{notice}</Text> : null}
      </Card>
      <View className='chat-list'>
        {messages.map((m, i) => (
          <View key={i} className={'chat-msg ' + (m.role === 'user' ? 'chat-msg-user' : 'chat-msg-ai')}>
            {m.text.indexOf('__IMAGE__') === 0 ? (
              <Image className='chat-image' src={m.text.slice('__IMAGE__'.length)} mode='widthFix' />
            ) : (
              <Text className='chat-bubble'>{m.text}</Text>
            )}
          </View>
        ))}
        {messages.length === 0 && chartKey ? (
          <Text className='muted'>试试问：“我的命宫主星是什么？”“今年流年四化怎么看？”——回答只结合本盘数据，超出盘数据会明说不知道。</Text>
        ) : null}
      </View>
      {chartKey ? (
        <View>
          <View className='ask-composer'>
            <Input className='ask-input' value={question} onInput={(e) => setQuestion(e.detail.value)} placeholder='结合本盘问点什么…' confirmType='send' onConfirm={send} />
            <LoadingButton loading={sending} onClick={send} className='ask-send'>发送</LoadingButton>
          </View>
          <View className='ask-composer' style={{ marginTop: '10px' }}>
            <Input className='ask-input' value={imagePrompt} onInput={(e) => setImagePrompt(e.detail.value)} placeholder='生图描述，如：紫微星空海报背景' />
            <LoadingButton loading={imaging} onClick={sendImage} className='ask-send'>生图 40 积分</LoadingButton>
          </View>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => { if (chartKey) { clearHistory(chartKey); setMessages([]); } }}>清空本盘会话</View>
          <Disclaimer />
        </View>
      ) : null}
    </View>
  );
}
