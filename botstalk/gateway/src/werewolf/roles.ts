/**
 * 狼人杀角色与配置表。
 * 纯数据 + 分配函数，不依赖其他模块。
 */

export type Role =
  | "werewolf"
  | "villager"
  | "seer"
  | "witch"
  | "hunter"
  | "guard";

export type Faction = "wolves" | "good";

export interface RoleInfo {
  name: string; // 中文名
  faction: Faction;
  skill: string; // 技能中文描述一句话
}

export const ROLE_INFO: Record<Role, RoleInfo> = {
  werewolf: {
    name: "狼人",
    faction: "wolves",
    skill: "夜晚与同伴共同选择一名玩家击杀。",
  },
  villager: {
    name: "平民",
    faction: "good",
    skill: "无特殊技能，白天通过发言与投票找出狼人。",
  },
  seer: {
    name: "预言家",
    faction: "good",
    skill: "每晚查验一名玩家的阵营是好人还是狼人。",
  },
  witch: {
    name: "女巫",
    faction: "good",
    skill: "拥有一瓶解药和一瓶毒药，每晚各可用一次（全局各仅一次）。",
  },
  hunter: {
    name: "猎人",
    faction: "good",
    skill: "被狼人杀死或被投票放逐出局时可开枪带走一名玩家。",
  },
  guard: {
    name: "守卫",
    faction: "good",
    skill: "每晚守护一名玩家免于被狼人击杀，不能连续两晚守护同一人。",
  },
};

/**
 * 标准配置表：人数 -> 角色列表（顺序无关，assignRoles 会洗牌分配）。
 * 6:2狼3民预言家
 * 7:2狼3民预言家女巫
 * 8:2狼4民预言家女巫
 * 9:3狼3民预言家女巫猎人
 * 10:3狼3民预言家女巫猎人守卫
 * 11:3狼4民预言家女巫猎人守卫
 * 12:4狼4民预言家女巫猎人守卫
 */
export const SUPPORTED_COUNTS: Record<number, Role[]> = {
  6: ["werewolf", "werewolf", "villager", "villager", "villager", "seer"],
  7: [
    "werewolf",
    "werewolf",
    "villager",
    "villager",
    "villager",
    "seer",
    "witch",
  ],
  8: [
    "werewolf",
    "werewolf",
    "villager",
    "villager",
    "villager",
    "villager",
    "seer",
    "witch",
  ],
  9: [
    "werewolf",
    "werewolf",
    "werewolf",
    "villager",
    "villager",
    "villager",
    "seer",
    "witch",
    "hunter",
  ],
  10: [
    "werewolf",
    "werewolf",
    "werewolf",
    "villager",
    "villager",
    "villager",
    "seer",
    "witch",
    "hunter",
    "guard",
  ],
  11: [
    "werewolf",
    "werewolf",
    "werewolf",
    "villager",
    "villager",
    "villager",
    "villager",
    "seer",
    "witch",
    "hunter",
    "guard",
  ],
  12: [
    "werewolf",
    "werewolf",
    "werewolf",
    "werewolf",
    "villager",
    "villager",
    "villager",
    "villager",
    "seer",
    "witch",
    "hunter",
    "guard",
  ],
};

/**
 * 按人数配置为每个座位分配角色。
 * seats 长度必须是 SUPPORTED_COUNTS 中的键，否则抛 Error。
 * 用 rng 洗牌保证可播种确定性。
 */
export function assignRoles(
  seats: string[],
  rng: () => number = Math.random,
): Map<string, Role> {
  if (!Array.isArray(seats)) {
    throw Error("seats 必须是数组");
  }
  const roles = SUPPORTED_COUNTS[seats.length];
  if (!roles) {
    throw Error(
      `不支持的人数: ${seats.length}（支持 ${Object.keys(SUPPORTED_COUNTS).join("/")}）`,
    );
  }
  for (const s of seats) {
    if (typeof s !== "string" || s.length === 0) {
      throw Error("座位必须是非空字符串");
    }
  }
  const pool = roles.slice();
  // Fisher-Yates
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = pool[i];
    pool[i] = pool[j];
    pool[j] = tmp;
  }
  const result = new Map<string, Role>();
  for (let i = 0; i < seats.length; i++) {
    result.set(seats[i], pool[i]);
  }
  return result;
}
