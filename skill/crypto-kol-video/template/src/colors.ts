import {C} from './ui';
/** named colors usable from video.json ("red", "green", "amber", "blue", "purple", "sub", "text") or any #hex */
export const col = (c?: string) => {
  if (!c) return C.text;
  const m: Record<string, string> = {red: C.red, green: C.green, amber: C.amber, blue: C.blue, purple: '#A78BFA', sub: C.sub, text: C.text};
  return m[c] ?? c;
};
export type Part = {t: string; c?: string; size?: number};
