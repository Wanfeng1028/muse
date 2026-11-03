import type { ActivatedSkillGuidance } from "../agent/skill-tool.js";
import type { WorkManifest, WorkProfile } from "../harness/contracts.js";
import type { AgentSkill, SkillResolutionResult } from "./types.js";

export function applyRequiredProfileSkills(
  resolution: SkillResolutionResult,
  profile: WorkProfile,
): SkillResolutionResult {
  const required = resolveProfileSkillActivations(resolution.availableSkills, profile);
  const used = new Map<string, AgentSkill>();
  for (const activation of required) used.set(activation.skill.id, activation.skill);
  for (const skill of resolution.usedSkills) used.set(skill.id, skill);
  return {
    ...resolution,
    usedSkills: [...used.values()],
    forcedSkillIds: [...new Set([...profile.requiredSkillIds, ...resolution.forcedSkillIds])],
  };
}

const WORK_CREATION_SKILLS: Readonly<Record<string, string>> = {
  fanfic: "inkos-fanfic-writing",
  continuation: "inkos-continuation-writing",
  spinoff: "inkos-spinoff-writing",
  imitation: "inkos-imitation-writing",
};

export function requiredWorkSkillIds(work: WorkManifest | null): string[] {
  const creationKind = work?.metadata.creationKind;
  if (typeof creationKind !== "string") return [];
  const skillId = WORK_CREATION_SKILLS[creationKind];
  return skillId ? [skillId] : [];
}

export function resolveWorkSkillActivations(
  availableSkills: ReadonlyArray<AgentSkill>,
  work: WorkManifest | null,
): ActivatedSkillGuidance[] {
  const requiredIds = requiredWorkSkillIds(work);
  if (requiredIds.length === 0) return [];
  const byId = new Map(availableSkills.map((skill) => [skill.id, skill]));
  const missing = requiredIds.filter((id) => !byId.has(id));
  if (missing.length > 0) {
    throw new Error(`Work "${work?.id}" requires unavailable skill(s): ${missing.join(", ")}`);
  }
  return requiredIds.map((id) => ({ skill: byId.get(id)!, resources: [] }));
}

export function applyRequiredWorkSkills(
  resolution: SkillResolutionResult,
  work: WorkManifest | null,
): SkillResolutionResult {
  const required = resolveWorkSkillActivations(resolution.availableSkills, work);
  if (required.length === 0) return resolution;
  const used = new Map(resolution.usedSkills.map((skill) => [skill.id, skill]));
  for (const activation of required) used.set(activation.skill.id, activation.skill);
  return {
    ...resolution,
    usedSkills: [...used.values()],
    forcedSkillIds: [...new Set([...resolution.forcedSkillIds, ...required.map((item) => item.skill.id)])],
  };
}

export function resolveProfileSkillActivations(
  availableSkills: ReadonlyArray<AgentSkill>,
  profile: WorkProfile,
  options: { readonly includeRecommended?: boolean } = {},
): ActivatedSkillGuidance[] {
  const byId = new Map(availableSkills.map((skill) => [skill.id, skill]));
  const missingRequired = profile.requiredSkillIds.filter((id) => !byId.has(id));
  if (missingRequired.length > 0) {
    throw new Error(
      `Profile "${profile.id}" requires unavailable skill(s): ${missingRequired.join(", ")}`,
    );
  }
  const ids = options.includeRecommended
    ? [...profile.requiredSkillIds, ...profile.recommendedSkillIds]
    : profile.requiredSkillIds;
  return [...new Set(ids)].flatMap((id) => {
    const skill = byId.get(id);
    return skill ? [{ skill, resources: [] }] : [];
  });
}

export function mergeActivatedSkillGuidance(
  ...groups: ReadonlyArray<ReadonlyArray<ActivatedSkillGuidance>>
): ActivatedSkillGuidance[] {
  const merged = new Map<string, ActivatedSkillGuidance>();
  for (const group of groups) {
    for (const activation of group) merged.set(activation.skill.id, activation);
  }
  return [...merged.values()];
}

export function activatedSkillIds(
  activations: ReadonlyArray<ActivatedSkillGuidance>,
): string[] {
  return activations.map((activation) => activation.skill.id);
}
