// CodexCopy 图标库 — 手写 SVG（复刻 Codex 界面图标风格）

const I = ({ children, size, vb = '0 0 16 16', fill = false, sw = 1.5 }) => (
  <svg width={size} height={size} viewBox={vb} fill={fill ? 'currentColor' : 'none'}
    stroke={fill ? 'none' : 'currentColor'} strokeWidth={fill ? undefined : sw} aria-hidden="true">
    {children}
  </svg>
);

export const CodexLogo = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 500 500" fill="currentColor" aria-hidden="true">
    <path d="M330.34 313.62h-67.84c-7.65 0-13.85-6.2-13.85-13.85s6.2-13.85 13.85-13.85h67.84c7.65 0 13.85 6.2 13.85 13.85s-6.2 13.85-13.85 13.85Z" />
    <path d="M169.65 313.38c-2.36 0-4.74-.6-6.93-1.87-6.62-3.83-8.88-12.31-5.05-18.93l23.78-41.08-23.91-43.21c-3.7-6.69-1.28-15.12 5.41-18.82 6.69-3.71 15.12-1.28 18.82 5.41l31.51 56.94-31.64 54.65c-2.57 4.43-7.22 6.91-12 6.91Z" />
    <path d="M144.61 144.5c1.42-41.82 35.79-75.27 77.95-75.25 27.89.02 52.35 14.68 66.11 36.71 10.93-5.82 23.41-9.12 36.65-9.11 43.05.02 77.94 34.94 77.91 78 0 13.24-3.32 25.72-9.16 36.64 22.02 13.79 36.66 38.26 36.64 66.15-.02 42.16-33.52 76.48-75.34 77.86-1.42 41.82-35.78 75.28-77.94 75.25-27.89-.02-52.35-14.68-66.11-36.72-10.93 5.82-23.4 9.13-36.65 9.12-43.05-.02-77.94-34.94-77.91-78 0-13.24 3.32-25.72 9.16-36.64-22.02-13.79-36.65-38.26-36.64-66.15.02-42.16 33.51-76.48 75.33-77.86ZM297.77 71.99c-19.24-19.26-45.83-31.17-75.2-31.19-49.23-.03-90.67 33.39-102.84 78.79-45.41 12.12-78.87 53.52-78.9 102.76-.02 29.37 11.87 55.97 31.1 75.23-2.35 8.79-3.62 18.03-3.63 27.56-.03 58.77 47.58 106.44 106.35 106.47 9.53 0 18.77-1.25 27.55-3.6 19.24 19.26 45.84 31.18 75.21 31.2 49.24.03 90.67-33.39 102.84-78.8 45.42-12.11 78.88-53.51 78.91-102.75.02-29.37-11.87-55.98-31.11-75.24 2.35-8.78 3.62-18.02 3.63-27.55.03-58.77-47.58-106.44-106.35-106.47-9.53 0-18.77 1.25-27.56 3.59Z" />
  </svg>
);

