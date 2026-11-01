// 人物档案（命例库）页：列表 + 详情 + pick 模式。
// - 列表态：档案名、性别、日期、城市、版本数、人格迷你徽标。
// - 详情态：档案字段、版本列表、PersonaCard、排盘 / 编辑 / 删除
//   （删除用 LongPressConfirm 900ms）、新增版本、删除某版本。
// - pick 模式（?pick=1，birth 页“从档案选择”进入）：点档案或
//   版本即写 zw_profile_pick 并 navigateBack，birth 页显示时取走。
// - “新建档案”按钮进 birth 页（birth 即新建入口，本页不另做表单）。
// 云端同步待 envId 后开通（pending 17）；本页只读写本地档案。

import { useState } from 'react';
import { View, Text, Input } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { LongPressConfirm } from '../../components/interactions/LongPressConfirm';
import PersonaCard from '../../components/persona';
import { useTheme } from '../../lib/theme';
import {
  listProfiles, getProfile, updateProfile, deleteProfile, deleteChartVersion,
  PROFILE_PICK_KEY, PROFILE_VERSION_TARGET_KEY, latestChart, type Profile,
} from '../../lib/profiles';
import { personaForChart } from '../../lib/persona';
import { saveInput } from '../../lib/chart';
import { shareChart, defaultShareEarn } from '../../lib/share';
import './index.scss';

