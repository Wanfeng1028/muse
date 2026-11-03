import { useMemo, useState } from 'react';
import { View, Text, Picker, Input, Button, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { PROVINCES } from '../../engine/cities';
import { BRANCHES } from '../../engine/constants';
import {
  branchFromClock, formatDate, parseDate, previewCorrections, saveInput,
  shichenLabel, shichenRange, shiftDate, loadInput, type BirthFormInput,
} from '../../lib/chart';
import { Ambient, AmbientLight, Card, ComposerBar, SegmentedControl } from '../../components/ui';
import { getProfile, createProfile, addChartVersion, PROFILE_PICK_KEY, PROFILE_VERSION_TARGET_KEY } from '../../lib/profiles';
import { useTheme } from '../../lib/theme';
import starMark from '../../assets/logo/star-mark.png';
import './index.scss';

const GENDERS = ['男', '女'];

export default function Birth() {
  const [theme] = useTheme();
  const [name, setName] = useState('');
  const [genderIdx, setGenderIdx] = useState(0);
  const [date, setDate] = useState('1995-06-15');
  const [time, setTime] = useState('12:00');
  const [provIdx, setProvIdx] = useState(0);
  const [cityIdx, setCityIdx] = useState(0);
  const [corrections, setCorrections] = useState<string[]>([]);
  const [versionTarget, setVersionTarget] = useState<string | null>(null);
  const [versionTargetName, setVersionTargetName] = useState('');
  const [profileNote, setProfileNote] = useState('');
  const [orig, setOrig] = useState<{ date: string; time: string; branch: number } | null>(null);

  const provinces = useMemo(() => PROVINCES.map((p) => p.name), []);
  const cities = useMemo(() => PROVINCES[provIdx]?.cities ?? [], [provIdx]);
  const clockHour = parseInt(time.split(':')[0], 10);
  const clockMinute = parseInt(time.split(':')[1], 10);
  const branch = branchFromClock(clockHour);
  const province = PROVINCES[provIdx];
  const city = cities[cityIdx] ?? cities[0];

  const draft: BirthFormInput = {
    name, gender: genderIdx === 0 ? 'male' : 'female', date,
    clockHour, clockMinute,
    province: province?.name ?? '', city: city?.name ?? '', longitude: city?.longitude ?? 120,
    branch, corrections,
    originalClockHour: clockHour, originalClockMinute: clockMinute, originalDate: date,
  };
  const preview = previewCorrections(draft);
  const hasStored = !!loadInput();

  // Pick result + version target are read ONCE on show and cleared
  // immediately (same pattern as lib/nav.ts takeDimTarget): the mode
  // then lives in component state, so returning from the chart page
  // keeps it, while abandoning the page drops it (no stale target).
  function fillFromInput(input: BirthFormInput) {
    setName(input.name || '');
    setGenderIdx(input.gender === 'female' ? 1 : 0);
    setDate(input.date);
    setTime(String(input.clockHour).padStart(2, '0') + ':' + String(input.clockMinute).padStart(2, '0'));
    const pi = PROVINCES.findIndex((pr) => pr.name === input.province);
    setProvIdx(pi >= 0 ? pi : 0);
    const cities = pi >= 0 ? PROVINCES[pi].cities : [];
    const ci = cities.findIndex((c) => c.name === input.city);
    setCityIdx(ci >= 0 ? ci : 0);
    setCorrections(input.corrections || []);
    setOrig({
      date: input.originalDate || input.date,
      time: String(input.originalClockHour).padStart(2, '0') + ':' + String(input.originalClockMinute).padStart(2, '0'),
      branch: branchFromClock(input.originalClockHour),
    });
  }

  useDidShow(() => {
    try {
      const pick = Taro.getStorageSync(PROFILE_PICK_KEY) as { profileId: string; version: number } | undefined;
      if (pick) {
        Taro.removeStorageSync(PROFILE_PICK_KEY);
        const p = getProfile(pick.profileId);
        const v = p ? p.charts.find((c) => c.version === pick.version) : null;
        if (v) {
          fillFromInput(v.input);
          setProfileNote('已填入档案「' + p!.name + '」版本 ' + v.version + '，可直接排盘或再校正。');
        }
      }
    } catch {
      // Storage failure: stay on the blank form, do not crash.
    }
    try {
      const target = Taro.getStorageSync(PROFILE_VERSION_TARGET_KEY) as string | undefined;
      if (target) {
        Taro.removeStorageSync(PROFILE_VERSION_TARGET_KEY);
        const p = getProfile(target);
        if (p) {
          fillFromInput(p.input);
          setVersionTarget(p.id);
          setVersionTargetName(p.name);
          setProfileNote('正在为「' + p.name + '」新增版本：保存为档案将追加版本而非新建档案。');
        }
      }
    } catch {
      // Storage failure: stay on the blank form, do not crash.
    }
  });

  function saveAsProfile() {
    if (versionTarget) {
      const v = addChartVersion(versionTarget, draft, '');
      if (!v) {
        Taro.showToast({ title: '追加版本失败：档案不存在', icon: 'none' });
        return;
      }
      setVersionTarget(null);
      setVersionTargetName('');
      Taro.showToast({ title: '已为「' + versionTargetName + '」追加版本 ' + v.version, icon: 'none' });
      Taro.navigateBack();
      return;
    }
    const created = createProfile(draft);
    Taro.showToast({ title: '已保存为档案「' + created.name + '」', icon: 'none' });
  }

  function captureOrig() {
    if (!orig) setOrig({ date, time, branch });
  }

  function applySolar() {
    if (!preview.solar || preview.solarBranch == null) return;
    captureOrig();
    const nextDate = preview.solar.dayOffset ? shiftDate(date, preview.solar.dayOffset) : date;
    const hh = String(preview.solar.hour).padStart(2, '0');
    const mm = String(preview.solar.minute).padStart(2, '0');
    setDate(nextDate);
    setTime(`${hh}:${mm}`);
    setCorrections((c) => c.includes('真太阳时校正') ? c : [...c, '真太阳时校正']);
    Taro.showToast({ title: '已应用真太阳时校正，可撤销', icon: 'none' });
  }

  function applyDst() {
    if (!preview.clockShifted) return;
    captureOrig();
    setTime(preview.clockShifted);
    setCorrections((c) => c.includes('夏令时减1小时') ? c : [...c, '夏令时减1小时']);
    Taro.showToast({ title: '已减 1 小时，可撤销', icon: 'none' });
  }

  function undoCorrections() {
    if (!orig) return;
    setDate(orig.date);
    setTime(orig.time);
    setCorrections([]);
    setOrig(null);
    Taro.showToast({ title: '已撤销全部校正', icon: 'none' });
  }

  function submit() {
    const input: BirthFormInput = {
      ...draft,
      originalClockHour: orig?.time ? parseInt(orig.time.split(':')[0], 10) : clockHour,
      originalClockMinute: orig?.time ? parseInt(orig.time.split(':')[1], 10) : clockMinute,
      originalDate: orig?.date ?? date,
    };
    try {
      saveInput(input);
    } catch (e) {
      Taro.showToast({ title: `排盘失败：${(e as Error).message}`, icon: 'none' });
      return;
    }
    Taro.navigateTo({ url: '/pages/chart/index' });
  }

  return (
    <View className={'page page-welcome theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient welcome />}
      <View className='hero'>
        <View className='hero-brand'>
          <Image className='brand-mark' src={starMark} mode='aspectFit' />
          <Text className='brand-name'>星命盘</Text>
        </View>
        <View className='hero-title-row'>
          <Text className='hero-title'>填写出生信息</Text>
          <View className='hero-cursor' />
        </View>
        <Text className='hero-sub'>排盘在本地完成，不走服务器。</Text>
        <Text className='hero-sub2'>出生信息填好后，点开始排盘即可看到命盘图。</Text>
      </View>
      <Card title='出生信息'>
        {profileNote ? <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>{profileNote}</Text> : null}
        <View className='btn-medley btn-medley-outline-light' style={{ marginBottom: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/profiles/index?pick=1' })}>从档案选择（免重填）</View>
        <View className='input-row'>
          <Text className='input-label'>姓名（可选）</Text>
          <Input className='field-input' placeholder='不填也可排盘' value={name} onInput={(e) => setName(e.detail.value)} />
        </View>
        <View className='input-row input-row-col'>
          <Text className='input-label'>性别</Text>
          <SegmentedControl options={GENDERS} value={genderIdx} onChange={setGenderIdx} tone='dark' />
        </View>
        <View className='input-row'>
          <Text className='input-label'>公历生日</Text>
          <Picker mode='date' value={date} onChange={(e) => setDate(String(e.detail.value))}>
            <Text className='input-value'>{date}</Text>
          </Picker>
        </View>
        <View className='input-row'>
          <Text className='input-label'>出生钟表时间</Text>
          <Picker mode='time' value={time} onChange={(e) => setTime(String(e.detail.value))}>
            <Text className='input-value'>{time}（{shichenLabel(branch)} {shichenRange(branch)}）</Text>
          </Picker>
        </View>
        <View className='input-row'>
          <Text className='input-label'>出生地</Text>
          <Picker
            mode='multiSelector'
            range={[provinces, cities.map((c) => c.name)]}
            value={[provIdx, cityIdx]}
            onColumnChange={(e) => {
              if (e.detail.column === 0) { setProvIdx(e.detail.value); setCityIdx(0); }
              else setCityIdx(e.detail.value);
            }}
            onChange={(e) => { const v = e.detail.value as number[]; setProvIdx(v[0]); setCityIdx(v[1]); }}
          >
            <Text className='input-value'>{province?.name} {city?.name}（经度 {city?.longitude}°）</Text>
          </Picker>
        </View>
      </Card>

      {/* 实时计算预览卡（宫垣 g1 式）：表单下方直接给结果，不改动输入；
          采用校正仍需到下方时间校正卡点按钮。数值随表单输入实时重算。 */}
      <Card title='计算结果预览'>
        <View className='preview-row'>
          <Text className='input-label'>出生地经度</Text>
          <Text className='input-value'>{province?.name} {city?.name} {city?.longitude}°</Text>
        </View>
        <View className='preview-row'>
          <Text className='input-label'>钟表时间</Text>
          <Text className='input-value'>{time}（{shichenLabel(branch)}）</Text>
        </View>
        <View className='preview-row'>
          <Text className='input-label'>真太阳时</Text>
          <Text className='input-value preview-accent'>
            {preview.solar
              ? `${String(preview.solar.hour).padStart(2, '0')}:${String(preview.solar.minute).padStart(2, '0')}（${shichenLabel(preview.solarBranch ?? branch)}）`
              : '—'}
          </Text>
        </View>
        <View className='preview-row'>
          <Text className='input-label'>修正量</Text>
          <Text className='input-value'>
            {preview.solar
              ? `经度 ${preview.solar.longitudeCorrectionMinutes.toFixed(1)} 分钟，均时差 ${preview.solar.equationOfTimeMinutes.toFixed(1)} 分钟`
              : '—'}
          </Text>
        </View>
        <View className='preview-row preview-row-last'>
          <Text className='input-label'>夏令时</Text>
          <Text className='input-value'>{preview.isDst ? `${preview.dstNote}，减 1 小时后为 ${preview.clockShifted}` : '该日期不在中国大陆夏令时期间，无需换算'}</Text>
        </View>
        <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>预览只展示计算结果，不改动你填的时间；要采用校正请到下方时间校正卡点按钮。</Text>
      </Card>

      <Card title='时间校正（手动、可撤销，绝不自动改）'>
        <Text className='muted'>
          默认按你填写的钟表时间排盘。下面两项只作提示，点按钮才会改时间，点撤销可恢复原值。
        </Text>
        {preview.solar ? (
          <View className='corr'>
            <Text className='muted'>
              真太阳时：经度修正 {preview.solar.longitudeCorrectionMinutes.toFixed(1)} 分钟，均时差 {preview.solar.equationOfTimeMinutes.toFixed(1)} 分钟，
              校正后 {String(preview.solar.hour).padStart(2, '0')}:{String(preview.solar.minute).padStart(2, '0')}，
              对应{shichenLabel(preview.solarBranch ?? branch)}{preview.solar.dayOffset !== 0 ? `（日期偏移 ${preview.solar.dayOffset} 天）` : ''}。
            </Text>
            <View className='btn-pill btn-pill-outline-dark' onClick={applySolar}>应用真太阳时校正</View>
          </View>
        ) : null}
        {preview.isDst ? (
          <View className='corr'>
            <Text className='muted'>{preview.dstNote}减 1 小时后为 {preview.clockShifted}。</Text>
            <View className='btn-pill btn-pill-outline-dark' onClick={applyDst}>夏令时减 1 小时</View>
          </View>
        ) : (
          <Text className='muted'>该日期不在中国大陆夏令时期间，无需夏令时换算。</Text>
        )}
        {corrections.length > 0 ? (
          <View className='corr'>
            <Text className='muted'>已应用：{corrections.join('、')}</Text>
            <View className='btn-pill btn-pill-outline-dark' onClick={undoCorrections}>撤销全部校正</View>
          </View>
        ) : null}
        <Text className='caption'>说明：真太阳时按出生地经度与均时差计算；夏令时按中国大陆通行口径表判定。两者都不自动生效。</Text>
      </Card>

      <View className='home-submit'><ComposerBar label='开始排盘' onClick={submit} /></View>
      {hasStored ? (
        <View className='btn-medley btn-medley-outline home-secondary' onClick={() => Taro.navigateTo({ url: '/pages/chart/index' })}>查看上次命盘</View>
      ) : null}
      <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={saveAsProfile}>{versionTarget ? '保存为档案（追加版本）' : '保存为档案'}</View>
      <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>地支对照：{BRANCHES.join(' ')}；时辰以两小时为一档，23:00 后属次日子时口径由排盘引擎处理。</Text>
      <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>从首页的排盘入口来到这里；排盘完成后可在命盘图页查看，也可在首页查看命宫与今年运限。</Text>
    </View>
  );
}
