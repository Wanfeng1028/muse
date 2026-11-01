import { useEffect, useState } from 'react';
import { View, Text, Input, Textarea, Image } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { Ambient, AmbientLight, Card, Disclaimer, SegmentedControl, EmptyState } from '../../components/ui';
import { Icon, IconBadge, type IconName } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import CustomTabBar from '../../custom-tab-bar';
import { Toggle, ParticleBurst, LongPressConfirm } from '../../components/interactions';
import { PosterCard } from '../../components/poster';
import CompareView from '../../components/compare';
import { loadReports, type ReportItem } from '../../lib/tools';
import starMark from '../../assets/logo/star-mark.png';
import { loadChart, STORAGE_INPUT, STORAGE_CHART } from '../../lib/chart';
import type { ZiweiChart } from '../../engine/types';
import {
  callFn, loginFlow, cloudConfigured, deviceFingerprint, tempFileURL,
  formatYuan, formatDateTime, isPlaceholderAdUnit,
  RULE_LABELS, PLAN_NAMES, ORDER_STATUS_NAMES,
  type CloudUser, type MembershipStatus, type OrderDoc,
  type LedgerEntry, type InviteInfo, type AppConfig, type SavedChart,
} from '../../lib/cloud';
import { PRIVACY_POLICY, TERMS_OF_SERVICE, MINOR_PROTECTION, ABOUT_TEXT } from '../../lib/legal';
import './index.scss';

type Section = 'main' | 'member' | 'points' | 'invite' | 'orders' | 'settings' | 'feedback' | 'legal' | 'charts' | 'compare' | 'poster' | 'reports';
type LegalTab = 'privacy' | 'terms' | 'minor' | 'about';

const GENDERS = ['未知', '男', '女'];
const PLANS = ['proMonthly', 'proContinuous', 'maxMonthly', 'maxContinuous'];
const LEGAL_TABS: Array<{ key: LegalTab; label: string; text: string }> = [
  { key: 'privacy', label: '隐私政策', text: PRIVACY_POLICY },
  { key: 'terms', label: '用户协议', text: TERMS_OF_SERVICE },
  { key: 'minor', label: '未成年人保护', text: MINOR_PROTECTION },
  { key: 'about', label: '关于（含数据来源）', text: ABOUT_TEXT },
];

