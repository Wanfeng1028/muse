import { useEffect, useRef } from "react";

export function MemoryDeleteDialog({
  count,
  onAnswer,
}: {
  count: number;
  onAnswer(value: boolean): void;
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
        className="consent-sheet memory-delete-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="memory-delete-title"
        ref={panel}
        onKeyDown={(event) => {
          if (event.key === "Escape") onAnswer(false);
          if (event.key !== "Tab") return;
          const buttons =
            panel.current?.querySelectorAll<HTMLButtonElement>("button");
          const first = buttons?.[0],
            last = buttons?.[1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          }
          if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <p className="eyebrow">记忆管理</p>
        <h2 id="memory-delete-title">
          删除{count === 1 ? "这条" : `这 ${count} 条`}记忆？
        </h2>
        <div className="delete-impact">
          <h3>会删除</h3>
          <p>所选记忆，以及对应的搜索向量和图关系。</p>
          <h3>会保留</h3>
          <p>仍被其他记忆引用的原始证据。来源应用中的对话不会被修改。</p>
        </div>
        <p className="delete-alternative">
          只是内容不准确，可以取消后选择“纠正”。
        </p>
        <div className="consent-actions">
          <button
            type="button"
            className="secondary"
            onClick={() => onAnswer(false)}
          >
            取消
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => onAnswer(true)}
          >
            确认删除
          </button>
        </div>
      </section>
    </div>
  );
}
