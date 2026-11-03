import type { ReactNode } from 'react'

export function StatusBar({ light = false, island = false }: { light?: boolean; island?: boolean }) {
  return (
    <div className={`statusbar${light ? ' statusbar--light' : ''}`}>
      {island && <div className="dynamic-island" aria-hidden="true" />}
      <span className="statusbar__time">9:41</span>
      <div className="statusbar__icons" aria-hidden="true">
        <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor">
          <rect x="0" y="7.5" width="3" height="3.5" rx="0.8" />
          <rect x="4.4" y="5.5" width="3" height="5.5" rx="0.8" />
          <rect x="8.8" y="3.4" width="3" height="7.6" rx="0.8" />
          <rect x="13.2" y="1" width="3" height="10" rx="0.8" />
        </svg>
        <svg width="15" height="11" viewBox="0 0 24 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M3 6.5a13 13 0 0 1 18 0M6.5 10.5a8.5 8.5 0 0 1 11 0" />
          <circle cx="12" cy="15" r="1.4" fill="currentColor" stroke="none" />
        </svg>
        <svg width="24" height="11" viewBox="0 0 28 13" fill="none">
          <rect x="0.6" y="1.2" width="23" height="10.6" rx="3" stroke="currentColor" opacity="0.5" />
          <rect x="2.2" y="2.8" width="18" height="7.4" rx="1.8" fill="currentColor" />
          <path d="M26 4.8v3.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
        </svg>
      </div>
    </div>
  )
}

export function HomeBar({ light = false }: { light?: boolean }) {
  return <div className={`homebar${light ? ' homebar--light' : ''}`} aria-hidden="true" />
}

export function Avatar({
  name,
  size = 36,
  tone = 'sand',
}: {
  name: string
  size?: number
  tone?: 'sand' | 'clay' | 'sage' | 'sky' | 'rose'
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <div
      className={`avatar avatar--${tone}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.3) }}
      title={name}
      aria-label={name}
    >
      {initials}
    </div>
  )
}

export function Screen({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`screen ${className}`}>{children}</div>
}
