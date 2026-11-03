import type { CSSProperties, ReactNode } from 'react'

type IconProps = {
  name: IconName
  size?: number
  stroke?: number
  className?: string
  style?: CSSProperties
}

const shapes = {
  'arrow-left': <path d="M15 5l-7 7 7 7" />,
  'arrow-right': <path d="M5 12h14M13 6l6 6-6 6" />,
  'arrow-up': <path d="M12 19V5M6 11l6-6 6 6" />,
  'chevron-right': <path d="M9 6l6 6-6 6" />,
  'chevron-down': <path d="M6 9l6 6 6-6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  bell: (
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M16.5 16.5L21 21" />
    </>
  ),
  filter: <path d="M4 7h16M7 12h10M10 17h4" />,
  home: <path d="M3 10.5L12 3l9 7.5M5 9.5V21h14V9.5M9.5 21v-5h5v5" />,
  doc: (
    <>
      <rect x="5" y="3.5" width="14" height="17" rx="2.5" />
      <path d="M8.5 8h7M8.5 12h7M8.5 16h4" />
    </>
  ),
  wallet: (
    <>
      <rect x="3.5" y="6" width="17" height="13" rx="2.5" />
      <path d="M3.5 10h17M16 14.5h.01" />
    </>
  ),
  sparkles: (
    <>
      <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z" />
      <path d="M18.5 15l.9 2.3 2.3.9-2.3.9-.9 2.3-2.3-.9 2.3-.9z" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M5.9 5.9l1.4 1.4M16.7 16.7l1.4 1.4M18.1 5.9L16.7 7.3M7.3 16.7l-1.4 1.4" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </>
  ),
  battery: (
    <>
      <rect x="3" y="7.5" width="15" height="9" rx="2" />
      <path d="M21 10.5v3M6 10h5" />
    </>
  ),
  bulb: (
    <>
      <path d="M9 18h6M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.2 11.1V15h6.4v-1.9A6 6 0 0 0 12 3z" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5M12 15v2" />
    </>
  ),
  wifi: (
    <>
      <path d="M3.5 9a13 13 0 0 1 17 0M6.5 12.5a8.5 8.5 0 0 1 11 0M9.5 16a4 4 0 0 1 5 0" />
      <circle cx="12" cy="19" r=".8" fill="currentColor" />
    </>
  ),
  power: (
    <>
      <path d="M12 3v8" />
      <path d="M7 6.2a8 8 0 1 0 10 0" />
    </>
  ),
  copy: (
    <>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.8 9a2.3 2.3 0 0 1 4.4.7c0 1.6-2.2 1.7-2.2 3.3M12 17h.01" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="6.5" width="12" height="11" rx="2.5" />
      <path d="M15 10.5l5-3v9l-5-3z" />
    </>
  ),
  calendar: (
    <>
      <rect x="4" y="5" width="16" height="15" rx="2.5" />
      <path d="M4 9.5h16M8 3v4M16 3v4" />
    </>
  ),
  swap: (
    <>
      <path d="M4 9h13M14 5l3 4-3 4M20 15H7M10 11l-3 4 3 4" />
    </>
  ),
  send: <path d="M21 3L10.5 13.5M21 3l-7 18-3.5-7.5L3 10z" />,
  grid: (
    <>
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.4" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.4" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.4" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.4" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 19a6.5 6.5 0 0 1 13 0M16.5 5.5a3.5 3.5 0 0 1 0 7M17 14.5a6 6 0 0 1 4.5 4.5" />
    </>
  ),
  heart: (
    <path d="M12 20s-7-4.3-7-9.5A3.9 3.9 0 0 1 12 7a3.9 3.9 0 0 1 7 3.5C19 15.7 12 20 12 20z" />
  ),
  list: (
    <>
      <path d="M8 6h12M8 12h12M8 18h12" />
      <circle cx="4" cy="6" r=".9" fill="currentColor" />
      <circle cx="4" cy="12" r=".9" fill="currentColor" />
      <circle cx="4" cy="18" r=".9" fill="currentColor" />
    </>
  ),
  chat: (
    <>
      <path d="M20 12a7 7 0 0 1-9.6 6.5L5 20l1.5-4.6A7 7 0 1 1 20 12z" />
      <path d="M9 11h.01M13 11h.01M17 11h.01" />
    </>
  ),
  umbrella: (
    <>
      <path d="M3.5 12a8.5 8.5 0 0 1 17 0z" />
      <path d="M12 12v6.5a2 2 0 0 0 4 0" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M19.1 4.9L17.6 6.4M6.4 17.6L4.9 19.1" />
    </>
  ),
  droplet: <path d="M12 3.5s6 6.4 6 10.2a6 6 0 0 1-12 0c0-3.8 6-10.2 6-10.2z" />,
  box: (
    <>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />
      <path d="M4 7.5l8 4.5 8-4.5M12 12v9" />
    </>
  ),
  flask: (
    <>
      <path d="M9 3h6M10 3v6L5.5 19a2 2 0 0 0 1.8 2h9.4a2 2 0 0 0 1.8-2L14 9V3" />
      <path d="M7.5 15h9" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 6v5h-5" />
      <path d="M4 18v-5h5" />
      <path d="M19 11a7.5 7.5 0 0 0-12.8-4.4M5 13a7.5 7.5 0 0 0 12.8 4.4" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7.5 3v6c0 4.5-3.2 7.8-7.5 9-4.3-1.2-7.5-4.5-7.5-9V6z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  leaf: (
    <>
      <path d="M5 19c0-8 5.5-14 15-14 0 9-5.5 14-13 14" />
      <path d="M4 20c3-5 6-7 10-9" />
    </>
  ),
  check: <path d="M4 12.5l5 5L20 6" />,
  'plus-circle': (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 8v8M8 12h8" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 8h.01" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="8" r="4" />
      <path d="M11 11l9 9M17 17l2-2M15 15l2-2" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c2.5 2.4 3.8 5.4 3.8 8.5s-1.3 6.1-3.8 8.5c-2.5-2.4-3.8-5.4-3.8-8.5s1.3-6.1 3.8-8.5z" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r="1.1" fill="currentColor" />
      <circle cx="12" cy="12" r="1.1" fill="currentColor" />
      <circle cx="19" cy="12" r="1.1" fill="currentColor" />
    </>
  ),
  apple: (
    <>
      <path
        d="M12.4 6.6c1.4 0 2.4-.8 3.3-1.9.8-1 1.3-2.3 1.2-3.5-1.2.1-2.4.8-3.2 1.8-.7.9-1.3 2.2-1.3 3.6z"
        fill="currentColor"
        stroke="none"
      />
      <path
        d="M15.8 20.6c1.1 0 2.5-.7 3.4-1.7.2-.2.3-.3.4-.5-1-.5-1.9-1-2.5-1.9-.6-.8-.8-1.9-.6-3 .1-.9.6-1.7 1.3-2.3.8-.6 1.7-.9 2.3-.8-.3-1.2-.9-2.3-1.9-3-1.1-.9-2.4-1.3-3.7-1.2-1.5 0-3 .6-4.2 1.6l-.3.3-.4-.1c-2.5-.7-4.9.6-5.9 2.9-1.2 2.8-.6 6.1 1.5 8.3.7.7 1.5 1.3 2.5 1.6 2.7.8 5.2-.2 6.9-2.1z"
        fill="currentColor"
        stroke="none"
      />
      <path d="M12.6 4.8c.5-1.1 1.6-1.9 2.8-2" fill="currentColor" stroke="none" />
    </>
  ),
} satisfies Record<string, ReactNode>

export type IconName = keyof typeof shapes

export function Ico({ name, size = 18, stroke = 1.6, className, style }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      {shapes[name]}
    </svg>
  )
}

export function GoogleG({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-label="Google">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  )
}
