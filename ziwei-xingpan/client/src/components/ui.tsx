import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import { DISCLAIMER } from '../lib/chart';
import { Icon } from './icons';
import './ui.scss';

// v3 ambient layers REMOVED (2026-11-02 rules 1+9: the layers were
// fixed-position radial gradients — both banned). The exports stay
// as documented no-ops so the dozen page call sites need no churn;
// they render nothing. Re-enable only if the user re-allows fixed
// gradient layers.
export function Ambient({ welcome }: { welcome?: boolean }) {
  void welcome;
  return null;
}

export function AmbientLight() {
  return null;
}

export function Card({ title, children, light }: { title?: string; children: ReactNode; light?: boolean }) {
  return (
    <View className={light ? 'card card-light' : 'card'}>
      {title ? <View className='card-title'>{title}</View> : null}
      {children}
    </View>
  );
}

// Medley InputBar single (composer): 56 bar + 36 send circle.
// The home submit action lives here, not in a full-width white button.
export function ComposerBar({ label, onClick, light }: { label: string; onClick: () => void; light?: boolean }) {
  return (
    <View className={light ? 'composer composer-light' : 'composer'} onClick={onClick}>
      <Text className='composer-label'>{label}</Text>
      <View className='composer-send' hoverClass='btn-press'>
        <Icon name='arrow-up' tone='white' size='38px' />
      </View>
    </View>
  );
}

export function Pill({ text, accent }: { text: string; accent?: boolean }) {
  return <Text className={accent ? 'chip chip-accent' : 'chip'}>{text}</Text>;
}

export function Disclaimer() {
  return <View className='disclaimer'>{DISCLAIMER}</View>;
}

// Segmented capsule control (Vant Cell / 宫垣 gender row pattern):
// options render as pills, the selected one as a solid pill. Dark pages:
// gold pill + black text (matches the 宫垣 gold selected 男). Light
// pages: violet pill + white text (light theme accent).
export function SegmentedControl({ options, value, onChange, tone }: {
  options: string[]; value: number; onChange: (i: number) => void; tone?: 'dark' | 'light';
}) {
  const cls = tone === 'light' ? 'segctl segctl-light' : 'segctl segctl-dark';
  return (
    <View className={cls}>
      {options.map((label, i) => (
        <View key={label} className={i === value ? 'segctl-opt segctl-opt-active' : 'segctl-opt'} onClick={() => onChange(i)}>
          <Text>{label}</Text>
        </View>
      ))}
    </View>
  );
}

// Vector cover card (knowledge): category gradient + abstract deco
// (translucent circle + dot, pure CSS — the logo mark is NOT reused as
// decoration) + bold title. No photos exist in this app and external
// hotlinks are not shippable, so covers are drawn, not fetched — the s5
// "image-led" bar is met by a real visual block + title hierarchy,
// honestly, not by a fake photo.
export function Cover({ kind, title, sub }: { kind: string; title: string; sub?: string }) {
  return (
    <View className={`cover cover-${kind}`}>
      <View className='cover-deco' />
      <View className='cover-deco-dot' />
      <Text className='cover-title'>{title}</Text>
      {sub ? <Text className='cover-sub'>{sub}</Text> : null}
    </View>
  );
}

// Honest empty state: states what is missing and what unlocks it.
// Never used to dress up a missing feature as content.
export function EmptyState({ title, hint, actionLabel, onAction }: {
  title: string; hint: string; actionLabel?: string; onAction?: () => void;
}) {
  return (
    <View className='empty-state'>
      <Text className='empty-state-title'>{title}</Text>
      <Text className='empty-state-hint'>{hint}</Text>
      {actionLabel && onAction ? (
        <View className='btn-medley btn-medley-outline-light empty-state-action' onClick={onAction}>{actionLabel}</View>
      ) : null}
    </View>
  );
}
