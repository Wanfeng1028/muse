/**
 * 来源 sdk/src/openagents/mods/coordination/task_delegation/capability_matcher.py
 * （Apache-2.0，算法思想移植、代码重写；本包代码沿用仓库 MIT 许可）
 */

export interface CapabilityRequirement {
  skills?: string[];
  tags?: string[];
  input_modes?: string[];
  output_modes?: string[];
}

export interface NormalizedCapability {
  agent_id: string;
  agent_type: "local" | "registry";
  skills: string[];
  tags: string[];
  input_modes: string[];
  output_modes: string[];
  description?: string;
  raw_capabilities: unknown;
}

export interface LocalAdapterInput {
  skills?: string[];
  tags?: string[];
  input_modes?: string[];
  output_modes?: string[];
  description?: string;
  raw?: unknown;
}

export interface ScoreResult {
  score: number;
  breakdown: {
    skills: number;
    tags: number;
    input_modes: number;
    output_modes: number;
  };
  matched: string[];
  missing: string[];
}

export interface PickResult {
  pick: string | null;
  scores: Record<string, number>;
  bestScore: number;
}

/** 只保留非空字符串，去重保序；非数组返回空数组 */
function cleanStringArray(arr: unknown): string[] {
  if (!Array.isArray(arr)) return [];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of arr) {
    if (typeof item === "string" && item !== "") {
      if (!seen.has(item)) {
        seen.add(item);
        result.push(item);
      }
    }
  }
  return result;
}

/** 将本地适配器输入归一化为标准能力描述 */
export function normalizeLocalAdapter(
  agentId: string,
  input: LocalAdapterInput
): NormalizedCapability {
  const skills = cleanStringArray(input.skills);
  const tags = cleanStringArray(input.tags);
  const inputModes = cleanStringArray(input.input_modes);
  const outputModes = cleanStringArray(input.output_modes);
  return {
    agent_id: agentId,
    agent_type: "local",
    skills,
    tags,
    input_modes: inputModes.length > 0 ? inputModes : ["text"],
    output_modes: outputModes.length > 0 ? outputModes : ["text"],
    description: input.description,
    raw_capabilities: input.raw !== undefined ? input.raw : input,
  };
}

/** ALL 语义：每个非空维度要求 agent 全部具备，维度缺失或空数组恒过 */
export function matchStructured(
  required: CapabilityRequirement,
  normalized: NormalizedCapability
): boolean {
  const check = (req: string[] | undefined, agent: string[]): boolean => {
    if (!req || req.length === 0) return true;
    const set = new Set(agent);
    return req.every((item) => set.has(item));
  };
  return (
    check(required.skills, normalized.skills) &&
    check(required.tags, normalized.tags) &&
    check(required.input_modes, normalized.input_modes) &&
    check(required.output_modes, normalized.output_modes)
  );
}

/** 加权评分，仅对 required 中非空维度计分并重归一化权重 */
export function scoreCapability(
  required: CapabilityRequirement,
  normalized: NormalizedCapability
): ScoreResult {
  type Key = "skills" | "tags" | "input_modes" | "output_modes";

  const rawWeights: Record<Key, number> = {
    skills: 0.5,
    tags: 0.25,
    input_modes: 0.125,
    output_modes: 0.125,
  };

  const dims: Array<{ key: Key; req: string[] | undefined; agent: string[] }> = [
    { key: "skills", req: required.skills, agent: normalized.skills },
    { key: "tags", req: required.tags, agent: normalized.tags },
    { key: "input_modes", req: required.input_modes, agent: normalized.input_modes },
    { key: "output_modes", req: required.output_modes, agent: normalized.output_modes },
  ];

  /* 筛选在场维度（required 中对应数组非空） */
  const present = dims.filter((d) => Array.isArray(d.req) && d.req!.length > 0);

  /* required 全空时直接返回零值 */
  if (present.length === 0) {
    return {
      score: 0,
      breakdown: { skills: 0, tags: 0, input_modes: 0, output_modes: 0 },
      matched: [],
      missing: [],
    };
  }

  /* 按在场维度重归一化权重总和 */
  const weightSum = present.reduce((s, d) => s + rawWeights[d.key], 0);

  let score = 0;
  const breakdown: Record<Key, number> = {
    skills: 0,
    tags: 0,
    input_modes: 0,
    output_modes: 0,
  };

  for (const dim of present) {
    const reqSet = new Set(dim.req!);
    const agentSet = new Set(dim.agent);
    let hit = 0;
    for (const item of reqSet) {
      if (agentSet.has(item)) hit++;
    }
    const dimScore = hit / reqSet.size;
    breakdown[dim.key] = dimScore;
    score += (rawWeights[dim.key] / weightSum) * dimScore;
  }

  /* matched / missing 仅统计 skills + tags 维度，保序去重 */
  const matched: string[] = [];
  const missing: string[] = [];
  const seen = new Set<string>();

  const stDims: Array<{ req: string[] | undefined; agent: string[] }> = [
    { req: required.skills, agent: normalized.skills },
    { req: required.tags, agent: normalized.tags },
  ];

  for (const { req, agent } of stDims) {
    if (!req) continue;
    const agentSet = new Set(agent);
    for (const item of req) {
      if (typeof item !== "string" || item === "") continue;
      if (seen.has(item)) continue;
      seen.add(item);
      if (agentSet.has(item)) {
        matched.push(item);
      } else {
        missing.push(item);
      }
    }
  }

  return {
    score,
    breakdown: { skills: breakdown.skills, tags: breakdown.tags, input_modes: breakdown.input_modes, output_modes: breakdown.output_modes },
    matched,
    missing,
  };
}

/** 逐个评分，最高分且 > 0 者胜出；并列取 id 字典序最小者 */
export function pickBestCandidate(
  candidates: Array<{ id: string; capability: NormalizedCapability }>,
  required: CapabilityRequirement
): PickResult {
  const scores: Record<string, number> = {};

  if (candidates.length === 0) {
    return { pick: null, scores, bestScore: 0 };
  }

  let bestScore = -Infinity;
  let bestId: string | null = null;

  for (const c of candidates) {
    const result = scoreCapability(required, c.capability);
    scores[c.id] = result.score;
    if (result.score > bestScore) {
      bestScore = result.score;
      bestId = c.id;
    } else if (result.score === bestScore && c.id < bestId!) {
      bestId = c.id;
    }
  }

  /* 最高分 <= 0 时不选中 */
  if (bestScore <= 0) {
    return { pick: null, scores, bestScore: 0 };
  }

  return { pick: bestId, scores, bestScore };
}
