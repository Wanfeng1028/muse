import { View, Text, Picker } from '@tarojs/components';
import type { SavedChart } from '../lib/cloud';

// 合盘对照视图：mine 的“合盘对照”section 与 pages/compare 独立页共用。
// 宫名必须用引擎原名（命宫 / 财帛 / 官禄 / 夫妻 / 疾厄 / 福德，不带
// “宫”后缀）。2026-11-01 前 mine 版误用“财帛宫”等带后缀名，
// palaceMajors 查不到宫、只显示“—”，本轮抽出时一并修正。
const PALACES = ['命宫', '财帛', '官禄', '夫妻', '疾厄', '福德'];

export function palaceMajors(c: SavedChart, palaceName: string): string {
  const p = c.chartData.palaces.find((x) => x.name === palaceName);
  if (!p) return '—';
  const majors = p.stars.filter((s) => s.type === 'major').map((s) => s.name);
  return majors.length ? majors.join(' ') : '无主星';
}

export default function CompareView({ charts, aId, bId, onA, onB, labelClass, locked }: {
  charts: SavedChart[];
  aId: string;
  bId: string;
  onA: (id: string) => void;
  onB: (id: string) => void;
  labelClass?: string;
  // locked=true hides the six-palace results (pickers stay visible).
  // Callers set it while the 60-point compare charge is pending or
  // unpaid, so results are never shown before payment.
  locked?: boolean;
}) {
  const label = labelClass || 'input-label';
  const a = charts.find((c) => c._id === aId) || null;
  const b = charts.find((c) => c._id === bId) || null;
  if (charts.length < 2) {
    return <Text className='muted'>合盘需要至少两张已保存的命盘，请先保存两张盘再来对照。</Text>;
  }
  return (
    <View>
      <View className='input-row'>
        <Text className={label}>第一张盘</Text>
        <Picker mode='selector' range={charts.map((c) => c.name)} value={charts.findIndex((c) => c._id === aId)} onChange={(e) => onA(charts[Number(e.detail.value)]._id)}>
          <Text className='input-value'>{a ? a.name : '请选择'}</Text>
        </Picker>
      </View>
      <View className='input-row'>
        <Text className={label}>第二张盘</Text>
        <Picker mode='selector' range={charts.map((c) => c.name)} value={charts.findIndex((c) => c._id === bId)} onChange={(e) => onB(charts[Number(e.detail.value)]._id)}>
          <Text className='input-value'>{b ? b.name : '请选择'}</Text>
        </Picker>
      </View>
      {a && b && !locked ? PALACES.map((p) => (
        <View key={p} className='input-row'>
          <Text className={label}>{p}</Text>
          <Text className='input-value'>{palaceMajors(a, p)} ｜ {palaceMajors(b, p)}</Text>
        </View>
      )) : null}
      <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>对照仅罗列双方各宫主星，不作合婚、关系或吉凶断言。</Text>
    </View>
  );
}
