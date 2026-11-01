import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { Solar } from 'lunar-javascript';
import { loadChart, loadInput, stemBranchLabel, branchLabel, type BirthFormInput } from '../../lib/chart';
import { callFn, cloudConfigured } from '../../lib/cloud';
import { getDaXianIndexForYear, getDaXianStartYear } from '../../engine/yunxian-context';
import { getLiuNianSiHua, getLiuYueSiHua } from '../../engine/sihua';
import { jiangQianShenName, suiQianShenName, boshiShenName } from '../../engine/shier-shen';
import { STEMS } from '../../engine/constants';
import type { Palace, ZiweiChart } from '../../engine/types';
import { Ambient, AmbientLight, Card, Disclaimer, SegmentedControl } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import { goInterpret } from '../../lib/nav';
import { buildDimensions } from '../../lib/interpret';
import './index.scss';

// 4x4 grid slots in reading order; null = center 2x2 area (handled as one cell).
const GRID: Array<number | null> = [5, 6, 7, 8, 4, null, null, 9, 3, null, null, 10, 2, 1, 0, 11];
const GRID_BRANCHES = GRID.filter((b): b is number => b !== null);
const SIHUA_CLASS: Record<string, string> = { '禄': 'sihua-lu', '权': 'sihua-quan', '科': 'sihua-ke', '忌': 'sihua-ji' };
const mod12 = (n: number) => ((n % 12) + 12) % 12;
// 三方四正（传统口径）：三合 = 本宫顺数 4 格、8 格（申子辰之类）；
// 对宫 = 本宫 +6 格。选中宫的三方四正即 本宫 + 三合两宫 + 对宫。
function sanFangSiZheng(b: number) {
  return { sanhe: [mod12(b + 4), mod12(b + 8)], duigong: mod12(b + 6) };
}

function PalaceCell({ p, chart, selected, liunianBranch, xiaoxianBranch, onSelect }: {
  p: Palace; chart: ZiweiChart; selected: boolean;
  liunianBranch: number; xiaoxianBranch: number; onSelect: (b: number) => void;
}) {
  const majors = p.stars.filter((s) => s.type === 'major');
  const minors = p.stars.filter((s) => s.type === 'minor');
  const luckies = p.stars.filter((s) => s.type === 'lucky');
  const shas = p.stars.filter((s) => s.type === 'sha');
  const rest = p.stars.filter((s) => s.type !== 'major' && s.type !== 'minor' && s.type !== 'lucky' && s.type !== 'sha');
  const yearBranch = chart.lunarInfo.yearBranch;
  const yearStem = chart.lunarInfo.yearStem;
  const gender = chart.birthInfo.gender;
  const cls = ['palace', `palace-b${p.branch}`];
  if (p.isCurrentDaXian) cls.push('current');
  if (selected) cls.push('selected');
  return (
    <View className={cls.join(' ')} onClick={() => onSelect(p.branch)}>
      <View className='palace-head'>
        <Text className='palace-branch'>{stemBranchLabel(p.stem, p.branch)}</Text>
        <Text className='palace-name'>{p.name}</Text>
      </View>
      {p.isMingGong ? <Text className='palace-tag'>命</Text> : null}
      {p.isShenGong ? <Text className='palace-tag'>身</Text> : null}
      {p.branch === liunianBranch ? <Text className='palace-tag palace-tag-liunian'>流年</Text> : null}
      {p.branch === xiaoxianBranch ? <Text className='palace-tag palace-tag-xiaoxian'>小限</Text> : null}
      {majors.map((s) => (
        <View key={s.name} className='star-major'>
          <Text>{s.name}</Text>
          {s.brightnessRaw ? <Text className='star-bright'>{s.brightnessRaw}</Text> : null}
          {s.siHua ? <Text className={SIHUA_CLASS[s.siHua] ?? ''}>化{s.siHua}</Text> : null}
        </View>
      ))}
      {minors.length > 0 ? (
        <View className='star-others star-minor'>{minors.map((s) => s.name).join(' ')}</View>
      ) : null}
      {luckies.length > 0 ? (
        <View className='star-others star-lucky'>{luckies.map((s) => s.name).join(' ')}</View>
      ) : null}
      {shas.length > 0 ? (
        <View className='star-others star-sha'>{shas.map((s) => s.name).join(' ')}</View>
      ) : null}
      {rest.length > 0 ? (
        <View className='star-others star-borrowed'>{rest.map((s) => s.name).join(' ')}</View>
      ) : null}
      {p.isEmpty && p.borrowedStars?.length ? (
        <View className='star-others star-borrowed'>借对宫：{p.borrowedStars.join(' ')}</View>
      ) : null}
      <View className='shensha'>
        {jiangQianShenName(yearBranch, p.branch)} · {suiQianShenName(yearBranch, p.branch)} · {boshiShenName(yearStem, gender, p.branch)}
      </View>
      {p.daXianAge ? <View className='daxian-age'>{p.daXianAge[0]}-{p.daXianAge[1]} 岁</View> : null}
    </View>
  );
}

