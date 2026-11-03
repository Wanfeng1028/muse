// 人物档案（命例库）：免重复录入。Local-first: profiles live in
// local storage now; cloud sync to a `profiles` collection is pending
// item 17 (needs envId). Cloud chartId and local profile id are two
// separate layers and are never conflated: a local profile converts to
// a SavedChart shape only for the CompareView, which takes charts as
// plain data and never writes back to the profile.
//
// One profile = one person; one profile holds many chart versions
// (different manual true-solar-time corrections of the same birth data).
// Sharing is read-only: a share link carries profile id + version and
// the chart page renders it without writing zw_chart_v1 and without a
// save button, so the original profile is never modified by a viewer.

import Taro from '@tarojs/taro';
import type { BirthFormInput } from './chart';
import { buildChart } from './chart';
import type { ZiweiChart } from '../engine/types';
import type { SavedChart } from './cloud';
import { chartKeyForUnlock } from './pricing';

export interface ProfileChart {
  version: number;
  label: string;
  input: BirthFormInput;
  chart: ZiweiChart;
  chartKey: string;
  createdAt: number;
}

export interface Profile {
  id: string;
  name: string;
  gender: 'male' | 'female';
  input: BirthFormInput;
  charts: ProfileChart[];
  createdAt: number;
  updatedAt: number;
}

const PROFILES_KEY = 'zw_profiles_v1';
// Handoff keys (same storage-transit pattern as lib/nav.ts goInterpret:
// Tab pages cannot receive navigateTo params, so the value is stored,
// read once by the target page, and cleared).
export const PROFILE_PICK_KEY = 'zw_profile_pick';
export const PROFILE_VERSION_TARGET_KEY = 'zw_profile_version_target';

function loadAll(): Profile[] {
  try {
    const v = Taro.getStorageSync(PROFILES_KEY);
    return Array.isArray(v) ? (v as Profile[]) : [];
  } catch {
    return [];
  }
}

function saveAll(list: Profile[]): void {
  try {
    Taro.setStorageSync(PROFILES_KEY, list);
  } catch {
    // Storage failure surfaces to the caller via the thrown path below;
    // this helper never silently drops a profile list.
    throw new Error('PROFILE_STORAGE_FAILED');
  }
}

function newId(): string {
  return 'p' + Date.now().toString(36) + Math.floor(Math.random() * 1000000).toString(36);
}

export function listProfiles(): Profile[] {
  return loadAll().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getProfile(id: string): Profile | null {
  return loadAll().find((p) => p.id === id) || null;
}

export function profileChartKey(input: BirthFormInput): string {
  return chartKeyForUnlock({
    date: input.date,
    clockHour: input.clockHour,
    clockMinute: input.clockMinute,
    province: input.province,
    city: input.city,
    longitude: input.longitude,
    gender: input.gender,
    corrections: input.corrections.join(','),
  });
}

// Create a profile from a birth form input. The first chart version is
// built immediately (buildChart is pure and local), so a profile always
// has at least one chart.
export function createProfile(input: BirthFormInput, label?: string): Profile {
  const chart = buildChart(input);
  const now = Date.now();
  const profile: Profile = {
    id: newId(),
    name: input.name || '未命名',
    gender: input.gender,
    input: input,
    charts: [{
      version: 1,
      label: label || '初版',
      input: input,
      chart: chart,
      chartKey: profileChartKey(input),
      createdAt: now,
    }],
    createdAt: now,
    updatedAt: now,
  };
  const list = loadAll();
  list.unshift(profile);
  saveAll(list);
  return profile;
}

// Edit the person's base fields. Editing does NOT rebuild existing
// chart versions (a version freezes the input it was built from); use
// addChartVersion to record a corrected chart for the same person.
export function updateProfile(id: string, patch: { name?: string; gender?: 'male' | 'female'; input?: BirthFormInput }): Profile | null {
  const list = loadAll();
  const p = list.find((x) => x.id === id);
  if (!p) return null;
  if (patch.name !== undefined) p.name = patch.name;
  if (patch.gender !== undefined) p.gender = patch.gender;
  if (patch.input !== undefined) p.input = patch.input;
  p.updatedAt = Date.now();
  saveAll(list);
  return p;
}

export function deleteProfile(id: string): boolean {
  const list = loadAll();
  const next = list.filter((p) => p.id !== id);
  if (next.length === list.length) return false;
  saveAll(next);
  return true;
}

// Add another chart version for the same person (e.g. after a different
// manual true-solar-time correction). Versions coexist; nothing is
// overwritten.
export function addChartVersion(profileId: string, input: BirthFormInput, label: string): ProfileChart | null {
  const list = loadAll();
  const p = list.find((x) => x.id === profileId);
  if (!p) return null;
  const chart = buildChart(input);
  const version: ProfileChart = {
    version: (p.charts.length > 0 ? Math.max.apply(null, p.charts.map((c) => c.version)) : 0) + 1,
    label: label || ('版本 ' + (p.charts.length + 1)),
    input: input,
    chart: chart,
    chartKey: profileChartKey(input),
    createdAt: Date.now(),
  };
  p.charts.push(version);
  p.updatedAt = Date.now();
  saveAll(list);
  return version;
}

export function deleteChartVersion(profileId: string, version: number): boolean {
  const list = loadAll();
  const p = list.find((x) => x.id === profileId);
  if (!p) return false;
  const next = p.charts.filter((c) => c.version !== version);
  if (next.length === p.charts.length) return false;
  // The last version cannot be deleted: a profile always keeps a chart.
  if (next.length === 0) return false;
  p.charts = next;
  p.updatedAt = Date.now();
  saveAll(list);
  return true;
}

export function latestChart(profile: Profile): ProfileChart | null {
  return profile.charts.length > 0 ? profile.charts[profile.charts.length - 1] : null;
}

// Convert a profile chart to the SavedChart shape CompareView accepts.
// The _id is synthetic (local profile id + version) and is only used as
// a React key / picker value inside the compare page; it is never sent
// to the cloud as a chart id.
export function profileToSavedChart(profile: Profile, version?: number): SavedChart | null {
  const c = version !== undefined
    ? profile.charts.find((x) => x.version === version) || null
    : latestChart(profile);
  if (!c) return null;
  return {
    _id: 'local-' + profile.id + '-v' + c.version,
    name: profile.name,
    birthParams: c.input as unknown as Record<string, unknown>,
    chartData: c.chart,
    chartHash: c.chartKey,
    isDefault: false,
    createdAt: new Date(c.createdAt).toISOString(),
    updatedAt: new Date(profile.updatedAt).toISOString(),
  };
}
