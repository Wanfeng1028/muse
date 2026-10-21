import type {
  GraphWidthDecision,
  GraphWidthStatus,
} from "@one-memory/contracts";
import { useEffect, useRef, useState } from "react";
import { decideGraphWidth, getGraphWidth } from "./api";
import { traceUiAction } from "./ui-trace";
import { isDefiniteRefusal, writeTraceStatus } from "./write-outcome";

/** Ask before the widths cost anything, and default to changing nothing.
 *
 * Without this the app installs, opens, looks healthy, and quietly fails
 * every extraction with `graph_width_mismatch:...` — the failure is in the
 * task record and nowhere the user looks. The three options are the ones the
 * core already implements; the only judgement encoded here is which one is
 * preselected, and that has to be the one that touches nothing.
 */
export function GraphWidthPrompt({
  onResolved = () => undefined,
}: {
  onResolved?(): void;
}) {
  const [status, setStatus] = useState<GraphWidthStatus | null>(null);
  const [decision, setDecision] = useState<GraphWidthDecision>("keep_existing");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settled, setSettled] = useState(false);
  const [exportedPath, setExportedPath] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getGraphWidth();
        if (!cancelled) setStatus(result);
      } catch {
        // A core that is not up yet is not a mismatch. Staying silent is the
        // right answer here; extraction has not started either.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (settled || !status?.mismatch) return;
    const element = panel.current;
    if (!element) return;
    const before = document.activeElement;
    element.querySelector<HTMLInputElement>("input:checked")?.focus();
    return () => {
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    };
  }, [settled, status]);

  if (settled || !status?.mismatch) return null;
  const { stored_width, expected_width } = status.mismatch;

  async function confirm() {
    setBusy(true);
    setError(null);
    const trace = traceUiAction("memory", "confirm");
    try {
      const receipt = await decideGraphWidth(decision, trace.traceId);
      if (receipt.exported_path) setExportedPath(receipt.exported_path);
      // The decision reached Core: that request succeeded whether or not the
      // graph still reports a mismatch.
      trace.done("succeeded");
      // Exporting is preparation, not a decision: the core still reports the
      // mismatch, and closing here would strand the user one step short of
      // the choice they exported in order to make.
      if (receipt.mismatch) return;
      setSettled(true);
      onResolved();
    } catch (reason) {
      const refused = isDefiniteRefusal(reason);
      trace.done(writeTraceStatus(reason), {
        reason: refused
          ? "graph_width_decision_failed"
          : "graph_width_decision_result_unknown",
      });
      // A refusal is a fact; a timeout is not. Only the refusal branch may
      // present the raw code as "failed", and the unknown branch says so.
      setError(
        refused
          ? reason instanceof Error
            ? reason.message
            : String(reason)
          : "宽度选择尚未确认，现有记忆库未被改动。请重试。",
      );
    } finally {
      setBusy(false);
    }
  }

  const choices: { value: GraphWidthDecision; label: string }[] = [
    {
      value: "keep_existing",
      label: `保留现有记忆库（默认）：继续用原来的 embedding 配置，${status.memory_count} 条记忆和关系图都不动`,
    },
    {
      value: "rebuild_with_new",
      label: `改用内置模型：现有关系图会被归档（不删除），${status.memory_count} 条记忆的关系需要重新建一遍`,
    },
    {
      value: "export_first",
      label: "先导出再决定：现在什么都不动，导出之后再回来选",
    },
  ];

  return (
    <div
      className="graph-width-prompt"
      role="dialog"
      aria-modal="true"
      aria-label="现有记忆库和内置模型对不上"
      ref={panel}
      onKeyDown={(event) => {
        if (event.key !== "Tab" || !panel.current) return;
        const controls = [
          ...panel.current.querySelectorAll<HTMLElement>(
            "button:not(:disabled), input:not(:disabled)",
          ),
        ];
        const first = controls[0];
        const last = controls.at(-1);
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
    >
      <h2>现有记忆库和内置模型对不上</h2>
      <p>
        {`你现在的记忆库按 ${stored_width} 维建的，内置模型出的是 ${expected_width} 维。两者接不上，不选一个的话抽取会一直失败。`}
      </p>
      <ul>
        {choices.map((choice) => (
          <li key={choice.value}>
            <label>
              <input
                type="radio"
                name="graph-width-decision"
                value={choice.value}
                aria-label={choice.label}
                checked={decision === choice.value}
                onChange={() => setDecision(choice.value)}
              />
              <span>{choice.label}</span>
            </label>
          </li>
        ))}
      </ul>
      {exportedPath ? (
        <p className="notice">
          已导出到 <code>{exportedPath}</code>。原库没有动，现在可以再选一次。
        </p>
      ) : null}
      {error ? <p className="notice">{error}</p> : null}
      <button type="button" disabled={busy} onClick={() => void confirm()}>
        就这么办
      </button>
    </div>
  );
}
