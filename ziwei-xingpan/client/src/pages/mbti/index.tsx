import { useState } from 'react';
import { View, Text } from '@tarojs/components';
import { MBTI_QUESTIONS, MBTI_DESCS, mbtiType } from '../../lib/tools';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// MBTI 趣味测试：16 题全部本站自编（每维 4 题），平局取 A 侧
// （E/S/T/J），规则写死、可复现。结果描述本站新写；本测试非官方
// MBTI，仅供娱乐参考。
export default function Mbti() {
  const [theme] = useTheme();
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const done = answers.length === MBTI_QUESTIONS.length;
  const type = done ? mbtiType(answers) : '';

  function answer(v: number) {
    setAnswers((a) => [...a, v]);
    setStep((s) => s + 1);
  }

  function restart() {
    setAnswers([]);
    setStep(0);
  }

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='MBTI 趣味测试'>
        {!done ? (
          <View>
            <Text className='muted'>第 {step + 1} / {MBTI_QUESTIONS.length} 题 · 本测试为本站自编问卷，非官方 MBTI。</Text>
            <Text className='tool-mid' style={{ display: 'block', marginTop: '12px' }}>{MBTI_QUESTIONS[step].q}</Text>
            <View className='qa-option' onClick={() => answer(0)}>
              <Text className='qa-option-text'>A · {MBTI_QUESTIONS[step].a}</Text>
            </View>
            <View className='qa-option' onClick={() => answer(1)}>
              <Text className='qa-option-text'>B · {MBTI_QUESTIONS[step].b}</Text>
            </View>
          </View>
        ) : (
          <View>
            <Text className='tool-big' style={{ display: 'block' }}>{type}</Text>
            <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>{MBTI_DESCS[type] || ''}</Text>
            <Text className='caption' style={{ display: 'block', marginTop: '8px' }}>计分：每维 4 题，选 B 过半取 B 侧，否则取 A 侧；平局取 A 侧。本测试非官方 MBTI，仅供娱乐参考。</Text>
            <View className='btn-medley btn-medley-outline-light' style={{ marginTop: '12px' }} onClick={restart}>重新测试</View>
          </View>
        )}
      </Card>
      <Disclaimer />
    </View>
  );
}