type Center = { x: number; y: number };
type Geometry = { w: number; h: number; centers: Record<number, Center> };

// One rotated segment View: from (x1,y1) to (x2,y2). Plain Views, not
// <svg>: WeChat has no native svg element, so SVG lines would render
// nothing on device. Measured centers are grid-relative, so the layer
// sits exactly over its own grid (position: relative on .chart-grid).
function LineSeg({ x1, y1, x2, y2, color }: { x1: number; y1: number; x2: number; y2: number; color: string }) {
  const len = Math.hypot(x2 - x1, y2 - y1);
  const ang = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
  return (
    <View
      className='chart-line'
      style={{ left: x1, top: y1, width: len, backgroundColor: color, transform: `rotate(${ang}deg)` }}
    />
  );
}

function ChartGrid({ chart, input, selectedBranch, onSelect, liunianBranch, xiaoxianBranch, scope }: {
  chart: ZiweiChart; input: BirthFormInput | null; selectedBranch: number; onSelect: (b: number) => void;
  liunianBranch: number; xiaoxianBranch: number; scope: string;
}) {
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const byBranch = (b: number) => chart.palaces.find((p) => p.branch === b)!;

  // Measure at runtime: grid rows are content-height (NOT square), so
  // percentage-based line coordinates would misalign vertically.
  // Retries cover late layout; if all fail, lines stay hidden and the
  // grid itself still works (honest degradation, no fake geometry).
  useEffect(() => {
    let alive = true;
    let attempts = 0;
    const measure = () => {
      attempts += 1;
      const q = Taro.createSelectorQuery();
      q.select(`.${scope}`).boundingClientRect();
      GRID_BRANCHES.forEach((b) => { q.select(`.${scope} .palace-b${b}`).boundingClientRect(); });
      // Taro exec results are untyped (any) by API design; guarded below
      // by the all-rects-present check before any geometry is used.
      q.exec((res: any[]) => {
        if (!alive) return;
        const grid = res?.[0];
        const rects = res?.slice(1);
        if (!grid || !rects || rects.some((r: any) => !r)) {
          if (attempts < 4) setTimeout(measure, attempts * 300);
          return;
        }
        const centers: Record<number, Center> = {};
        GRID_BRANCHES.forEach((b, i) => {
          const r = rects[i];
          centers[b] = { x: r.left - grid.left + r.width / 2, y: r.top - grid.top + r.height / 2 };
        });
        setGeometry({ w: grid.width, h: grid.height, centers });
      });
    };
    const t = setTimeout(measure, 150);
    return () => { alive = false; clearTimeout(t); };
  }, [chart, scope]);

  const sfs = sanFangSiZheng(selectedBranch);
  const sel = geometry?.centers[selectedBranch];
  const tri = geometry ? [sel!, geometry.centers[sfs.sanhe[0]], geometry.centers[sfs.sanhe[1]]] : null;
  const dui = geometry ? geometry.centers[sfs.duigong] : null;

  return (
    <View className={`chart-grid ${scope}`}>
      {GRID.map((b, i) => {
        if (b === null) {
          if (i === 5) {
            return (
              <View key='center' className='chart-center'>
                <View className='brand-dots center-dots'>
                  <View className='brand-dot brand-dot-green' />
                  <View className='brand-dot brand-dot-blue' />
                  <View className='brand-dot brand-dot-pink' />
                </View>
                <Text className='center-name'>{chart.birthInfo.name || '未具名'} · {chart.birthInfo.gender === 'male' ? '男' : '女'}</Text>
                <Text className='center-line'>农历 {chart.lunarInfo.lunarYear} 年 {Math.abs(chart.lunarInfo.lunarMonth)} 月 {chart.lunarInfo.lunarDay} 日{chart.lunarInfo.isLeapMonth ? '（闰月）' : ''}</Text>
                <Text className='center-line'>{chart.wuxingJuName} · 命主 {chart.mingZhu} · 身主 {chart.shenZhu}</Text>
                <Text className='center-line'>{chart.yinYangGender} · 虚岁 {chart.currentAge} 岁</Text>
                <Text className='center-line'>命宫 {branchLabel(chart.mingGongBranch)} · 身宫 {branchLabel(chart.shenGongBranch)}</Text>
                {input?.corrections?.length ? <Text className='center-line'>已应用：{input.corrections.join('、')}</Text> : null}
              </View>
            );
          }
          return null;
        }
        return (
          <PalaceCell
            key={b}
            p={byBranch(b)}
            chart={chart}
            selected={b === selectedBranch}
            liunianBranch={liunianBranch}
            xiaoxianBranch={xiaoxianBranch}
            onSelect={onSelect}
          />
        );
      })}
      {geometry && tri && dui && sel ? (
        <View className='chart-lines-layer' style={{ width: geometry.w, height: geometry.h }}>
          <LineSeg x1={tri[0].x} y1={tri[0].y} x2={tri[1].x} y2={tri[1].y} color='#5ec8a7' />
          <LineSeg x1={tri[1].x} y1={tri[1].y} x2={tri[2].x} y2={tri[2].y} color='#5ec8a7' />
          <LineSeg x1={tri[2].x} y1={tri[2].y} x2={tri[0].x} y2={tri[0].y} color='#5ec8a7' />
          <LineSeg x1={sel.x} y1={sel.y} x2={dui.x} y2={dui.y} color='#e3ac45' />
          <View className='chart-vertex' style={{ left: tri[1].x, top: tri[1].y, backgroundColor: '#5ec8a7' }} />
          <View className='chart-vertex' style={{ left: tri[2].x, top: tri[2].y, backgroundColor: '#5ec8a7' }} />
          <View className='chart-vertex' style={{ left: dui.x, top: dui.y, backgroundColor: '#e3ac45' }} />
        </View>
      ) : null}
    </View>
  );
}

