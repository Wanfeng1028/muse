import type { ReactNode } from "react";

export function DesktopFrame({ children }: { children: ReactNode }) {
  if (!window.oneMemory) return children;
  return (
    <div className="desktop-frame">
      <div className="window-drag-region" aria-hidden="true" />
      <div className="desktop-frame-content">{children}</div>
    </div>
  );
}
