export interface ConflictInfo {
  currentVersion: number;
  updatedBy: string;
}

export function parseConflictBody(json: unknown): ConflictInfo | null {
  if (typeof json !== 'object' || json === null) return null;
  const o = json as Record<string, unknown>;
  const cv = o['current_version'];
  const ub = o['updated_by'];
  if (typeof cv !== 'number' || typeof ub !== 'string') return null;
  return { currentVersion: cv, updatedBy: ub };
}

export function conflictMessage(info: ConflictInfo): string {
  return info.updatedBy === 'agent'
    ? '内容已被 agent 修改，是否刷新？'
    : '内容已被其他编辑者修改，是否刷新？';
}

export const THEME_WHITELIST: readonly string[] = [
  '--ph-canvas-bg',
  '--ph-panel-bg',
  '--ph-panel-border',
  '--ph-text',
  '--ph-accent',
];

export function readThemeWhitelist(host: HTMLElement): Record<string, string> {
  const cs = getComputedStyle(host);
  const out: Record<string, string> = {};
  for (const name of THEME_WHITELIST) {
    const v = cs.getPropertyValue(name).trim();
    if (v) out[name] = v;
  }
  return out;
}