export default function Profiles() {
  const [theme] = useTheme();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [pickMode, setPickMode] = useState(false);
  const [editName, setEditName] = useState('');
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState('');

  function refresh() {
    setProfiles(listProfiles());
  }

  useDidShow(() => {
    const params = (Taro.getCurrentInstance().router?.params as any) || {};
    setPickMode(params.pick === '1');
    refresh();
    if (detailId) {
      const p = getProfile(detailId);
      if (p) setEditName(p.name);
    }
  });

  function openDetail(p: Profile) {
    setDetailId(p.id);
    setEditName(p.name);
    setEditing(false);
  }

  function pick(profileId: string, version: number) {
    try {
      Taro.setStorageSync(PROFILE_PICK_KEY, { profileId: profileId, version: version });
    } catch {
      // Storage failure: stay on the page and report instead of a
      // silent navigateBack that drops the pick.
      setNotice('档案选择失败：本地存储不可用，请重试。');
      return;
    }
    Taro.navigateBack();
  }

  async function shareLatest(detail: Profile) {
    const latest = latestChart(detail);
    if (!latest) return;
    const result = await shareChart({ profileId: detail.id, version: latest.version, name: detail.name }, defaultShareEarn);
    setNotice(result.shared ? '已分享最新盘（版本 ' + latest.version + '）' + (result.granted ? '，+' + result.granted + ' 积分（每日 1 次）' : '') : '分享未完成：' + result.note + '（未发积分）');
  }

  function useForChart(p: Profile, version?: number) {
    const c = version !== undefined
      ? p.charts.find((x) => x.version === version) || null
      : latestChart(p);
    if (!c) return;
    saveInput(c.input);
    Taro.navigateTo({ url: '/pages/chart/index' });
  }

  function saveEdit(p: Profile) {
    const name = editName.trim();
    if (!name) {
      setNotice('姓名不能为空。');
      return;
    }
    updateProfile(p.id, { name: name });
    setEditing(false);
    refresh();
    setNotice('已保存档案名。');
  }

  function removeProfile(p: Profile) {
    if (deleteProfile(p.id)) {
      setDetailId(null);
      refresh();
      setNotice('已删除档案「' + p.name + '」。');
    }
  }

  function removeVersion(p: Profile, version: number) {
    if (!deleteChartVersion(p.id, version)) {
      setNotice('无法删除该版本：档案至少保留一张盘。');
      return;
    }
    refresh();
    setNotice('已删除版本 ' + version + '。');
  }

  function newVersion(p: Profile) {
    try {
      Taro.setStorageSync(PROFILE_VERSION_TARGET_KEY, p.id);
    } catch {
      setNotice('新增版本失败：本地存储不可用，请重试。');
      return;
    }
    Taro.navigateTo({ url: '/pages/birth/index' });
  }

  const detail = detailId ? getProfile(detailId) : null;

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      {notice ? <Text className='muted' style={{ display: 'block', marginBottom: '12px' }}>{notice}</Text> : null}
      {pickMode && !detail ? (
        <Card light title='选择档案'>
          <Text className='muted'>点一个人设为排盘对象（用最新盘；进详情可挑指定版本）。</Text>
        </Card>
      ) : null}
      {!detail ? (
        <Card light title='人物档案'>
          {profiles.length === 0 ? (
            <Text className='muted'>还没有档案。点“新建档案”填一次 birth 信息，以后排盘、合盘、分享都不用重填。</Text>
          ) : profiles.map((p) => {
            const latest = latestChart(p);
            return (
              <View key={p.id} className='profile-row'>
                <View style={{ flex: 1 }} onClick={() => { if (pickMode) { if (latest) pick(p.id, latest.version); } else openDetail(p); }}>
                  <Text className='profile-name'>{p.name}（{p.gender === 'male' ? '男' : '女'}）</Text>
                  <Text className='muted' style={{ display: 'block' }}>{p.input.date} · {p.input.province}{p.input.city} · {p.charts.length} 张盘</Text>
                </View>
                {latest ? (
                  <View style={{ width: '64px' }} onClick={() => openDetail(p)}>
                    <PersonaCard preset={personaForChart(latest.chart)} compact />
                  </View>
                ) : null}
              </View>
            );
          })}
          <View className='btn-medley btn-medley-dark' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/birth/index' })}>新建档案</View>
        </Card>
      ) : (
        <Card light title={'档案 · ' + detail.name}>
          <Text className='muted' style={{ display: 'block' }}>{detail.gender === 'male' ? '男' : '女'} · {detail.input.date} · {detail.input.province}{detail.input.city}（{detail.input.city}经度 {detail.input.longitude}）</Text>
          <Text className='muted' style={{ display: 'block' }}>校正状态：{detail.input.corrections.length > 0 ? detail.input.corrections.join('、') : '未校正（钟表时间直接排盘）'}</Text>
          {latestChart(detail) ? (
            <View style={{ marginTop: '12px' }}>
              <PersonaCard preset={personaForChart(latestChart(detail)!.chart)} compact />
            </View>
          ) : null}
          <View className='btn-medley btn-medley-dark' style={{ marginTop: '12px' }} onClick={() => useForChart(detail)}>用此档案排盘</View>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => newVersion(detail)}>新增版本（不同校正并存）</View>
          {editing ? (
            <View style={{ marginTop: '12px' }}>
              <Input className='input-field' value={editName} onInput={(e) => setEditName(e.detail.value)} placeholder='档案名' />
              <View className='btn-medley btn-medley-dark' style={{ marginTop: '10px' }} onClick={() => saveEdit(detail)}>保存姓名</View>
              <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => setEditing(false)}>取消</View>
            </View>
          ) : (
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => setEditing(true)}>编辑姓名</View>
          )}
          <View style={{ marginTop: '16px' }}>
            <Text className='profile-section'>盘版本（{detail.charts.length}）</Text>
            {detail.charts.map((c) => (
              <View key={c.version} className='profile-version'>
                <View style={{ flex: 1 }}>
                  <Text className='profile-version-label'>{c.label}（版本 {c.version}）</Text>
                  <Text className='muted' style={{ display: 'block' }}>{c.input.date} {String(c.input.clockHour).padStart(2, '0')}:{String(c.input.clockMinute).padStart(2, '0')} · {c.input.corrections.length > 0 ? c.input.corrections.join('、') : '未校正'}</Text>
                </View>
                <View className='btn-pill btn-pill-black' onClick={() => { if (pickMode) pick(detail.id, c.version); else useForChart(detail, c.version); }}>{pickMode ? '选此版本' : '排盘'}</View>
                <LongPressConfirm onConfirm={() => removeVersion(detail, c.version)} hint='长按删除此版本'>
                  <View className='btn-pill btn-pill-outline-light'>删除</View>
                </LongPressConfirm>
              </View>
            ))}
          </View>
          {latestChart(detail) ? (
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => shareLatest(detail)}>微信分享最新盘（只读，成功分享 +5 积分/日）</View>
          ) : null}
          <LongPressConfirm onConfirm={() => removeProfile(detail)} hint='长按删除整个档案'>
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '16px' }}>删除档案</View>
          </LongPressConfirm>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => setDetailId(null)}>返回列表</View>
        </Card>
      )}
      <Disclaimer />
    </View>
  );
}
