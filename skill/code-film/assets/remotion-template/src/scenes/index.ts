import type React from 'react';
import {AsciiSun} from './AsciiSun';
import {CameraTour} from './CameraTour';
import {Statement} from './Statement';
import {TitleCard} from './TitleCard';

/** storyboard.json 里 shot.scene 的名字对应这里的组件。新增场景后在这里登记。 */
export const scenes: Record<string, React.ComponentType<any>> = {
  Statement,
  TitleCard,
  AsciiSun,
  CameraTour,
};