export const PlusIcon = ({ size = 15 }) => (
  <I size={size} sw={1.6}><path d="M8 2v12M2 8h12" strokeLinecap="round" /></I>
);
export const SearchIcon = ({ size = 16 }) => (
  <I size={size} sw={1.6}><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" strokeLinecap="round" /></I>
);
export const SettingsIcon = ({ size = 17 }) => (
  <I size={size}><circle cx="8" cy="8" r="2.2" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4" strokeLinecap="round" /></I>
);
export const SendIcon = ({ size = 15 }) => (
  <I size={size} sw={1.8}><path d="M8 14V2M3.5 6.5 8 2l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const AttachIcon = ({ size = 15 }) => (
  <I size={size}><path d="M11 7 5.8 12.2a2.3 2.3 0 0 1-3.2-3.2L9.4 2.2a1.6 1.6 0 0 1 2.3 2.3L5 11.2" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const ChevronDown = ({ size = 14 }) => (
  <I size={size} sw={1.6}><path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const ChevronRight = ({ size = 14 }) => (
  <I size={size} sw={1.6}><path d="M6 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const TerminalIcon = ({ size = 14 }) => (
  <I size={size}><rect x="1.5" y="2.5" width="13" height="11" rx="2" /><path d="M5 6l2.5 2L5 10M9 10.5h2.5" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const FileIcon = ({ size = 14 }) => (
  <I size={size}><path d="M4 1.5h5.5L12.5 4.5V14.5H4z" strokeLinejoin="round" /><path d="M9.5 1.5v3h3" strokeLinejoin="round" /></I>
);
export const EditIcon = ({ size = 14 }) => (
  <I size={size}><path d="M11.5 2.5l2 2L5 13H3v-2z" strokeLinejoin="round" /></I>
);
export const CheckIcon = ({ size = 14 }) => (
  <I size={size} sw={2}><path d="M3 8.5l3.5 3.5L13 4.5" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const XIcon = ({ size = 14 }) => (
  <I size={size} sw={1.6}><path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" /></I>
);
export const ClockIcon = ({ size = 14 }) => (
  <I size={size}><circle cx="8" cy="8" r="6" /><path d="M8 4.5V8l2.5 1.5" strokeLinecap="round" /></I>
);
export const GitIcon = ({ size = 14 }) => (
  <I size={size}><circle cx="4.5" cy="4" r="1.8" /><circle cx="4.5" cy="12" r="1.8" /><circle cx="11.5" cy="8" r="1.8" /><path d="M4.5 5.8v4.4M6 4h4.2a1.5 1.5 0 0 1 0 3H7" strokeLinecap="round" /></I>
);
export const CpuIcon = ({ size = 14 }) => (
  <I size={size}><rect x="4" y="4" width="8" height="8" rx="1.5" /><path d="M6.5 1.5v2M9.5 1.5v2M6.5 12.5v2M9.5 12.5v2M1.5 6.5h2M1.5 9.5h2M12.5 6.5h2M12.5 9.5h2" strokeLinecap="round" /></I>
);
export const PaletteIcon = ({ size = 14 }) => (
  <I size={size}><circle cx="8" cy="8" r="6" /><circle cx="6" cy="6.5" r="1" fill="currentColor" stroke="none" /><circle cx="10" cy="6" r="1" fill="currentColor" stroke="none" /><circle cx="6.5" cy="10" r="1" fill="currentColor" stroke="none" /></I>
);
export const PlugIcon = ({ size = 14 }) => (
  <I size={size}><path d="M6 2v4M10 2v4M4 6h8v3a4 4 0 0 1-8 0zM8 13v1.5" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const FolderIcon = ({ size = 14 }) => (
  <I size={size}><path d="M1.5 4.5a1 1 0 0 1 1-1h3l1.5 2h5.5a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1z" strokeLinejoin="round" /></I>
);
export const GlobeIcon = ({ size = 14 }) => (
  <I size={size}><circle cx="8" cy="8" r="6" /><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12" /></I>
);
export const TrashIcon = ({ size = 14 }) => (
  <I size={size}><path d="M2.5 4h11M6.5 2.5h3M4 4l1 10h6l1-10M6.5 7v4M9.5 7v4" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const PlayIcon = ({ size = 14 }) => (
  <I size={size} fill><path d="M4.5 2.8v10.4c0 .6.7 1 1.2.7l8-5.2c.5-.3.5-1 0-1.3l-8-5.2c-.5-.4-1.2 0-1.2.6z" /></I>
);
export const PauseIcon = ({ size = 14 }) => (
  <I size={size} fill><rect x="4" y="3" width="3" height="10" rx="1" /><rect x="9" y="3" width="3" height="10" rx="1" /></I>
);
export const DiffIcon = ({ size = 14 }) => (
  <I size={size}><rect x="1.5" y="2.5" width="13" height="11" rx="2" /><path d="M5 6.5h3M5 9.5h5M5 12h2" strokeLinecap="round" /></I>
);
export const HistoryIcon = ({ size = 14 }) => (
  <I size={size}><path d="M2.5 8a5.5 5.5 0 1 1 1.6 3.9M2.5 8V4.5M2.5 8h3.5" strokeLinecap="round" strokeLinejoin="round" /><path d="M8 5.5V8l1.8 1.2" strokeLinecap="round" /></I>
);
export const CommandIcon = ({ size = 14 }) => (
  <I size={size}><path d="M5.5 5.5A2.5 2.5 0 1 1 8 8M10.5 10.5a2.5 2.5 0 1 1-2.5-2.5M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3" strokeLinecap="round" /></I>
);
export const ChatIcon = ({ size = 16 }) => (
  <I size={size}><circle cx="8" cy="8" r="5.5" /><path d="M8 5.5v.01M5.8 8h.01M10.2 8h.01" strokeLinecap="round" strokeWidth={2} /></I>
);
export const SidebarIcon = ({ size = 16 }) => (
  <I size={size}><rect x="1.5" y="2.5" width="13" height="11" rx="2" /><path d="M6 2.5v11" /></I>
);
export const BackIcon = ({ size = 16 }) => (
  <I size={size} sw={1.6}><path d="M10 3 5 8l5 5" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const ForwardIcon = ({ size = 16 }) => (
  <I size={size} sw={1.6}><path d="M6 3l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" /></I>
);
export const MoreIcon = ({ size = 16 }) => (
  <I size={size}><circle cx="8" cy="3.5" r="1.3" fill="currentColor" stroke="none" /><circle cx="8" cy="8" r="1.3" fill="currentColor" stroke="none" /><circle cx="8" cy="12.5" r="1.3" fill="currentColor" stroke="none" /></I>
);
export const PanelIcon = ({ size = 16 }) => (
  <I size={size}><rect x="1.5" y="2.5" width="13" height="11" rx="2" /><path d="M10 2.5v11" /></I>
);
export const StopIcon = ({ size = 16 }) => (
  <I size={size}><rect x="4" y="4" width="8" height="8" rx="1.5" fill="currentColor" stroke="none" /></I>
);
export const BellIcon = ({ size = 16 }) => (
  <I size={size}><path d="M8 2.5a4 4 0 0 0-4 4v2.5L2.8 10.5h10.4L12 9V6.5a4 4 0 0 0-4-4Z" /><path d="M6.8 13a1.3 1.3 0 0 0 2.4 0" /></I>
);
export const ExploreIcon = ({ size = 16 }) => (
  <I size={size}><circle cx="4" cy="4" r="1.2" fill="currentColor" stroke="none" /><circle cx="12" cy="4" r="1.2" fill="currentColor" stroke="none" /><circle cx="4" cy="12" r="1.2" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" /></I>
);
export const HelpIcon = ({ size = 16 }) => (
  <I size={size}><circle cx="8" cy="8" r="6" /><path d="M6.2 6.2A1.9 1.9 0 0 1 8 4.8c1 0 1.9.7 1.9 1.7 0 1.2-1.4 1.4-1.9 2.3" strokeLinecap="round" /><path d="M8 11.5v.01" strokeLinecap="round" strokeWidth={2} /></I>
);
export const MicIcon = ({ size = 16 }) => (
  <I size={size}><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M4 7.5a4 4 0 0 0 8 0M8 11.5V14" strokeLinecap="round" /></I>
);
export const MonitorIcon = ({ size = 14 }) => (
  <I size={size}><rect x="2" y="3" width="12" height="8" rx="1.5" /><path d="M6 13.5h4" strokeLinecap="round" /></I>
);
export const CloudIcon = ({ size = 40 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.2}>
    <path d="M17.5 18a4.5 4.5 0 0 0 .4-8.98A6 6 0 0 0 6.2 10.5 3.8 3.8 0 0 0 7 18h10.5Z" strokeLinejoin="round" />
    <path d="M9.5 12.5h.01M12 12.5h.01M14.5 12.5h.01" strokeLinecap="round" strokeWidth={2} />
  </svg>
);
export const ZapIcon = ({ size = 13 }) => (
  <I size={size}><path d="M9 1.5 3.5 9H7l-1 5.5L11.5 7H8l1-5.5Z" strokeLinejoin="round" /></I>
);
export const GoalIcon = ({ size = 14 }) => (
  <I size={size}><circle cx="8" cy="8" r="5.5" /><circle cx="8" cy="8" r="2.5" /></I>
);
export const SitesIcon = ({ size = 16 }) => (
  <I size={size}><rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /><rect x="9" y="9" width="5" height="5" rx="1" /></I>
);
export const TaskIcon = ({ size = 16 }) => (
  <I size={size}><path d="M3 5.5h9M3 5.5v7a1.5 1.5 0 0 0 1.5 1.5h7A1.5 1.5 0 0 0 13 12.5v-7" /><path d="M3 5.5 4.5 4h9L15 5.5" /></I>
);
export const WandIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth={1.6}><path d="M6 21 21 6l-3-3L3 18l3 3Z" strokeLinejoin="round" /><path d="M14 5l3 3" strokeLinecap="round" /></svg>
);
export const BookIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth={1.6}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5Z" strokeLinejoin="round" /><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20" /></svg>
);
export const ListIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth={1.6}><path d="M8 6h13M8 12h13M8 18h13" strokeLinecap="round" /><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" strokeLinecap="round" strokeWidth={2.5} /></svg>
);
export const ClockColorIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#f97316" strokeWidth={1.6}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" strokeLinecap="round" /></svg>
);
export const DocIcon = ({ size = 14 }) => (
  <I size={size}><path d="M4 2.5h5.5L13 6v11.5H4V2.5Z" strokeLinejoin="round" /><path d="M9.5 2.5V6H13" /></I>
);
