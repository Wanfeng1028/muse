import { useEffect, useRef } from "react";

export function SourceDisconnectDialog({
  name,
  onCancel,
  onConfirm,
}: {
  name: string;
  onCancel(): void;
  onConfirm(): void;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, []);
  return (
    <div className="consent-backdrop">
      <section
        ref={panel}
        className="consent-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="disconnect-source-title"
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
          if (event.key !== "Tab") return;
          const controls = panel.current?.querySelectorAll("button");
          const first = controls?.[0],
            last = controls?.[1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <h2 id="disconnect-source-title">撤回 {name} 的授权？</h2>
        <p>
          停止同步与相关记忆的外部读取。已导入的原文和修改历史保留在本机，不修改来源应用中的对话。
        </p>
        <div className="consent-actions">
          <button type="button" className="secondary" onClick={onCancel}>
            取消
          </button>
          <button type="button" onClick={onConfirm}>
            撤回授权
          </button>
        </div>
      </section>
    </div>
  );
}
