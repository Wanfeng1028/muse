import { useState } from 'react';
import { View, Text } from '@tarojs/components';
import { throwCoins, hexagramOf, type YaoLine } from '../../lib/tools';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 六爻卜卦：三枚铜钱掷六次成卦，卦名按文王卦序与上下卦查表
// （表见 lib/tools-data.ts，经 lib/tools.ts 转出，组合唯一性已自检）。本页只展示所起之爻、
// 本卦与变卦，不附传统解卦文本，不作吉凶断言。
function YaoRow({ line }: { line: YaoLine }) {
  return (
    <View className='yao-line'>
      <Text className='yao-label'>{line.label}</Text>
      {line.yang ? (
        <View className='yao-bar' />
      ) : (
        <View style={{ display: 'flex', flex: 1, gap: '15.38px' }}>
          <View className='yao-bar-half' />
          <View className='yao-bar-half' />
        </View>
      )}
      {line.moving ? <Text className='yao-moving'>动</Text> : null}
    </View>
  );
}

export default function Liuyao() {
  const [theme] = useTheme();
  const [lines, setLines] = useState<YaoLine[] | null>(null);
  const result = lines ? hexagramOf(lines) : null;

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='六爻卜卦'>
        <Text className='muted'>三枚铜钱掷六次，自下而上成卦：三正为老阳（动）、两正为少阳、一正为少阴、零正为老阴（动）。起卦随机，仅供娱乐。</Text>
        <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={() => setLines(throwCoins())}>起卦</View>
        {lines && result ? (
          <View>
            <View className='yao-lines'>
              {lines.map((l, i) => (<YaoRow key={i} line={l} />))}
            </View>
            <Text className='tool-mid' style={{ display: 'block' }}>
              本卦：{result.base.name}（上{result.base.upper}下{result.base.lower}）
            </Text>
            {result.movingNames.length ? (
              <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>
                动爻：{result.movingNames.join('、')}；变卦：{result.changed?.name}（上{result.changed?.upper}下{result.changed?.lower}）
              </Text>
            ) : (
              <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>无动爻，无变卦。</Text>
            )}
          </View>
        ) : null}
      </Card>
      <Disclaimer />
    </View>
  );
}
