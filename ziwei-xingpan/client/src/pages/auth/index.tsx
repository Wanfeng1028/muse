import { useState } from 'react';
import { View, Text, Input, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { Card, SegmentedControl } from '../../components/ui';
import { Icon } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import { cloudConfigured } from '../../lib/cloud';
import starMark from '../../assets/logo/star-mark.png';
import './index.scss';

// Login / register (user's standing login spec, 2026-10-04 + 2026-11-01):
// international-app style, NO phone/SMS; email + password; login and
// register share one page with a segmented switch; forgot-password
// entry; Google / Apple third-party buttons; every control a 999px
// capsule; primary button = Gemini blue gradient; Lucide icons;
// light by default (theme-aware like every other page).
// Honesty rule: no backend for email accounts exists yet (envId and 13
// user items pending), so submit NEVER fakes a success — unconfigured
// shows the unconfigured toast, configured shows that the email
// account function is not open yet. Mode lands from ?mode=login |
// register | forgot so screenshots can capture each state directly.
type Mode = 'login' | 'register' | 'forgot';

function initialMode(): Mode {
  try {
    // Taro's router params are loosely typed (same any-as-API pattern as
    // currentPath in custom-tab-bar); guarded by the value check below.
    const m = (Taro.getCurrentInstance() as any)?.router?.params?.mode;
    if (m === 'register' || m === 'forgot') return m;
  } catch { /* default login */ }
  return 'login';
}

export default function Auth() {
  const [theme] = useTheme();
  const [mode, setMode] = useState<Mode>(initialMode());
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [nickname, setNickname] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [notice, setNotice] = useState('');

  const configured = cloudConfigured();
  const dark = theme === 'dark';

  function toast(title: string) {
    Taro.showToast({ title, icon: 'none' });
  }

  function submit() {
    if (!email || email.indexOf('@') < 1) {
      toast('请填写正确的邮箱地址');
      return;
    }
    if (password.length < 6) {
      toast('密码至少 6 位');
      return;
    }
    if (mode === 'register' && password !== confirm) {
      toast('两次输入的密码不一致');
      return;
    }
    if (!configured) {
      setNotice('云开发未配置：登录、注册功能需用户提供云开发环境 ID 后开通，当前不会创建账号或登录。');
      toast('云开发未配置，登录功能暂不可用');
      return;
    }
    setNotice('邮箱账号体系尚未开通云函数，当前不会创建账号或登录；微信快捷登录随云开发开通后可用。');
  }

  function thirdParty(name: string) {
    if (!configured) {
      toast('云开发未配置，第三方登录暂不可用');
      return;
    }
    setNotice(`${name} 登录尚未开通云函数与厂商 OAuth 配置，当前不会登录任何账号。`);
  }

  function sendReset() {
    if (!email || email.indexOf('@') < 1) {
      toast('请先填写邮箱地址');
      return;
    }
    if (!configured) {
      setNotice('云开发未配置，密码重置邮件暂不可发送。');
      toast('云开发未配置，重置邮件暂不可发送');
      return;
    }
    setNotice('密码重置尚未开通云函数，当前不会发送重置邮件；请返回登录或联系客服。');
  }

  return (
    <View className={'page theme-' + theme}>
      <View className='auth-back' onClick={() => Taro.navigateBack()}>
        <Icon name='chevron-left' tone={dark ? 'sky' : 'blue'} size='40px' />
        <Text className='auth-back-text'>返回</Text>
      </View>
      <View className='auth-brand'>
        <Image className='auth-brand-mark' src={starMark} mode='aspectFit' />
        <Text className='brand-name'>紫微星盘</Text>
      </View>
      <Text className='auth-title'>{mode === 'forgot' ? '找回密码' : mode === 'register' ? '注册账号' : '欢迎回来'}</Text>
      <Text className='auth-sub'>
        {mode === 'forgot' ? '输入注册邮箱，我们会把重置链接发到你的邮箱。' : '邮箱登录，无需手机号与验证码。'}
      </Text>

      {mode === 'forgot' ? (
        <Card>
          <View className='auth-row'>
            <Icon name='mail' tone={dark ? 'sky' : 'blue'} size='40px' />
            <Input className='auth-input' placeholder='邮箱地址' value={email} onInput={(e) => setEmail(e.detail.value)} />
          </View>
          <View className='auth-submit' hoverClass='btn-press' onClick={sendReset}>
            <Text className='auth-submit-text'>发送重置链接</Text>
          </View>
          <View className='auth-switch' onClick={() => setMode('login')}>
            <Text className='auth-link'>返回登录</Text>
          </View>
        </Card>
      ) : (
        <View>
          <View style={{ marginBottom: '23.08px' }}>
            <SegmentedControl
              options={['登录', '注册']}
              value={mode === 'register' ? 1 : 0}
              onChange={(i) => { setMode(i === 1 ? 'register' : 'login'); setNotice(''); }}
              tone={dark ? 'dark' : 'light'}
            />
          </View>
          <Card>
            <View className='auth-row'>
              <Icon name='mail' tone={dark ? 'sky' : 'blue'} size='40px' />
              <Input className='auth-input' placeholder='邮箱地址' value={email} onInput={(e) => setEmail(e.detail.value)} />
            </View>
            <View className='auth-row'>
              <Icon name='lock' tone={dark ? 'sky' : 'blue'} size='40px' />
              <Input className='auth-input' placeholder='密码（至少 6 位）' password={!showPwd} value={password} onInput={(e) => setPassword(e.detail.value)} />
              <View onClick={() => setShowPwd(!showPwd)}>
                <Icon name={showPwd ? 'eye-off' : 'eye'} tone='gray' size='40px' />
              </View>
            </View>
            {mode === 'register' ? (
              <View>
                <View className='auth-row'>
                  <Icon name='lock' tone={dark ? 'sky' : 'blue'} size='40px' />
                  <Input className='auth-input' placeholder='确认密码' password={!showPwd} value={confirm} onInput={(e) => setConfirm(e.detail.value)} />
                </View>
                <View className='auth-row auth-row-last'>
                  <Icon name='user' tone={dark ? 'sky' : 'blue'} size='40px' />
                  <Input className='auth-input' placeholder='昵称（可选）' value={nickname} onInput={(e) => setNickname(e.detail.value)} />
                </View>
              </View>
            ) : null}
            {mode === 'login' ? (
              <View className='auth-forgot' onClick={() => setMode('forgot')}>
                <Text className='auth-link'>忘记密码？</Text>
              </View>
            ) : null}
            <View className='auth-submit' hoverClass='btn-press' onClick={submit}>
              <Text className='auth-submit-text'>{mode === 'register' ? '注册' : '登录'}</Text>
            </View>
            <View className='auth-divider'><Text className='auth-divider-text'>或</Text></View>
            <View className='auth-third' onClick={() => thirdParty('Google')}>
              <Icon name='chrome' tone={dark ? 'sky' : 'blue'} size='40px' />
              <Text className='auth-third-text'>使用 Google 继续</Text>
            </View>
            <View className='auth-third' onClick={() => thirdParty('Apple')}>
              <Icon name='apple' tone={dark ? 'sky' : 'blue'} size='40px' />
              <Text className='auth-third-text'>使用 Apple 继续</Text>
            </View>
            <Text className='auth-note'>
              登录即代表同意《用户协议》与《隐私政策》。Lucide 无官方 Google /
              Apple 品牌标，第三方按钮用 Lucide chrome / apple 字形 + 文字表示，
              不仿造厂商原标。
            </Text>
          </Card>
        </View>
      )}
      {notice ? <Text className='muted' style={{ display: 'block', marginTop: '23.08px' }}>{notice}</Text> : null}
      <Text className='caption' style={{ display: 'block', marginTop: '23.08px' }}>
        账号体系说明：当前版本账号功能依赖云开发（环境 ID 待用户提供）；未开通前本页只做表单与提示，不产生任何登录态。
      </Text>
    </View>
  );
}
