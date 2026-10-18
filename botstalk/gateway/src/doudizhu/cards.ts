// 牌面数字映射：3=3, 4=4, ..., 13=K, 14=A, 15=2, 16=小王, 17=大王

export type ComboType =
  | "single"
  | "pair"
  | "trio"
  | "trio_single"
  | "trio_pair"
  | "straight"
  | "pair_straight"
  | "plane"
  | "plane_wings"
  | "four_with_two"
  | "bomb"
  | "rocket"
  | "invalid";

export interface Combo {
  type: ComboType;
  cards: number[];
  mainRank: number;
  length: number;
}

export function sortCards(cards: number[]): number[] {
  // 返回升序新数组，不修改入参
  return cards.slice().sort((x, y) => x - y);
}

function countRanks(cards: number[]): Map<number, number> {
  // 统计每个点数出现次数
  const map = new Map<number, number>();
  for (const c of cards) {
    map.set(c, (map.get(c) ?? 0) + 1);
  }
  return map;
}

function invalidCombo(sorted: number[]): Combo {
  // 构造非法牌型结果
  return { type: "invalid", cards: sorted, mainRank: 0, length: sorted.length };
}

function isConsecutive(ranks: number[]): boolean {
  // 判断点数数组是否严格连续递增
  for (let i = 1; i < ranks.length; i++) {
    if (ranks[i] !== ranks[i - 1] + 1) return false;
  }
  return true;
}

function tryStraight(sorted: number[], counts: Map<number, number>): Combo | null {
  // 顺子：>=5 张，连续，每张 <=14，无重复
  // 口径决策（2026-10-18）：A 不可作为 1 回绕，A2345 / A23456 均非法。
  // 依据主流口径（腾讯欢乐斗地主等）：顺子最小 3、最大 A，A 为端点不回绕。
  const n = sorted.length;
  if (n < 5) return null;
  if (counts.size !== n) return null;
  for (const r of sorted) {
    if (r > 14) return null;
  }
  if (!isConsecutive(sorted)) return null;
  return { type: "straight", cards: sorted, mainRank: sorted[n - 1], length: n };
}

function tryPairStraight(sorted: number[], counts: Map<number, number>): Combo | null {
  // 连对：>=6 且偶数，>=3 个连续对子，每对点数 <=14
  const n = sorted.length;
  if (n < 6 || n % 2 !== 0) return null;
  const ranks: number[] = [];
  for (const [r, c] of counts) {
    if (c !== 2) return null;
    if (r > 14) return null;
    ranks.push(r);
  }
  if (ranks.length < 3) return null;
  ranks.sort((x, y) => x - y);
  if (!isConsecutive(ranks)) return null;
  return { type: "pair_straight", cards: sorted, mainRank: ranks[ranks.length - 1], length: n };
}

function tryPlane(sorted: number[], counts: Map<number, number>): Combo | null {
  // 飞机（不带翅膀）：>=6 且 3 的倍数，>=2 个连续三张，点数 <=14
  const n = sorted.length;
  if (n < 6 || n % 3 !== 0) return null;
  const ranks: number[] = [];
  for (const [r, c] of counts) {
    if (c !== 3) return null;
    if (r > 14) return null;
    ranks.push(r);
  }
  if (ranks.length < 2) return null;
  ranks.sort((x, y) => x - y);
  if (!isConsecutive(ranks)) return null;
  return { type: "plane", cards: sorted, mainRank: ranks[ranks.length - 1], length: n };
}

function tryPlaneWings(sorted: number[], counts: Map<number, number>): Combo | null {
  // 飞机带翅膀：n 个连续三张(n>=2,<=14)，带 n 个单张(总 4n) 或 n 个对子(总 5n)
  const n = sorted.length;
  const trioRanks: number[] = [];
  for (const [r, c] of counts) {
    if (c >= 3 && r <= 14) {
      trioRanks.push(r);
    }
  }
  if (trioRanks.length < 2) return null;
  trioRanks.sort((x, y) => x - y);

  // 尝试找出所有可能的连续三张序列，长度 k >= 2
  // 由于存在翅膀可能也有 >=3 张，需要尝试连续段
  const candidates: number[][] = [];
  for (let i = 0; i < trioRanks.length; i++) {
    const seq: number[] = [trioRanks[i]];
    for (let j = i + 1; j < trioRanks.length; j++) {
      if (trioRanks[j] === seq[seq.length - 1] + 1) {
        seq.push(trioRanks[j]);
        if (seq.length >= 2) candidates.push(seq.slice());
      } else {
        break;
      }
    }
  }

  for (const seq of candidates) {
    const k = seq.length;
    const trioSet = new Set(seq);
    // 验证：每个三张点数至少出现 3 次
    let ok = true;
    for (const r of seq) {
      if ((counts.get(r) ?? 0) < 3) {
        ok = false;
        break;
      }
    }
    if (!ok) continue;

    // 4n 结构：k 个三张 + k 个单张
    if (n === 4 * k) {
      // 剩余牌数量
      const remain: number[] = [];
      const tmp = new Map(counts);
      for (const r of seq) {
        tmp.set(r, tmp.get(r)! - 3);
      }
      for (const [r, c] of tmp) {
        for (let i = 0; i < c; i++) remain.push(r);
      }
      if (remain.length === k) {
        // 翅膀点数不能与三张同点
        let wingOk = true;
        for (const r of remain) {
          if (trioSet.has(r)) {
            wingOk = false;
            break;
          }
        }
        if (wingOk) {
          return { type: "plane_wings", cards: sorted, mainRank: seq[seq.length - 1], length: n };
        }
      }
    }

    // 5n 结构：k 个三张 + k 个对子
    if (n === 5 * k) {
      const tmp = new Map(counts);
      for (const r of seq) {
        tmp.set(r, tmp.get(r)! - 3);
      }
      // 剩余必须全是对子，数量恰好 2k，且每个点数出现 2 次，且不能与三张同点
      let wingOk = true;
      let total = 0;
      for (const [r, c] of tmp) {
        if (c === 0) continue;
        if (c !== 2) {
          wingOk = false;
          break;
        }
        if (trioSet.has(r)) {
          wingOk = false;
          break;
        }
        total += c;
      }
      if (wingOk && total === 2 * k) {
        return { type: "plane_wings", cards: sorted, mainRank: seq[seq.length - 1], length: n };
      }
    }
  }

  return null;
}