export default function Mine() {
  const [theme, applyTheme] = useTheme();
  const [section, setSection] = useState<Section>('main');
  const [legalTab, setLegalTab] = useState<LegalTab>('privacy');
  const [user, setUser] = useState<CloudUser | null>(null);
  const [membership, setMembership] = useState<MembershipStatus | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [orders, setOrders] = useState<OrderDoc[]>([]);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [feedbacks, setFeedbacks] = useState<Array<{ content: string; contact: string; status: string; createdAt: string }>>([]);
  const [savedCharts, setSavedCharts] = useState<SavedChart[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [localChart, setLocalChart] = useState<ZiweiChart | null>(null);
  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [notice, setNotice] = useState('');
  const [failed, setFailed] = useState<string[]>([]);
  const [busy, setBusy] = useState('');
  const [nickname, setNickname] = useState('');
  const [genderIdx, setGenderIdx] = useState(0);
  const [birthYearStr, setBirthYearStr] = useState('');
  const [isMinorSwitch, setIsMinorSwitch] = useState(false);
  const [signinBurst, setSigninBurst] = useState(0);
  const [bindCode, setBindCode] = useState('');
  const [fbContent, setFbContent] = useState('');
  const [fbContact, setFbContact] = useState('');
  const [qrUrl, setQrUrl] = useState('');
  const [qrNote, setQrNote] = useState('');

  const configured = cloudConfigured();
  const failedHas = (k: string) => failed.indexOf(k) !== -1;

  async function refreshAll() {
    setLocalChart(loadChart());
    setReports(loadReports());
    if (!configured) {
      setNotice('云开发未配置：登录、会员、积分、邀请、订单功能需用户提供云开发环境 ID 后开通；下方各入口均如实显示未配置状态，不展示虚假数据。');
      return;
    }
    setNotice('');
    const login = await loginFlow({ nickname: nickname || undefined, gender: genderIdx || undefined });
    if (!login.ok) {
      setNotice('登录失败：' + login.code + ' ' + login.message);
      return;
    }
    setUser(login.data.user);
    if (login.data.user.nickname) setNickname(login.data.user.nickname);
    if (login.data.user.gender) setGenderIdx(login.data.user.gender);
    if (login.data.user.birthYear) setBirthYearStr(String(login.data.user.birthYear));
    setIsMinorSwitch(!!login.data.user.minor);
    const fails: string[] = [];
    const m = await callFn<MembershipStatus>('membership', { action: 'status' });
    if (m.ok) setMembership(m.data); else fails.push('会员');
    const p = await callFn<{ balance: number; ledger: LedgerEntry[] }>('points', { action: 'balance' });
    if (p.ok) { setBalance(p.data.balance); setLedger(p.data.ledger); } else fails.push('积分');
    const iv = await callFn<InviteInfo>('invite', { action: 'info' });
    if (iv.ok) setInvite(iv.data); else fails.push('邀请');
    const o = await callFn<{ orders: OrderDoc[] }>('order', { action: 'list' });
    if (o.ok) setOrders(o.data.orders); else fails.push('订单');
    const c = await callFn<AppConfig>('config', { action: 'get' });
    if (c.ok) setConfig(c.data); else fails.push('配置');
    const f = await callFn<{ feedbacks: Array<{ content: string; contact: string; status: string; createdAt: string }> }>('feedback', { action: 'list' });
    if (f.ok) setFeedbacks(f.data.feedbacks); else fails.push('反馈');
    const ch = await callFn<{ charts: SavedChart[] }>('charts', { action: 'list' });
    if (ch.ok) setSavedCharts(ch.data.charts); else fails.push('命盘');
    setFailed(fails);
    if (fails.length > 0) setNotice('以下数据加载失败（不是空数据）：' + fails.join('、') + '。请稍后点“刷新”重试。');
  }

  useEffect(() => { refreshAll(); }, []);

  // Same tab-staleness rule as Home: local chart + local report history
  // reload on every show (cheap, no cloud calls); cloud refresh stays
  // mount-only + the manual 刷新 button.
  useDidShow(() => { setLocalChart(loadChart()); setReports(loadReports()); });

  function toast(title: string) {
    Taro.showToast({ title, icon: 'none' });
  }

  async function buy(plan: string) {
    setBusy('buy-' + plan);
    const res = await callFn<{ orderId: string; outTradeNo: string; amountFen: number; payment: any }>('order', { action: 'create', plan });
    setBusy('');
    if (!res.ok) {
      if (res.code === 'PAY_NOT_CONFIGURED') {
        toast('微信支付未配置，订单已建为待支付，可在订单中查看');
        refreshAll();
        return;
      }
      toast('下单失败：' + res.code);
      return;
    }
    if (!res.data.payment) {
      toast('下单成功，待支付（订单号 ' + res.data.outTradeNo + '）');
      refreshAll();
      return;
    }
    const pay = res.data.payment;
    try {
      await Taro.requestPayment({
        timeStamp: String(pay.timeStamp),
        nonceStr: String(pay.nonceStr),
        package: String(pay.package),
        signType: (pay.signType as any) || 'RSA',
        paySign: String(pay.paySign),
      });
      toast('支付成功，会员到账请刷新查看');
      refreshAll();
    } catch {
      toast('支付未完成，订单仍为待支付');
      refreshAll();
    }
  }

  async function cancelRenew() {
    const res = await callFn<MembershipStatus>('membership', { action: 'cancelAutoRenew' });
    if (res.ok) { toast('取消续费已生效，当前周期到期后降回普通'); refreshAll(); }
    else if (res.code === 'NO_MEMBERSHIP') toast('当前无会员记录，无需取消');
    else toast('取消失败：' + res.code);
  }

  async function earn(rule: string) {
    setBusy('earn-' + rule);
    const res = await callFn<{ delta: number; balance: number }>('points', { action: 'earn', rule, deviceFingerprint: deviceFingerprint() });
    setBusy('');
    if (res.ok) {
      toast('已领取 +' + res.data.delta + ' 积分');
      if (rule === 'signin') setSigninBurst((n) => n + 1);
      refreshAll();
    }
    else if (res.code === 'DAILY_LIMIT_REACHED') toast('今日领取次数已达上限');
    else if (res.code === 'ALREADY_CLAIMED') toast('该奖励已领取过');
    else if (res.code === 'DEVICE_MISMATCH') toast('设备与登录设备不一致，拒绝领取');
    else toast('领取失败：' + res.code);
  }

  async function watchVideo() {
    const adUnitId = config?.ads.rewardedVideo || '';
    if (!config || !config.ads.enabled || isPlaceholderAdUnit(adUnitId)) {
      toast('激励视频暂未开通（流量主 UV 未达 1000）');
      return;
    }
    const createAd = (Taro as any).createRewardedVideoAd;
    if (typeof createAd !== 'function') {
      toast('当前环境不支持激励视频');
      return;
    }
    try {
      const ad = createAd({ adUnitId });
      ad.onClose((r: { isEnded: boolean }) => {
        if (r && r.isEnded) earn('video');
        else toast('完整看完视频才能领取积分');
      });
      await ad.show();
    } catch {
      toast('激励视频拉起失败，请稍后重试');
    }
  }

  async function redeem(rule: string) {
    setBusy('redeem-' + rule);
    const res = await callFn<{ delta: number; balance: number }>('points', { action: 'spend', rule });
    setBusy('');
    if (res.ok) { toast('兑换成功'); refreshAll(); }
    else if (res.code === 'INSUFFICIENT_POINTS') toast('积分不足');
    else toast('兑换失败：' + res.code);
  }

  async function bindInvite() {
    const code = bindCode.trim().toUpperCase();
    if (!code) { toast('请先填写邀请码'); return; }
    const res = await callFn<{ inviterOpenid: string; inviteeBonus: number }>('invite', { action: 'bind', code });
    if (res.ok) { toast('绑定成功，被邀奖励 +50 积分'); refreshAll(); }
    else if (res.code === 'SELF_INVITE') toast('不能绑定自己的邀请码');
    else if (res.code === 'ALREADY_BOUND') toast('已绑定过邀请人，不可重复绑定');
    else if (res.code === 'SAME_DEVICE') toast('同一设备只计一次邀请');
    else if (res.code === 'INVITE_CODE_NOT_FOUND') toast('邀请码不存在');
    else toast('绑定失败：' + res.code);
  }

  async function settleInvite() {
    const res = await callFn<{ newlySuccess: number; successCount: number }>('invite', { action: 'settle' });
    if (res.ok) { toast('结算完成，新增成功邀请 ' + res.data.newlySuccess + ' 人'); refreshAll(); }
    else toast('结算失败：' + res.code);
  }

  function copyCode() {
    if (!invite?.inviteCode) return;
    Taro.setClipboardData({ data: invite.inviteCode });
    toast('邀请码已复制');
  }

  async function loadQr() {
    setQrNote('');
    setQrUrl('');
    const res = await callFn<{ fileID?: string; placeholder?: boolean; message?: string }>('invite', { action: 'qrcode' });
    if (!res.ok) { setQrNote('小程序码获取失败：' + res.code); return; }
    if (res.data.placeholder || !res.data.fileID) {
      setQrNote(res.data.message || '小程序码暂不可用（待 AppID / 环境配置就绪后重试），未返回真实 fileID。');
      return;
    }
    const url = await tempFileURL(res.data.fileID);
    if (url) setQrUrl(url);
    else setQrNote('小程序码已生成，但临时链接获取失败，请稍后重试。');
  }

  async function saveSettings() {
    const year = parseInt(birthYearStr, 10);
    const res = await loginFlow({
      nickname: nickname || undefined,
      gender: genderIdx,
      birthYear: Number.isNaN(year) ? undefined : year,
      isMinor: isMinorSwitch || undefined,
    });
    if (res.ok) { setUser(res.data.user); toast('资料已保存'); refreshAll(); }
    else toast('保存失败：' + res.code);
  }

  async function submitFeedback() {
    if (!fbContent.trim()) { toast('请先填写反馈内容'); return; }
    const res = await callFn<{ feedbackId: string }>('feedback', { action: 'create', content: fbContent.trim(), contact: fbContact.trim() });
    if (res.ok) { toast('反馈已提交'); setFbContent(''); setFbContact(''); refreshAll(); }
    else toast('提交失败：' + res.code);
  }

  async function chartAction(action: string, chartId: string) {
    const res = await callFn<{ chartId: string }>('charts', { action, chartId });
    if (res.ok) { toast(action === 'remove' ? '已删除' : '已设为默认盘'); refreshAll(); }
    else toast('操作失败：' + res.code);
  }

  async function removeChart(chartId: string) {
    // 删除确认已由长按按钮本身承担（按满进度才触发），不再弹二次确认框。
    chartAction('remove', chartId);
  }

  function loadSavedChart(c: SavedChart) {
    try {
      Taro.setStorageSync(STORAGE_INPUT, c.birthParams);
      Taro.setStorageSync(STORAGE_CHART, c.chartData);
      setLocalChart(c.chartData);
      toast('已载入该盘，可到命盘图页查看');
    } catch {
      toast('载入失败');
    }
  }

  function backBtn() {
    return <View className='btn-medley btn-medley-outline-light' style={{ marginBottom: '12px' }} onClick={() => setSection('main')}>返回我的</View>;
  }

  function unconfiguredNote() {
    if (configured) return null;
    return <Text className='muted'>云开发未配置：该功能需用户提供云开发环境 ID 后开通，当前不展示虚假数据。</Text>;
  }

  function needLoginNote() {
    if (!configured || user) return null;
    return <Text className='muted'>请先点上方“登录”按钮，登录后这里才会加载真实数据。</Text>;
  }

  const header = (
    <Card light>
      <View style={{ display: 'flex', alignItems: 'center' }} onClick={() => { if (!user) Taro.navigateTo({ url: '/pages/auth/index' }); }}>
        <View className='avatar-geo'>
          <Image className='avatar-mark' src={starMark} mode='aspectFit' />
        </View>
        <View style={{ marginLeft: '12px', flex: 1 }}>
          <Text className='mine-name'>{user?.nickname || '紫微星盘用户'}</Text>
          {membership ? (
            <Text className='muted'>会员：<Text className={membership.tier === 'free' ? 'mine-tier-free' : membership.tier === 'max' ? 'mine-tier-max' : 'mine-tier-pro'}>{membership.tier === 'free' ? '普通' : membership.tier.toUpperCase()}</Text>{membership.expiresAt ? '，到期 ' + formatDateTime(membership.expiresAt) : ''}{membership.autoRenew ? '（连续包月）' : ''}</Text>
          ) : (
            <Text className='muted'>{configured ? '登录后可查看会员与积分。' : '云开发未配置，账号功能暂不可用。'}</Text>
          )}
          {balance !== null ? <Text className='muted' style={{ display: 'block' }}>积分：<Text className='mine-points-num'>{balance}</Text>（永不过期）</Text> : null}
        </View>
      </View>
      {!user ? (
        <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={() => Taro.navigateTo({ url: '/pages/auth/index' })}>登录 / 注册</View>
      ) : null}
      <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => refreshAll()}>刷新</View>
      {notice ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{notice}</Text> : null}
    </Card>
  );

  if (section === 'member') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='会员中心'>
          {unconfiguredNote()}{needLoginNote()}
          {failedHas('会员') ? <Text className='muted'>会员状态加载失败，请点“我的”页刷新重试。</Text> : null}
          {membership ? (
            <View>
              <Text className='muted'>当前有效档位：{membership.tier === 'free' ? '普通' : membership.tier.toUpperCase()}（原始档位 {membership.rawTier}）</Text>
              <Text className='muted' style={{ display: 'block' }}>到期：{formatDateTime(membership.expiresAt)}；连续包月：{membership.autoRenew ? '已开启' : '未开启'}</Text>
              {membership.autoRenew ? <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={cancelRenew}>取消连续包月（到期降回普通）</View> : null}
            </View>
          ) : null}
        </Card>
        <Card light title='购买会员（价目来自云端配置）'>
          {unconfiguredNote()}{needLoginNote()}
          {failedHas('配置') ? <Text className='muted'>价目加载失败，不展示价格，请刷新重试。</Text> : null}
          {config ? PLANS.map((plan) => {
            const p = config.pricing.plans[plan];
            if (!p) return null;
            return (
              <View key={plan} className='input-row'>
                <Text className='input-label mine-row-label'>{PLAN_NAMES[plan]}（{p.days} 天）</Text>
                <View style={{ display: 'flex', alignItems: 'center' }}>
                  <Text className='input-value mine-price' style={{ marginRight: '10px' }}>{formatYuan(p.fen)}</Text>
                  <View className='btn-pill btn-pill-black' onClick={() => buy(plan)}>{busy === 'buy-' + plan ? '处理中…' : '购买'}</View>
                </View>
              </View>
            );
          }) : null}
          {config?.pricing.cancelNote ? <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>{config.pricing.cancelNote}</Text> : null}
        </Card>
        <Card light title='积分兑换 Pro'>
          <View className='btn-medley btn-medley-outline-light' style={{ marginBottom: '10px' }} onClick={() => redeem('pro7d')}>{busy === 'redeem-pro7d' ? '处理中…' : '300 积分兑换 7 天 Pro'}</View>
          <View className='btn-medley btn-medley-outline-light' onClick={() => redeem('pro30d')}>{busy === 'redeem-pro30d' ? '处理中…' : '1500 积分兑换 30 天 Pro'}</View>
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'points') {
    const videoOpen = !!config && config.ads.enabled && !isPlaceholderAdUnit(config.ads.rewardedVideo);
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='积分中心'>
          {unconfiguredNote()}{needLoginNote()}
          {failedHas('积分') ? <Text className='muted'>积分加载失败，请刷新重试。</Text> : null}
          {balance !== null ? <Text className='mine-balance'>当前积分：{balance}</Text> : null}
          <Text className='muted' style={{ display: 'block', marginTop: '6px' }}>积分永不过期。视频与分享领取由客户端动作触发、服务端按日限校验。</Text>
          <ParticleBurst burstKey={signinBurst}>
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={() => earn('signin')}>{busy === 'earn-signin' ? '处理中…' : '每日签到 +10'}</View>
          </ParticleBurst>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={watchVideo}>{videoOpen ? '看激励视频 +20（每日上限 5 次）' : '激励视频暂未开通（流量主 UV 未达 1000）'}</View>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => earn('share')}>{busy === 'earn-share' ? '处理中…' : '分享海报 +5（每日 1 次）'}</View>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={() => earn('profile')}>{busy === 'earn-profile' ? '处理中…' : (user?.profileBonusClaimed ? '完善资料 +30（已领取）' : '完善资料 +30（一次，需先在设置填昵称）')}</View>
        </Card>
        <Card light title='积分账本（最近 50 条）'>
          {ledger.length === 0 ? <EmptyState title='暂无积分记录' hint='每日签到 +10，完整看完激励视频 +20，邀请好友 +100。' /> : ledger.map((e, i) => (
            <View key={i} className='input-row'>
              <Text className='input-label mine-row-label'>{RULE_LABELS[e.rule] || e.rule}</Text>
              <Text className='input-value'><Text className={e.delta > 0 ? 'mine-delta-pos' : 'mine-delta-neg'}>{e.delta > 0 ? '+' + e.delta : e.delta}</Text><Text className='muted'> · {formatDateTime(e.createdAt)}</Text></Text>
            </View>
          ))}
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'invite') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='邀请中心'>
          {unconfiguredNote()}{needLoginNote()}
          {failedHas('邀请') ? <Text className='muted'>邀请数据加载失败，请刷新重试。</Text> : null}
          {invite ? (
            <View>
              <View className='input-row'>
                <Text className='input-label mine-row-label'>我的邀请码</Text>
                <Text className='input-value'>{invite.inviteCode || '—'}</Text>
              </View>
              <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={copyCode}>复制邀请码</View>
              <Text className='muted' style={{ display: 'block', marginTop: '10px' }}>
                成功邀请：{invite.successCount} 人；下一阶梯：{invite.nextTier ? `邀 ${invite.nextTier.count} 人 → ${invite.nextTier.days} 天 ${invite.nextTier.tier.toUpperCase()}` : '全部阶梯已达成'}
                ；已发放阶梯：{invite.grantedTiers.length ? invite.grantedTiers.join('、') : '无'}
              </Text>
              <Text className='muted' style={{ display: 'block', marginTop: '6px' }}>阶梯：邀 3 人 → 7 天 Pro；邀 10 人 → 30 天 Pro；邀 30 人 → Max 月卡。被邀人完成一次真实排盘才算成功；同一微信号、同一设备只计一次。</Text>
            </View>
          ) : null}
        </Card>
        <Card light title='绑定邀请码（被邀人注册 +50 积分）'>
          <View className='input-row'>
            <Text className='input-label'>邀请码</Text>
            <Input className='field-input' placeholder='填写邀请人的码' value={bindCode} onInput={(e) => setBindCode(e.detail.value)} />
          </View>
          <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={bindInvite}>绑定</View>
          <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '10px' }} onClick={settleInvite}>结算我的邀请（核查被邀人是否已排盘）</View>
          {user?.invitedBy ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>已绑定邀请人，不可重复绑定。</Text> : null}
        </Card>
        <Card light title='邀请海报小程序码'>
          <View className='btn-medley btn-medley-outline-light' onClick={loadQr}>获取小程序码</View>
          {qrUrl ? <Image src={qrUrl} style={{ width: '200px', height: '200px', marginTop: '12px' }} /> : null}
          {qrNote ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{qrNote}</Text> : null}
          <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>完整分享海报（含邀请二维码）在三期随海报功能提供；此处先提供小程序码原图。</Text>
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'orders') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='我的订单'>
          {unconfiguredNote()}{needLoginNote()}
          {failedHas('订单') ? <Text className='muted'>订单加载失败，请刷新重试。</Text> : null}
          {orders.length === 0 ? <EmptyState title='暂无订单' hint='在会员中心购买后，订单会出现在这里。' /> : orders.map((o) => (
            <View key={o._id} className='input-row'>
              <View>
                <Text className='mine-row-label'>{PLAN_NAMES[o.plan] || o.plan} · {formatYuan(o.amountFen)}</Text>
                <Text className='muted' style={{ display: 'block' }}>订单号 {o.outTradeNo} · {formatDateTime(o.createdAt)}</Text>
              </View>
              <Text className={o.status === 'paid' ? 'input-value mine-status-paid' : o.status === 'pending' ? 'input-value mine-status-pending' : 'input-value'}>{ORDER_STATUS_NAMES[o.status] || o.status}</Text>
            </View>
          ))}
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'settings') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='设置'>
          {unconfiguredNote()}{needLoginNote()}
          <View className='input-row'>
            <Text className='input-label'>昵称</Text>
            <Input className='field-input' placeholder='填写昵称' value={nickname} onInput={(e) => setNickname(e.detail.value)} />
          </View>
          <View className='input-row input-row-col'>
            <Text className='input-label'>性别</Text>
            <SegmentedControl options={GENDERS} value={genderIdx} onChange={setGenderIdx} tone='light' />
          </View>
          <View className='input-row'>
            <Text className='input-label'>出生年份</Text>
            <Input className='field-input' type='number' placeholder='例如 1998（用于未成年人门禁）' value={birthYearStr} onInput={(e) => setBirthYearStr(e.detail.value)} />
          </View>
          <View className='input-row'>
            <Text className='input-label'>我是未成年人</Text>
            <Toggle checked={isMinorSwitch} onChange={setIsMinorSwitch} />
          </View>
          <View className='input-row'>
            <Text className='input-label'>深色模式（默认亮色）</Text>
            <Toggle checked={theme === 'dark'} onChange={(v) => applyTheme(v ? 'dark' : 'light')} />
          </View>
          {user?.minor ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>当前账号已标记为未成年人：AI 解读、付费会员、积分兑换付费内容均不可用。清除标记需填写成年出生年份后保存。</Text> : null}
          <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={saveSettings}>保存资料</View>
          <Text className='muted' style={{ display: 'block', marginTop: '10px' }}>设备指纹（防刷用，本机安装标识，非真实设备号）：{deviceFingerprint()}</Text>
          <Text className='muted' style={{ display: 'block', marginTop: '6px' }}>取消连续包月请到会员中心操作；命盘管理请到档案管理；出生年份可在下方填写，用于未成年人门禁换算（未满 18 岁不可使用付费解读与付费会员）。</Text>
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'feedback') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='联系客服'>
          {unconfiguredNote()}{needLoginNote()}
          <View className='input-row'>
            <Text className='input-label'>联系方式（可选）</Text>
            <Input className='field-input' placeholder='邮箱或微信号' value={fbContact} onInput={(e) => setFbContact(e.detail.value)} />
          </View>
          <Textarea className='field-textarea' placeholder='请描述问题或建议（1–1000 字）' value={fbContent} onInput={(e) => setFbContent(e.detail.value)} />
          <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={submitFeedback}>提交反馈</View>
          <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>反馈由运营在云端处理；未回复的项状态保持“待处理”，不伪造回复。</Text>
        </Card>
        <Card light title='我的反馈'>
          {feedbacks.length === 0 ? <EmptyState title='暂无反馈记录' hint='在上方提交反馈后，处理状态会出现在这里。' /> : feedbacks.map((f, i) => (
            <View key={i} className='input-row'>
              <View style={{ flex: 1 }}>
                <Text className='mine-row-label'>{f.content}</Text>
                <Text className='muted' style={{ display: 'block' }}>{f.status === 'open' ? '待处理' : f.status} · {formatDateTime(f.createdAt)}</Text>
              </View>
            </View>
          ))}
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'charts') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='档案管理（多盘管理）'>
          {unconfiguredNote()}{needLoginNote()}
          {failedHas('命盘') ? <Text className='muted'>档案管理加载失败，请刷新重试。</Text> : null}
          {savedCharts.length === 0 ? <EmptyState title='暂无保存的命盘' hint='请先排盘，再到命盘图页点“保存到我的命盘”。' actionLabel='去排盘' onAction={() => Taro.navigateTo({ url: '/pages/birth/index' })} /> : savedCharts.map((c) => (
            <View key={c._id} style={{ marginBottom: '12px' }}>
              <View className='input-row'>
                <Text className='input-label mine-row-label'>{c.name}{c.isDefault ? '（默认盘）' : ''}</Text>
                <Text className='input-value'>{formatDateTime(c.createdAt)}</Text>
              </View>
              <View style={{ display: 'flex', marginTop: '8px' }}>
                <View className='btn-pill btn-pill-black' style={{ marginRight: '8px' }} onClick={() => loadSavedChart(c)}>载入此盘</View>
                {!c.isDefault ? <View className='btn-pill btn-pill-black' style={{ marginRight: '8px' }} onClick={() => chartAction('setDefault', c._id)}>设为默认</View> : null}
                <LongPressConfirm hint='长按删除' onConfirm={() => removeChart(c._id)}>删除</LongPressConfirm>
              </View>
            </View>
          ))}
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'compare') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='合盘对照（两盘主星对照）'>
          {unconfiguredNote()}{needLoginNote()}
          <CompareView charts={savedCharts} aId={compareA} bId={compareB} onA={setCompareA} onB={setCompareB} labelClass='input-label mine-row-label' />
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'reports') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='报告记录'>
          <Text className='muted'>这里只记你自己打开过的解读（本地记录，按日期去重），不编造浏览数据。</Text>
          {reports.length === 0 ? <EmptyState title='暂无报告记录' hint='到解读页打开一次命盘解读，这里就会记下一条。' actionLabel='去解读页' onAction={() => Taro.switchTab({ url: '/pages/interpret/index' })} /> : reports.map((r, i) => (
            <View key={i} className='input-row'>
              <Text className='input-label mine-row-label'>{r.title}</Text>
              <Text className='input-value'>{r.date}</Text>
            </View>
          ))}
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'poster') {
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <PosterCard chart={localChart} inviteCode={invite?.inviteCode || ''} />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  if (section === 'legal') {
    const tab = LEGAL_TABS.find((t) => t.key === legalTab) || LEGAL_TABS[0];
    return (
      <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
        {backBtn()}
        <Card light title='关于 / 隐私 / 条款'>
          <View style={{ display: 'flex', flexWrap: 'wrap' }}>
            {LEGAL_TABS.map((t) => (
              <Text key={t.key} className={t.key === legalTab ? 'chip chip-accent' : 'chip'} onClick={() => setLegalTab(t.key)}>{t.label}</Text>
            ))}
          </View>
          <Text className='legal-body'>{tab.text}</Text>
        </Card>
        <Disclaimer />
        {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
      </View>
    );
  }

  // Spaced divider-free service cards (s6 pattern): color dot + bold title
  // + one-line sub + violet arrow. No divider lines, big whitespace.
  const ROWS: Array<{ label: string; sub: string; icon: IconName; section: Section }> = [
    { label: '会员中心', sub: 'Pro / Max 订阅与连续包月', icon: 'crown', section: 'member' },
    { label: '积分中心', sub: '签到、视频、邀请赚积分', icon: 'coins', section: 'points' },
    { label: '邀请中心', sub: '邀请码与阶梯奖励', icon: 'users', section: 'invite' },
    { label: '档案管理', sub: '已保存的命盘', icon: 'history', section: 'charts' },
    { label: '合盘对照', sub: '双方六宫主星对照', icon: 'layers', section: 'compare' },
    { label: '报告记录', sub: '自己打开过的解读', icon: 'clipboard-list', section: 'reports' },
    { label: '分享海报', sub: '命盘海报与邀请码', icon: 'share-2', section: 'poster' },
    { label: '我的订单', sub: '购买与支付记录', icon: 'clipboard-list', section: 'orders' },
    { label: '设置', sub: '资料、未成年人标记', icon: 'settings', section: 'settings' },
    { label: '联系客服', sub: '告诉我们你的建议', icon: 'message-square', section: 'feedback' },
    { label: '关于（含数据来源）', sub: '协议与数据来源', icon: 'info', section: 'legal' },
  ];
  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      {header}
      <Card light title='星币'>
        {unconfiguredNote()}
        {balance !== null ? <Text className='mine-balance'>当前星币：{balance}</Text> : null}
        <Text className='muted' style={{ display: 'block', marginTop: '6px' }}>星币与积分同一余额；充值需微信支付商户配置，当前未开通，不展示虚假购买入口。</Text>
        <View className='btn-row' style={{ marginTop: '12px' }}>
          <View className='btn-medley btn-medley-outline-light' onClick={() => setSection('points')}>签到领星币</View>
          <View className='btn-medley btn-medley-outline-light' onClick={() => setSection('points')}>分享领星币</View>
          <View className='btn-medley btn-medley-outline-light' onClick={() => toast('星币充值需微信支付商户配置，待用户提供后开通')}>充值</View>
        </View>
      </Card>
      <Text className='svc-heading'>我的服务</Text>
      <View className='svc-grid'>
        {ROWS.map((r) => (
          <View key={r.section} className='svc-card' onClick={() => setSection(r.section)}>
            <IconBadge name={r.icon} dark={theme === 'dark'} />
            <View className='svc-body'>
              <Text className='svc-title'>{r.label}</Text>
              <Text className='svc-sub'>{r.sub}</Text>
            </View>
            <View className='svc-arrow-img'><Icon name='chevron-right' tone={theme === 'dark' ? 'sky' : 'blue'} size='38px' /></View>
          </View>
        ))}
        <View className='svc-card' onClick={() => Taro.navigateTo({ url: '/pages/demo/index' })}>
          <IconBadge name='layout-grid' dark={theme === 'dark'} />
          <View className='svc-body'>
            <Text className='svc-title'>组件演示</Text>
            <Text className='svc-sub'>6 个交互组件演示</Text>
          </View>
          <View className='svc-arrow-img'><Icon name='chevron-right' tone={theme === 'dark' ? 'sky' : 'blue'} size='38px' /></View>
        </View>
      </View>
      <Text className='caption'>
        数据来源：排盘引擎移植自 Renhuai123/ziwei-doushu（MIT，见引擎目录 LICENSE 与 SOURCE.md）。
        内容源自传统紫微斗数文化，仅供学习与娱乐参考，不构成人生决策建议。
      </Text>
      {/* H5 fallback mount (weapp injects the custom tabBar natively). */}
      {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
    </View>
  );
}
