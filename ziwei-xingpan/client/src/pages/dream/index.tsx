import { useState } from 'react';
import { View, Text, Textarea } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { loadDreams, addDream } from '../../lib/tools';
import { goInterpret } from '../../lib/nav';
import { cloudConfigured } from '../../lib/cloud';
import { Ambient, AmbientLight, Card, Disclaimer, EmptyState } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// AI 解梦：梦境只存本机日记；AI 解读走云端通道，未配置时诚实
// 告知、不伪造解读。已配置时引导到解读页的 AI 问答（需先保存命盘）。
export default function Dream() {
  const [theme] = useTheme();
  const [text, setText] = useState('');
  const [dreams, setDreams] = useState(loadDreams());
  const [aiNote, setAiNote] = useState('');

  function saveDream() {
    const v = text.trim();
    if (!v) { Taro.showToast({ title: '请先写下梦境', icon: 'none' }); return; }
    setDreams(addDream(v));
    setText('');
    Taro.showToast({ title: '梦境已保存到本机', icon: 'none' });
  }

  function aiDream() {
    if (!cloudConfigured()) {
      setAiNote('云开发未配置：AI 解梦需环境 ID 后开通，当前不展示伪造解读。');
      return;
    }
    setAiNote('');
    Taro.showToast({ title: '请在解读页 AI 问答中描述你的梦', icon: 'none' });
    goInterpret();
  }

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='AI 解梦'>
        <Text className='muted'>先把梦记下来；AI 解读需云端通道，未配置时不会编造解读给你。</Text>
        <Textarea className='field-textarea' placeholder='写下你的梦（只存在本机）' value={text} onInput={(e) => setText(e.detail.value)} />
        <View className='btn-row' style={{ marginTop: '12px' }}>
          <View className='btn-medley btn-medley-outline-light' onClick={saveDream}>保存梦境</View>
          <View className='btn-medley btn-medley-dark' hoverClass='btn-press' onClick={aiDream}>AI 解梦</View>
        </View>
        {aiNote ? <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>{aiNote}</Text> : null}
      </Card>
      <Card light title='我的梦境日记'>
        {dreams.length === 0 ? <EmptyState title='还没有梦境记录' hint='在上方写下并保存，梦境只会存在本机。' /> : dreams.map((d, i) => (
          <View key={i} className='input-row'>
            <Text className='input-label' style={{ flex: 1, textAlign: 'left' }}>{d.text}</Text>
            <Text className='input-value'>{d.date}</Text>
          </View>
        ))}
      </Card>
      <Disclaimer />
    </View>
  );
}
