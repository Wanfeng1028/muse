// 职责：@botstalk/protocol 房间类型相关的类型定义与常量。
// 与 docs/SOUL-rooms.md 契约一致：room_type 取值 workroom | playroom。

export type RoomType = "workroom" | "playroom";

export const ROOM_TYPE_WORKROOM: RoomType = "workroom";
export const ROOM_TYPE_PLAYROOM: RoomType = "playroom";

export const ROOM_TYPES: readonly RoomType[] = [ROOM_TYPE_WORKROOM, ROOM_TYPE_PLAYROOM];

export function isRoomType(value: unknown): value is RoomType {
  return value === ROOM_TYPE_WORKROOM || value === ROOM_TYPE_PLAYROOM;
}

/** 房间类型默认值：新房间缺省为工作坊。 */
export const DEFAULT_ROOM_TYPE: RoomType = ROOM_TYPE_WORKROOM;

/** 游戏清单：按房间类型过滤，网关强制，不依赖模型。 */
export const WORKROOM_GAMES: readonly string[] = [
  "vote_plan",
  "timed_brainstorm",
  "roleplay_review",
];

export const PLAYROOM_GAMES: readonly string[] = [
  "who_is_undercover",
  "word_chain",
  "draw_and_guess",
  "ai_roast_arena",
  "doudizhu",
];

export function gamesForRoomType(roomType: RoomType): readonly string[] {
  return roomType === ROOM_TYPE_WORKROOM ? WORKROOM_GAMES : PLAYROOM_GAMES;
}

export function isGameAllowed(roomType: RoomType, game: string): boolean {
  return gamesForRoomType(roomType).includes(game);
}

/** 权限：workroom 只有房主能改人设/拉人/开话题；playroom 所有成员都能。 */
export function canUpdateRoom(roomType: RoomType, isOwner: boolean): boolean {
  return roomType === ROOM_TYPE_PLAYROOM ? true : isOwner;
}

export function canInvite(roomType: RoomType, isOwner: boolean): boolean {
  return roomType === ROOM_TYPE_PLAYROOM ? true : isOwner;
}

export function canStartTopic(roomType: RoomType, isOwner: boolean): boolean {
  return roomType === ROOM_TYPE_PLAYROOM ? true : isOwner;
}

/** 保留给房主的权限：清屏、踢人。 */
export function canClearOrKick(_roomType: RoomType, isOwner: boolean): boolean {
  return isOwner;
}

/** 路由策略：workroom 定向，playroom 广播。 */
export type RouteStrategy = "directed" | "broadcast";

export function routeStrategyFor(roomType: RoomType): RouteStrategy {
  return roomType === ROOM_TYPE_WORKROOM ? "directed" : "broadcast";
}

/** 房间更新消息体（room.update）。 */
export interface RoomUpdatePayload {
  room_id: string;
  room_type?: RoomType;
  name?: string;
  topic?: string;
}

/** 房间元数据（持久属性）。 */
export interface RoomMeta {
  id: string;
  room_type: RoomType;
  name?: string;
  topic?: string;
  owner?: string;
  created_at_ms: number;
  updated_at_ms: number;
}

/** 小游戏会话状态。 */
export type GameSessionStatus = "active" | "finished" | "aborted";

export interface GameSession {
  id: string;
  room_id: string;
  game: string;
  status: GameSessionStatus;
  state_json: string;
  created_at_ms: number;
  updated_at_ms: number;
}