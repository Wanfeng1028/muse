import {useEffect, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';
import {theme} from '../theme';

let loading: Promise<void> | null = null;

const loadAll = () => {
  if (!loading) {
    loading = Promise.all(
      theme.fonts.map(async (f) => {
        try {
          const face = new FontFace(f.family, `url(${staticFile(f.file)})`, {weight: f.weight ?? '400'});
          await face.load();
          // 部分版本的 TS DOM 类型没有 FontFaceSet.add，运行时是存在的
          (document.fonts as unknown as {add: (font: FontFace) => void}).add(face);
        } catch (err) {
          console.warn(`[code-film] 字体加载失败：public/${f.file}，将回退到系统字体`, err);
        }
      }),
    ).then(() => undefined);
  }
  return loading;
};

/** 在渲染任何一帧之前，等 theme.fonts 里的字体全部加载完。 */
export const useFonts = () => {
  const [handle] = useState(() => delayRender('加载字体'));
  useEffect(() => {
    loadAll().then(() => continueRender(handle));
  }, [handle]);
};
