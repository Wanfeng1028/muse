import { View, Text } from '@tarojs/components';
import { PERSONAS } from '../../lib/tools';
import { goInterpret } from '../../lib/nav';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { Icon } from '../../components/icons';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// AI 占星师：4 位本站原创人格（名、介绍、擅长均为新写），头像为
// Lucide 字形渐变圆，不用参照对象的人格名与头像，不展示任何聊过
// 人数（没有该数据就不编）。私聊打开解盘对话：本地 13 维解读；
// AI 生成需云开发配置（见解读页诚实态）。
export default function Astrologers() {
  const [theme] = useTheme();
  const dark = theme === 'dark';

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='AI 占星师'>
        <Text className='muted'>四位原创人格，分别擅长不同的方向；点私聊打开解盘对话。</Text>
      </Card>
      {PERSONAS.map((p, i) => (
        <View key={p.id} className='persona-card'>
          <View className={'persona-avatar persona-avatar-' + (i + 1)}>
            <Icon name={p.glyph} tone='white' size='56px' />
          </View>
          <View className='persona-body'>
            <Text className='persona-name'>{p.name}</Text>
            <Text className='persona-intro'>{p.intro}</Text>
            <View style={{ display: 'flex', flexWrap: 'wrap', marginTop: '8px' }}>
              {p.tags.map((t) => (
                <Text key={t} className='chip chip-accent' style={{ marginRight: '8px', marginBottom: '8px' }}>{t}</Text>
              ))}
            </View>
            <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '8px' }} onClick={() => goInterpret()}>私聊</View>
          </View>
        </View>
      ))}
      <Text className='caption'>人格头像为 Lucide 字形渐变圆，非真人照片；不展示聊过人数等无来源数据。</Text>
      <Disclaimer />
    </View>
  );
}
