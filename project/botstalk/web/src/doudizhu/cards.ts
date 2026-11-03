// 牌数字映射：3..10 原样，11=J 12=Q 13=K 14=A 15=2 16=小王 17=大王。
// 花色仅用于视觉区分，按 n%4 取 ♠♥♣♦，16/17 为大小王无花色。

export function rankLabel(n: number): string {
  if (n >= 3 && n <= 10) return String(n);
  switch (n) {
    case 11:
      return 'J';
    case 12:
      return 'Q';
    case 13:
      return 'K';
    case 14:
      return 'A';
    case 15:
      return '2';
    case 16:
      return '小王';
    case 17:
      return '大王';
    default:
      return '?';
  }
}

const SUITS = ['\u2660', '\u2665', '\u2663', '\u2666'];

export function suitMark(n: number): { mark: string; red: boolean } {
  if (n === 16 || n === 17) return { mark: '', red: false };
  if (n >= 3 && n <= 15) {
    const mark = SUITS[n % 4];
    return { mark, red: mark === '\u2665' || mark === '\u2666' };
  }
  return { mark: '', red: false };
}

export function sortHand(cards: number[]): number[] {
  return [...cards].sort((a, b) => a - b);
}