export default function ChartPage() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  const [input, setInput] = useState(loadInput());
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [seg, setSeg] = useState(0);
  const [fullScreen, setFullScreen] = useState(false);
  useEffect(() => { setChart(loadChart()); setInput(loadInput()); }, []);

  async function saveChart() {
    if (!chart || !input) return;
    if (!cloudConfigured()) {
      Taro.showToast({ title: '云开发未配置，命盘历史需环境 ID 后开通', icon: 'none' });
      return;
    }
    setSaving(true);
    const res = await callFn<{ chartId: string }>('charts', {
      action: 'create',
      name: chart.birthInfo.name || '我的命盘',
      birthParams: input,
      chartData: chart,
    });
    setSaving(false);
    if (res.ok) {
      setSaved(true);
      Taro.showToast({ title: '已保存到我的命盘', icon: 'none' });
    } else {
      Taro.showToast({ title: '保存失败：' + res.code, icon: 'none' });
    }
  }

  if (!chart) {
    return (
      <View className={'page theme-' + theme}>
        {theme === 'light' ? <AmbientLight /> : <Ambient />}
        <Card title='还没有命盘'>
          <Text className='muted'>请先填写出生信息并排盘。</Text>
          <View className='btn-medley btn-medley-white' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>去排盘</View>
        </Card>
      </View>
    );
  }

  // 分段条（参照的合盘/天象/本命/行运/三限/次限分段，只借结构）：
  // 紫微仍为核心，不做西洋轮盘与三限/次限；本命=盘面，大运/流年/
  // 流月=滚动到对应卡片，合盘=对照页。天象对应星象日历，见首页三卡。
  const SEGMENTS = ['本命', '大运', '流年', '流月', '合盘'];
  function scrollToId(id: string) {
    const q = Taro.createSelectorQuery();
    q.selectViewport().scrollOffset();
    q.select('#' + id).boundingClientRect();
    q.exec((res: any[]) => {
      const off = res?.[0];
      const r = res?.[1];
      if (r) Taro.pageScrollTo({ scrollTop: (off?.scrollTop ?? 0) + r.top - 12, duration: 300 });
    });
  }
  function onSegment(i: number) {
    if (i === 4) { Taro.navigateTo({ url: '/pages/compare/index' }); return; }
    setSeg(i);
    if (i === 0) { Taro.pageScrollTo({ scrollTop: 0, duration: 300 }); return; }
    if (i === 1) { scrollToId('chart-daxian'); return; }
    scrollToId('chart-liunian');
  }

  const byBranch = (b: number) => chart.palaces.find((p) => p.branch === b)!;
  const now = new Date();
  const todayLunar = Solar.fromYmd(now.getFullYear(), now.getMonth() + 1, now.getDate()).getLunar();
  const liunianYear = todayLunar.getYear();
  const liunianAge = liunianYear - chart.lunarInfo.lunarYear + 1;
  const dxIdx = getDaXianIndexForYear(chart, liunianYear);
  const dx = dxIdx >= 0 ? chart.daXians[dxIdx] : null;
  const liunianSihua = getLiuNianSiHua(liunianYear);
  const liuyue = Array.from({ length: 12 }, (_, i) => getLiuYueSiHua(liunianSihua.stemIndex, i + 1));
  // 流年支：农历年 −4 取余（2024 甲辰 → 辰，验算通过）。
  const liunianBranch = mod12(liunianYear - 4);
  // 小限支（通行口径）：男顺数、女逆数，从生年支起数虚岁。
  const xiaoxianBranch = chart.birthInfo.gender === 'male'
    ? mod12(chart.lunarInfo.yearBranch + liunianAge - 1)
    : mod12(chart.lunarInfo.yearBranch - (liunianAge - 1));
  const selectedBranch = selected ?? chart.mingGongBranch;
  const selPalace = byBranch(selectedBranch);
  const sfs = sanFangSiZheng(selectedBranch);
  const selMajors = selPalace.stars.filter((s) => s.type === 'major');
  const selDim = buildDimensions(chart).find((d) => d.palaceName === selPalace.name);

  // Detail card, single source for main view and fullscreen overlay
  // (render method, not an inner component, per project convention).
  // compact = fullscreen focus view: main stars + dimension body only;
  // the full version adds 三方四正 / 大运 / 流年 / 小限 lines + hint.
  const renderDetail = (compact: boolean) => (
    <Card title={`${selPalace.name} · ${stemBranchLabel(selPalace.stem, selPalace.branch)}`}>
      <Text className='detail-line'>
        主星：{selMajors.length ? selMajors.map((s) => `${s.name}${s.brightnessRaw ?? ''}${s.siHua ? `化${s.siHua}` : ''}`).join(' ') : '无主星'}
        {selPalace.isEmpty && selPalace.borrowedStars?.length ? `（借对宫：${selPalace.borrowedStars.join(' ')}）` : ''}
      </Text>
      {compact ? null : (
        <Text className='detail-line'>
          三方四正：三合 {byBranch(sfs.sanhe[0]).name}、{byBranch(sfs.sanhe[1]).name}，对宫 {byBranch(sfs.duigong).name}
        </Text>
      )}
      {!compact && selPalace.daXianAge ? (
        <Text className='detail-line'>大运：{selPalace.daXianAge[0]}-{selPalace.daXianAge[1]} 岁</Text>
      ) : null}
      {!compact && selectedBranch === liunianBranch ? <Text className='detail-line detail-liunian'>今年流年落此宫</Text> : null}
      {!compact && selectedBranch === xiaoxianBranch ? <Text className='detail-line detail-xiaoxian'>今年小限落此宫</Text> : null}
      {selDim ? <Text className='detail-body'>{selDim.body}</Text> : null}
      {compact ? null : (
        <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>点任意宫位切换选中；金色边为选中宫，三合碧色三角与对宫金色线随选中宫变化。</Text>
      )}
    </Card>
  );

  return (
    <View className={'page theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <View style={{ marginBottom: '12px' }}>
        <SegmentedControl options={SEGMENTS} value={seg} onChange={onSegment} tone={theme === 'light' ? 'light' : 'dark'} />
      </View>
      <View className='chart-plate'>
        <ChartGrid
          chart={chart}
          input={input}
          selectedBranch={selectedBranch}
          onSelect={setSelected}
          liunianBranch={liunianBranch}
          xiaoxianBranch={xiaoxianBranch}
          scope='chart-grid-main'
        />
      </View>

      {/* 宫位详情卡（宫垣 g2 式）：盘下直接跟选中宫的主星 + 解读。 */}
      {renderDetail(false)}

      <View className='btn-row chart-actions'>
        <View className='btn-medley btn-medley-white' onClick={saveChart}>
          {saving ? '保存中…' : saved ? '已保存，去“我的 → 档案管理”查看' : '保存到我的命盘'}
        </View>
        <View className='btn-medley btn-medley-outline' onClick={() => setFullScreen(true)}>全屏查看</View>
        {saved ? (
          <View className='btn-medley btn-medley-outline' onClick={() => Taro.switchTab({ url: '/pages/mine/index' })}>去我的页查看档案管理</View>
        ) : null}
      </View>

      <View className='btn-medley btn-medley-dark chart-ai-cta' hoverClass='btn-press' onClick={() => goInterpret()}>AI 解读星盘</View>

      <View id='chart-daxian'>
      <Card title='大运'>
        {chart.daXians.map((d, i) => (
          <View key={`${d.startAge}-${d.palaceBranch}`} className='daxian-row'>
            <Text>{d.startAge}-{d.endAge} 岁 · {d.palaceName}（{branchLabel(d.palaceBranch)}）</Text>
            {i === chart.currentDaXianIndex ? <Text className='chip chip-accent'>当前</Text> : null}
            {dxIdx === i ? <Text className='chip'>本年所属</Text> : null}
            {getDaXianStartYear(chart, i) != null ? <Text className='muted'> 约 {getDaXianStartYear(chart, i)} 农历年起</Text> : null}
          </View>
        ))}
      </Card>

      </View>

      <View id='chart-liunian'>
      <Card title={`流年 / 流月（今年农历 ${liunianYear} 年，虚岁 ${liunianAge} 岁）`}>
        <Text className='muted'>
          所属大限：{dx ? `${dx.palaceName}（${dx.startAge}-${dx.endAge} 岁）` : '童限或超出范围'}；
          流年干 {liunianSihua.stemName}：化禄 {liunianSihua.transforms['禄']}、化权 {liunianSihua.transforms['权']}、
          化科 {liunianSihua.transforms['科']}、化忌 {liunianSihua.transforms['忌']}。
        </Text>
        <View style={{ marginTop: '10px' }}>
          {liuyue.map((m) => (
            <View key={m.month} className='liuyue-row'>
              <Text>{m.month} 月（{STEMS[m.stemIndex]}）</Text>
              <Text className='muted'> 禄 {m.transforms['禄']} · 权 {m.transforms['权']} · 科 {m.transforms['科']} · 忌 {m.transforms['忌']}</Text>
            </View>
          ))}
        </View>
        <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>流月按农历月序排列，月份天干用五虎遁推算。</Text>
      </Card>
      </View>
      <Disclaimer />

      {fullScreen ? (
        <View className='chart-fullscreen'>
          <View className='chart-fullscreen-bar'>
            <Text className='chart-fullscreen-title'>全屏命盘（点宫位可切换选中）</Text>
            <View className='btn-pill btn-pill-black' onClick={() => setFullScreen(false)}>关闭</View>
          </View>
          <View className='chart-plate'>
            <ChartGrid
              chart={chart}
              input={input}
              selectedBranch={selectedBranch}
              onSelect={setSelected}
              liunianBranch={liunianBranch}
              xiaoxianBranch={xiaoxianBranch}
              scope='chart-grid-full'
            />
          </View>
          {renderDetail(true)}
        </View>
      ) : null}
    </View>
  );
}
