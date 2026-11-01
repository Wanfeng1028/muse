import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { calendarMonth, dayInfo } from '../../lib/fortune';
import { Ambient, AmbientLight, Card, Disclaimer, SegmentedControl } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 万年历 / 老黄历 / 星宿：同一月历 + 选中日，分段切换详情。
// 全部数据取 lunar-javascript 1.7.3 实测方法（宜忌、冲煞、星宿、
// 节气、节日、干支日分开取天干地支）；日五行该库无方法，故不展示，
// 不编造。月历周日为首列。
const TABS = ['日历', '黄历', '星宿'];
const TAB_KEYS = ['calendar', 'huangli', 'xingsu'];
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
const XIU28: Array<{ name: string; yao: string }> = [
  { name: '角', yao: '木蛟' }, { name: '亢', yao: '金龙' }, { name: '氐', yao: '土貉' },
  { name: '房', yao: '日兔' }, { name: '心', yao: '月狐' }, { name: '尾', yao: '火虎' },
  { name: '箕', yao: '水豹' }, { name: '斗', yao: '木獬' }, { name: '牛', yao: '金牛' },
  { name: '女', yao: '土蝠' }, { name: '虚', yao: '日鼠' }, { name: '危', yao: '月燕' },
  { name: '室', yao: '火猪' }, { name: '壁', yao: '水貐' }, { name: '奎', yao: '木狼' },
  { name: '娄', yao: '金狗' }, { name: '胃', yao: '土雉' }, { name: '昴', yao: '日鸡' },
  { name: '毕', yao: '月乌' }, { name: '觜', yao: '火猴' }, { name: '参', yao: '水猿' },
  { name: '井', yao: '木犴' }, { name: '鬼', yao: '金羊' }, { name: '柳', yao: '土獐' },
  { name: '星', yao: '日马' }, { name: '张', yao: '月鹿' }, { name: '翼', yao: '火蛇' },
  { name: '轸', yao: '水蚓' },
];

export default function CalendarPage() {
  const [theme] = useTheme();
  const [tab, setTab] = useState(0);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [sel, setSel] = useState({ y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() });

  useEffect(() => {
    const t = (Taro.getCurrentInstance().router?.params as any)?.tab as string | undefined;
    const i = TAB_KEYS.indexOf(t ?? '');
    if (i >= 0) setTab(i);
  }, []);

  function shiftMonth(delta: number) {
    let y = year;
    let m = month + delta;
    if (m < 1) { y -= 1; m = 12; }
    if (m > 12) { y += 1; m = 1; }
    setYear(y);
    setMonth(m);
  }

  const weeks = calendarMonth(year, month, now);
  const info = dayInfo(sel.y, sel.m, sel.d);
  const todayInfo = dayInfo(now.getFullYear(), now.getMonth() + 1, now.getDate());

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <SegmentedControl options={TABS} value={tab} onChange={setTab} tone={theme === 'light' ? 'light' : 'dark'} />
      <Card light title={`${year}年${month}月`}>
        <View style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
          <View className='btn-pill btn-pill-outline-light' onClick={() => shiftMonth(-1)}>上月</View>
          <View className='btn-pill btn-pill-outline-light' onClick={() => { setYear(now.getFullYear()); setMonth(now.getMonth() + 1); setSel({ y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() }); }}>回到今天</View>
          <View className='btn-pill btn-pill-outline-light' onClick={() => shiftMonth(1)}>下月</View>
        </View>
        <View className='cal-weekdays'>
          {WEEKDAYS.map((w) => (<Text key={w} className='cal-weekday'>{w}</Text>))}
        </View>
        {weeks.map((week, wi) => (
          <View key={wi} className='cal-week'>
            {week.map((c) => {
              const cls = ['cal-cell'];
              if (!c.inMonth) cls.push('cal-cell-dim');
              if (c.isToday) cls.push('cal-cell-today');
              if (c.y === sel.y && c.m === sel.m && c.d === sel.d) cls.push('cal-cell-selected');
              return (
                <View key={`${c.y}-${c.m}-${c.d}`} className={cls.join(' ')} onClick={() => setSel({ y: c.y, m: c.m, d: c.d })}>
                  <Text className='cal-cell-day'>{c.d}</Text>
                  <Text className='cal-cell-lunar'>{c.lunarLabel}</Text>
                  {c.jieqi ? <Text className='cal-cell-mark'>{c.jieqi}</Text> : null}
                  {c.festivals ? <Text className='cal-cell-mark'>{c.festivals}</Text> : null}
                </View>
              );
            })}
          </View>
        ))}
        <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>点任意一天查看该日详情；节气与节日直接标在格子里。</Text>
      </Card>

      {tab === 0 ? (
        <Card light title={`选中日 · ${sel.y}年${sel.m}月${sel.d}日`}>
          <Text className='muted'>{info.lunarFull}</Text>
          <Text className='muted' style={{ display: 'block' }}>干支日：{info.ganzhiDay}日</Text>
          {info.jieqi ? <Text className='muted' style={{ display: 'block' }}>节气：{info.jieqi}</Text> : null}
          {info.festivals ? <Text className='muted' style={{ display: 'block' }}>节日：{info.festivals}</Text> : null}
          <Text className='muted' style={{ display: 'block' }}>当日生肖：{info.dayShengxiao} · 值日星宿：{info.xiu || '—'}</Text>
        </Card>
      ) : null}

      {tab === 1 ? (
        <Card light title={`老黄历 · ${sel.y}年${sel.m}月${sel.d}日`}>
          <Text className='muted'>{info.lunarFull} · 干支 {info.ganzhiDay}日 · 当日生肖 {info.dayShengxiao} · 冲 {info.chong || '—'} · 煞 {info.sha || '—'}</Text>
          <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>宜</Text>
          <View className='yi-row'>
            {info.yi.length ? info.yi.map((y) => (<Text key={y} className='yi-chip'>{y}</Text>)) : <Text className='muted'>—</Text>}
          </View>
          <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>忌</Text>
          <View className='yi-row'>
            {info.ji.length ? info.ji.map((j) => (<Text key={j} className='ji-chip'>{j}</Text>)) : <Text className='muted'>—</Text>}
          </View>
          <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>宜忌、冲煞、干支日取 lunar-javascript 当日数据；日五行该库无方法，故不展示，不编造。</Text>
        </Card>
      ) : null}

      {tab === 2 ? (
        <Card light title='星宿'>
          <Text className='muted'>今日值日宿：{todayInfo.xiu || '—'}（取 lunar-javascript 当日数据）。</Text>
          <Text className='muted' style={{ display: 'block', marginTop: '6px' }}>选中日值日宿：{info.xiu || '—'}</Text>
          <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>二十八宿名与七曜为传统公共知识；值日宿按当日计算。</Text>
          {XIU28.map((x) => (
            <View key={x.name} className='input-row'>
              <Text className='input-label'>{x.name}宿 · {x.yao}</Text>
              <Text className='input-value'>{todayInfo.xiu === x.name ? '今日值日' : info.xiu === x.name ? '选中日值日' : ''}</Text>
            </View>
          ))}
        </Card>
      ) : null}
      <Disclaimer />
    </View>
  );
}