function tryFourWithTwo(sorted: number[], counts: Map<number, number>): Combo | null {
  // 四带二：6 张，一个四张 + 两张单张（可同点）
  if (sorted.length !== 6) return null;
  let fourRank = -1;
  let fourCount = 0;
  for (const [r, c] of counts) {
    if (c === 4) {
      fourRank = r;
      fourCount++;
    }
  }
  if (fourCount !== 1) return null;
  // 剩余两张：可以同点（对子）或不同点
  const remain = sorted.filter((r) => r !== fourRank);
  if (remain.length !== 2) return null;
  return { type: "four_with_two", cards: sorted, mainRank: fourRank, length: 6 };
}

export function parseCombo(cards: number[]): Combo {
  // 拷贝并排序
  const sorted = sortCards(cards);

  // 非法输入：空数组 或 含 <3 或 >17
  if (sorted.length === 0) return invalidCombo(sorted);
  for (const c of sorted) {
    if (c < 3 || c > 17) return invalidCombo(sorted);
  }

  const counts = countRanks(sorted);
  const n = sorted.length;

  // a. 王炸
  if (n === 2 && counts.has(16) && counts.has(17)) {
    return { type: "rocket", cards: sorted, mainRank: 17, length: 2 };
  }

  // b. 炸弹
  if (n === 4 && counts.size === 1) {
    const rank = sorted[0];
    return { type: "bomb", cards: sorted, mainRank: rank, length: 4 };
  }

  // c. 单张
  if (n === 1) {
    return { type: "single", cards: sorted, mainRank: sorted[0], length: 1 };
  }

  // d. 对子
  if (n === 2 && counts.size === 1) {
    return { type: "pair", cards: sorted, mainRank: sorted[0], length: 2 };
  }

  // e. 三张
  if (n === 3 && counts.size === 1) {
    return { type: "trio", cards: sorted, mainRank: sorted[0], length: 3 };
  }

  // f. 三带一：4 张，恰好 3+1
  if (n === 4 && counts.size === 2) {
    for (const [r, c] of counts) {
      if (c === 3) {
        return { type: "trio_single", cards: sorted, mainRank: r, length: 4 };
      }
    }
  }

  // g. 三带对：5 张，结构 3+2
  if (n === 5 && counts.size === 2) {
    let trioRank = -1;
    let pairFound = false;
    for (const [r, c] of counts) {
      if (c === 3) trioRank = r;
      else if (c === 2) pairFound = true;
    }
    if (trioRank !== -1 && pairFound) {
      return { type: "trio_pair", cards: sorted, mainRank: trioRank, length: 5 };
    }
  }

  // h. 顺子
  const straight = tryStraight(sorted, counts);
  if (straight) return straight;

  // i. 连对
  const pairStraight = tryPairStraight(sorted, counts);
  if (pairStraight) return pairStraight;

  // j. 飞机（不带翅膀）
  const plane = tryPlane(sorted, counts);
  if (plane) return plane;

  // k. 飞机带翅膀
  const planeWings = tryPlaneWings(sorted, counts);
  if (planeWings) return planeWings;

  // l. 四带二
  const fourWithTwo = tryFourWithTwo(sorted, counts);
  if (fourWithTwo) return fourWithTwo;

  // m. 其他一律非法
  return invalidCombo(sorted);
}

export function canBeat(a: Combo, b: Combo): boolean {
  // 任一非法则不能压
  if (a.type === "invalid" || b.type === "invalid") return false;

  // a 是王炸：除同为王炸外，压一切
  if (a.type === "rocket") {
    if (b.type === "rocket") return false;
    return true;
  }

  // b 是王炸：a 不是王炸，压不了
  if (b.type === "rocket") return false;

  // a 是炸弹
  if (a.type === "bomb") {
    if (b.type !== "bomb") return true;
    return a.mainRank > b.mainRank;
  }

  // b 是炸弹，a 不是炸弹/王炸
  if (b.type === "bomb") return false;

  // 其他情况：同牌型同长度比 mainRank
  if (a.type === b.type && a.length === b.length) {
    return a.mainRank > b.mainRank;
  }

  return false;
}