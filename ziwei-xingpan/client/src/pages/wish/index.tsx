import { useEffect, useState } from 'react';
import { View, Text, Textarea } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { loadWishes, addWish, prayerToday, doPrayer } from '../../lib/tools';
import { Ambient, AmbientLight, Card, Disclaimer, SegmentedControl, EmptyState } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 许愿 / 祈福：只存本机自己的记录，不展示他人数据，不含“多少人
// 实现”类说法；祈福每日一次，连续天数只算自己的连续记录。
export default function Wish() {
  const [theme] = useTheme();
  const [tab, setTab] = useState(0);
  const [text, setText] = useState('');
  const [wishes, setWishes] = useState(loadWishes());
  const [prayer, setPrayer] = useState(prayerToday());

  useEffect(() => {
    const t = (Taro.getCurrentInstance().router?.params as any)?.tab as string | undefined;
    if (t === 'prayer') setTab(1);
    else if (t === 'wish') setTab(0);
  }, []);

  function submitWish() {
    const v = text.trim();
    if (!v) { Taro.showToast({ title: '请先写下愿望', icon: 'none' }); return; }
    setWishes(addWish(v));
    setText('');
    Taro.showToast({ title: '愿望已保存到本机', icon: 'none' });
  }

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <SegmentedControl options={['许愿', '祈福']} value={tab} onChange={setTab} tone={theme === 'light' ? 'light' : 'dark'} />
      {tab === 0 ? (
        <View>
          <Card light title='许下一个愿望'>
            <Textarea className='field-textarea' placeholder='写下你的愿望，只存在本机' value={text} onInput={(e) => setText(e.detail.value)} />
            <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={submitWish}>许愿</View>
          </Card>
          <Card light title='我的愿望'>
            {wishes.length === 0 ? <EmptyState title='还没有愿望' hint='在上方写下第一个愿望，它只会存在本机。' /> : wishes.map((w, i) => (
              <View key={i} className='input-row'>
                <Text className='input-label' style={{ flex: 1, textAlign: 'left' }}>{w.text}</Text>
                <Text className='input-value'>{w.date}</Text>
              </View>
            ))}
          </Card>
        </View>
      ) : (
        <View>
          <Card light title='今日祈福'>
            <Text className='tool-mid' style={{ display: 'block' }}>{prayer.line}</Text>
            <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>
              {prayer.doneToday ? '今日已祈福。' : '今日还没有祈福。'}
              {prayer.streak > 0 ? `连续祈福 ${prayer.streak} 天（只算你自己的记录）。` : ''}
            </Text>
            {!prayer.doneToday ? (
              <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={() => { const r = doPrayer(); setPrayer(prayerToday()); Taro.showToast({ title: `祈福完成，连续 ${r.streak} 天`, icon: 'none' }); }}>祈福</View>
            ) : null}
          </Card>
          <Text className='caption'>祈福文案为本站新写，每日按日期轮换一句；不含他人数据与“多少人获得好运”类说法。</Text>
        </View>
      )}
      <Disclaimer />
    </View>
  );
}
