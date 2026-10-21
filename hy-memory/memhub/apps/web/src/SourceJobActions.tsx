import type { ImportJob } from "@one-memory/contracts";
import {
  ArrowLeft,
  LoaderCircle,
  Pause,
  Play,
  RefreshCw,
  X,
} from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMediaPreference } from "./use-media-preference";
import "./source-job-actions.css";

export interface SourceJobActionsProps {
  job: ImportJob;
  sourceLabel: string;
  syncEnabled: boolean;
  disabled?: boolean;
  snapshotStale?: boolean;
  onAction(
    jobId: string,
    action: "pause" | "resume" | "cancel",
  ): Promise<ImportJob>;
}

type Action = Parameters<SourceJobActionsProps["onAction"]>[1];
type Attempt = Readonly<{
  job: ImportJob;
  sourceLabel: string;
  syncEnabled: boolean;
  action: Action;
  scope: string;
  epoch: number;
  trigger: HTMLElement;
}>;
type Failure = { attempt: Attempt; message: string };
const changedMessage =
  "任务或来源范围已变化，请返回后重新确认。不会把本次操作用于变化后的任务。";
const pendingLabels: Record<Action, string> = {
  pause: "正在暂停，等待后台确认…",
  resume: "正在继续，等待后台确认…",
  cancel: "正在取消，等待后台确认…",
};
const retryLabels: Record<Action, string> = {
  pause: "核对并重试暂停",
  resume: "核对并重试继续",
  cancel: "核对并重试取消",
};
const statuses = new Set([
  "pending",
  "running",
  "paused",
  "interrupted",
  "failed",
  "completed",
  "cancelled",
]);
const learningSelector = ".om-spotlight, .om-scenario-cover";
const modalSelector = '[role="dialog"][aria-modal="true"]';

export function SourceJobActions(props: SourceJobActionsProps) {
  const { sourceLabel, syncEnabled, disabled = false } = props;
  const [receipt, setReceipt] = useState<ImportJob | null>(null);
  const [snapshot, setSnapshot] = useState<Attempt | null>(null);
  const [pending, setPending] = useState<Attempt | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const root = useRef<HTMLFieldSetElement>(null);
  const flight = useRef<Attempt | null>(null);
  const mounted = useRef(false);
  const currentJob = newerReceipt(props.job, receipt);
  const scope = scopeKey(currentJob, sourceLabel, syncEnabled);
  const identity = useRef({ scope, epoch: 0 });
  if (identity.current.scope !== scope) {
    identity.current = { scope, epoch: identity.current.epoch + 1 };
  }
  const current = useRef({ ...props, job: currentJob, scope });
  current.current = { ...props, job: currentJob, scope };
  const busy = pending !== null;
  const relevantPending = pending?.scope === scope ? pending : null;
  const relevantFailure = failure?.attempt.scope === scope ? failure : null;
  const action = primaryAction(currentJob);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function stillCurrent(attempt: Attempt) {
    return (
      mounted.current &&
      attempt.scope === current.current.scope &&
      attempt.epoch === identity.current.epoch
    );
  }

  async function submit(attempt: Attempt): Promise<boolean> {
    if (
      flight.current ||
      !stillCurrent(attempt) ||
      current.current.disabled ||
      !allowed(current.current.job, attempt.action)
    )
      return false;
    flight.current = attempt;
    setPending(attempt);
    setFailure(null);
    try {
      const result = await current.current.onAction(
        attempt.job.job_id,
        attempt.action,
      );
      if (!stillCurrent(attempt)) return false;
      if (!validReceipt(result, attempt.job))
        throw new Error("未收到此任务的有效回执。");
      const saved = { ...result };
      setReceipt(saved);
      if (!settledAction(attempt.action, saved))
        throw new Error("后台尚未确认此操作完成。");
      return true;
    } catch (reason) {
      if (stillCurrent(attempt))
        setFailure({
          attempt,
          message: `状态待核对。${
            reason instanceof Error && reason.message.trim()
              ? reason.message
              : "未能确认操作结果。"
          }`,
        });
      return false;
    } finally {
      flight.current = null;
      if (mounted.current) setPending(null);
    }
  }

  function begin(next: Action, trigger: HTMLElement) {
    if (
      disabled ||
      flight.current ||
      snapshot ||
      !allowed(currentJob, next) ||
      anotherBusinessDialog()
    )
      return;
    const attempt: Attempt = Object.freeze({
      job: Object.freeze({ ...currentJob }),
      sourceLabel,
      syncEnabled,
      action: next,
      scope,
      epoch: identity.current.epoch,
      trigger,
    });
    setFailure(null);
    if (next === "cancel") setSnapshot(attempt);
    else void submit(attempt);
  }

  return (
    <fieldset
      ref={root}
      className="source-job-actions"
      aria-label={`${sourceLabel} ${operationLabel(currentJob)}任务操作`}
      aria-busy={busy}
      tabIndex={-1}
      data-job-id={currentJob.job_id}
    >
      <p className="source-job-status" role="status" aria-live="polite">
        {!relevantPending && props.snapshotStale ? "最近回执：" : ""}
        {relevantPending
          ? pendingLabels[relevantPending.action]
          : statusLabel(currentJob)}
      </p>
      <div className="source-job-buttons">
        {action && (
          <button
            type="button"
            className="quiet source-job-icon"
            aria-label={action.label}
            title={action.label}
            disabled={disabled || busy || snapshot !== null}
            onClick={(event) => begin(action.action, event.currentTarget)}
          >
            {busy ? (
              <LoaderCircle size={16} aria-hidden="true" />
            ) : action.action === "pause" ? (
              <Pause size={16} aria-hidden="true" />
            ) : currentJob.status === "failed" ? (
              <RefreshCw size={16} aria-hidden="true" />
            ) : (
              <Play size={16} aria-hidden="true" />
            )}
          </button>
        )}
        {cancellable(currentJob) && (
          <button
            type="button"
            className="quiet source-job-icon"
            aria-label={`取消本次${operationLabel(currentJob)}`}
            title={`取消本次${operationLabel(currentJob)}`}
            disabled={disabled || busy || snapshot !== null}
            onClick={(event) => begin("cancel", event.currentTarget)}
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>
      {!snapshot && relevantFailure && (
        <div className="source-job-failure">
          <p className="source-job-error" role="alert">
            {relevantFailure.message}
          </p>
          {allowed(currentJob, relevantFailure.attempt.action) && (
            <button
              type="button"
              className="quiet source-job-retry"
              disabled={disabled || busy}
              onClick={() => void submit(relevantFailure.attempt)}
            >
              <RefreshCw size={16} aria-hidden="true" />
              {retryLabels[relevantFailure.attempt.action]}
            </button>
          )}
        </div>
      )}
      {snapshot && (
        <CancelJobSheet
          snapshot={snapshot}
          currentJob={currentJob}
          currentScope={scope}
          currentEpoch={identity.current.epoch}
          disabled={disabled}
          pending={pending === snapshot}
          error={failure?.attempt === snapshot ? failure.message : null}
          fallback={root}
          onConfirm={() => submit(snapshot)}
          onClose={() => {
            setSnapshot(null);
            setFailure(null);
          }}
        />
      )}
    </fieldset>
  );
}

function CancelJobSheet({
  snapshot,
  currentJob,
  currentScope,
  currentEpoch,
  disabled,
  pending,
  error,
  fallback,
  onConfirm,
  onClose,
}: {
  snapshot: Attempt;
  currentJob: ImportJob;
  currentScope: string;
  currentEpoch: number;
  disabled: boolean;
  pending: boolean;
  error: string | null;
  fallback: { current: HTMLElement | null };
  onConfirm(): Promise<boolean>;
  onClose(): void;
}) {
  const id = useId();
  const panel = useRef<HTMLElement>(null);
  const cover = useRef<HTMLDivElement>(null);
  const [stale, setStale] = useState(false);
  const [owned, setOwned] = useState(false);
  const [closing, setClosing] = useState(false);
  const reducedMotion = useMediaPreference("(prefers-reduced-motion: reduce)");
  const reducedTransparency = useMediaPreference(
    "(prefers-reduced-transparency: reduce)",
  );
  const invalid =
    currentScope !== snapshot.scope ||
    currentEpoch !== snapshot.epoch ||
    !cancellable(currentJob);
  const invalidated = useRef(false);
  const flight = useRef(false);
  const alive = useRef(false);
  const closingRef = useRef(false);
  const latest = useRef({
    disabled,
    pending,
    invalid,
    owned,
    onClose,
    reducedMotion,
  });
  latest.current = {
    disabled,
    pending,
    invalid,
    owned,
    onClose,
    reducedMotion,
  };

  useEffect(() => {
    if (invalid) {
      invalidated.current = true;
      setStale(true);
    }
  }, [invalid]);

  useEffect(() => {
    if (!closing) return;
    if (reducedMotion) {
      latest.current.onClose();
      return;
    }
    const timer = window.setTimeout(() => latest.current.onClose(), 160);
    return () => window.clearTimeout(timer);
  }, [closing, reducedMotion]);

  function exit() {
    if (closingRef.current) return;
    closingRef.current = true;
    if (latest.current.reducedMotion) latest.current.onClose();
    else setClosing(true);
  }

  function close() {
    if (flight.current || latest.current.pending) return;
    exit();
  }

  useLayoutEffect(() => {
    alive.current = true;
    const dialog = panel.current;
    const overlay = cover.current;
    if (!dialog || !overlay) return;
    let release: (() => void) | undefined;
    let focusGuard = false;
    const prior = new Map<
      HTMLElement,
      { inert: boolean; attribute: string | null }
    >();
    const controls = () =>
      Array.from(
        dialog.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
      );
    const focusInside = () => {
      if (focusGuard) return;
      focusGuard = true;
      (latest.current.pending || closingRef.current
        ? dialog
        : (controls()[0] ?? dialog)
      ).focus({ preventScroll: true });
      focusGuard = false;
    };
    const contain = (event: FocusEvent) => {
      if (event.target instanceof Node && !dialog.contains(event.target))
        focusInside();
    };
    const scroll = (event: WheelEvent | TouchEvent) => {
      if (event.target instanceof Node && !dialog.contains(event.target))
        event.preventDefault();
    };
    const inertBackground = () => {
      for (const child of document.body.children) {
        if (
          !(child instanceof HTMLElement) ||
          child === overlay ||
          prior.has(child)
        )
          continue;
        prior.set(child, {
          inert: !!child.inert,
          attribute: child.getAttribute("inert"),
        });
        child.inert = true;
        child.setAttribute("inert", "");
      }
    };
    const takeOwnership = () => {
      if (release) {
        inertBackground();
        return;
      }
      // Wait for any other modal owner to release its focus lease before
      // installing a second focus trap.
      if (
        Array.from(document.querySelectorAll(modalSelector)).some(
          (node) => node !== dialog && !node.closest("[hidden]"),
        )
      )
        return;
      overlay.inert = false;
      overlay.removeAttribute("inert");
      inertBackground();
      document.addEventListener("focusin", contain);
      overlay.addEventListener("wheel", scroll, { passive: false });
      overlay.addEventListener("touchmove", scroll, { passive: false });
      release = () => {
        document.removeEventListener("focusin", contain);
        overlay.removeEventListener("wheel", scroll);
        overlay.removeEventListener("touchmove", scroll);
        for (const [element, previous] of prior) {
          element.inert = previous.inert;
          if (previous.attribute === null) element.removeAttribute("inert");
          else element.setAttribute("inert", previous.attribute);
        }
      };
      setOwned(true);
      focusInside();
    };
    const observer = new MutationObserver(takeOwnership);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["role", "aria-modal", "hidden"],
    });
    takeOwnership();
    return () => {
      alive.current = false;
      observer.disconnect();
      release?.();
      // Wait until React removes the dialog and re-enables its original trigger.
      queueMicrotask(() => {
        if (alive.current) return;
        const candidate = focusable(snapshot.trigger)
          ? snapshot.trigger
          : fallback.current;
        const other = document.querySelector(modalSelector);
        if (focusable(candidate) && (!other || other.contains(candidate)))
          candidate.focus({ preventScroll: true });
      });
    };
  }, [snapshot, fallback]);

  useLayoutEffect(() => {
    if (!owned) return;
    if (pending || closing) panel.current?.focus({ preventScroll: true });
    else if (
      !panel.current?.contains(document.activeElement) ||
      document.activeElement?.matches(":disabled")
    ) {
      panel.current
        ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
        ?.focus({ preventScroll: true });
    }
  }, [pending, closing, owned]);

  async function confirm() {
    if (
      flight.current ||
      closingRef.current ||
      invalidated.current ||
      stale ||
      latest.current.invalid ||
      latest.current.disabled ||
      !latest.current.owned
    )
      return;
    flight.current = true;
    const accepted = await onConfirm();
    flight.current = false;
    if (alive.current && accepted) exit();
  }

  const blocked = disabled || pending || stale || invalid || closing || !owned;
  return createPortal(
    <div
      ref={cover}
      className="consent-backdrop source-job-backdrop"
      data-closing={closing}
      data-motion={reducedMotion ? "reduced" : "full"}
      data-reduced-transparency={reducedTransparency}
    >
      <section
        ref={panel}
        className="consent-sheet source-job-sheet"
        role="dialog"
        aria-modal="true"
        aria-busy={pending}
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-consequences`}
        tabIndex={-1}
        data-closing={closing}
        data-motion={reducedMotion ? "reduced" : "full"}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            close();
          }
          if (event.key !== "Tab") return;
          const buttons = panel.current?.querySelectorAll<HTMLButtonElement>(
            "button:not(:disabled)",
          );
          const first = buttons?.[0],
            last = buttons?.[buttons.length - 1];
          if (!first || pending || closing) {
            event.preventDefault();
            panel.current?.focus();
          } else if (
            event.shiftKey &&
            (document.activeElement === first ||
              document.activeElement === panel.current)
          ) {
            event.preventDefault();
            last?.focus();
          } else if (
            !event.shiftKey &&
            (document.activeElement === last ||
              document.activeElement === panel.current)
          ) {
            event.preventDefault();
            first.focus();
          }
          event.stopPropagation();
        }}
      >
        <header className="source-job-heading">
          <h2 id={`${id}-title`}>
            取消 {snapshot.sourceLabel} 的本次{operationLabel(snapshot.job)}？
          </h2>
          <button
            type="button"
            className="quiet source-job-icon"
            aria-label="关闭取消确认"
            title="关闭取消确认"
            disabled={pending || closing || !owned}
            onClick={close}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="source-job-sheet-body">
          <p id={`${id}-consequences`}>
            仅停止本次{operationLabel(snapshot.job)}
            。已保存的本机副本会保留，不会撤回来源读取授权，也不会修改或删除原文件。
          </p>
          <dl className="source-job-snapshot">
            <div>
              <dt>来源</dt>
              <dd>
                {snapshot.sourceLabel} <span>{snapshot.job.source_id}</span>
              </dd>
            </div>
            <div>
              <dt>任务</dt>
              <dd>
                <code>{snapshot.job.job_id}</code>
              </dd>
            </div>
            <div>
              <dt>{isSyncJob(snapshot.job) ? "本次新增" : "已保存"}</dt>
              <dd>{snapshot.job.stored.toLocaleString()} 条</dd>
            </div>
          </dl>
          {snapshot.syncEnabled && (
            <p className="source-job-sync-note">
              持续同步仍开启，未来新增对话仍可能触发新的同步任务。本次取消不会关闭持续同步。
            </p>
          )}
          {pending && <p role="status">{pendingLabels.cancel}</p>}
          {(stale || invalid || error) && (
            <p className="source-job-error" role="alert">
              {stale || invalid ? changedMessage : error}
            </p>
          )}
        </div>
        <footer className="consent-actions source-job-sheet-actions">
          <button
            type="button"
            className="secondary"
            disabled={pending || closing || !owned}
            onClick={close}
          >
            <ArrowLeft size={16} aria-hidden="true" />
            返回
          </button>
          <button
            type="button"
            className="source-job-cancel"
            disabled={blocked}
            onClick={() => void confirm()}
          >
            {pending ? (
              <LoaderCircle size={16} aria-hidden="true" />
            ) : error ? (
              <RefreshCw size={16} aria-hidden="true" />
            ) : (
              <X size={16} aria-hidden="true" />
            )}
            {error && !stale && !invalid ? retryLabels.cancel : "确认取消"}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

function jobIdentity(job: ImportJob): unknown[] {
  return [
    job.job_id,
    job.user_id,
    job.source_id,
    job.created_at,
    "operation" in job ? job.operation : null,
  ];
}

function scopeKey(job: ImportJob, sourceLabel: string, syncEnabled: boolean) {
  return JSON.stringify([...jobIdentity(job), sourceLabel, syncEnabled]);
}

function sameJob(left: ImportJob, right: ImportJob) {
  return (
    JSON.stringify(jobIdentity(left)) === JSON.stringify(jobIdentity(right))
  );
}

function newerReceipt(job: ImportJob, receipt: ImportJob | null) {
  if (!receipt || !sameJob(job, receipt)) return job;
  return Date.parse(job.updated_at) > Date.parse(receipt.updated_at)
    ? job
    : receipt;
}

function cancellable(job: ImportJob) {
  return (
    statuses.has(job.status) &&
    job.status !== "completed" &&
    job.status !== "cancelled"
  );
}

function primaryAction(
  job: ImportJob,
): { action: "pause" | "resume"; label: string } | null {
  if (["pending", "running"].includes(job.status))
    return { action: "pause", label: `暂停${operationLabel(job)}` };
  if (["paused", "interrupted"].includes(job.status))
    return { action: "resume", label: `继续${operationLabel(job)}` };
  if (job.status === "failed")
    return {
      action: "resume",
      label: isSyncJob(job) ? "重试新增同步" : "重试未完成部分",
    };
  return null;
}

function allowed(job: ImportJob, action: Action) {
  return action === "cancel"
    ? cancellable(job)
    : primaryAction(job)?.action === action;
}

export function validReceipt(
  result: ImportJob | undefined,
  expected: ImportJob,
): result is ImportJob {
  return (
    !!result &&
    sameJob(result, expected) &&
    statuses.has(result.status) &&
    Number.isSafeInteger(result.stored) &&
    result.stored >= 0 &&
    Number.isFinite(Date.parse(result.updated_at))
  );
}

export function settledAction(action: Action, result: ImportJob) {
  if (!cancellable(result)) return true;
  if (action === "resume") return true;
  return (
    action === "pause" && ["paused", "interrupted"].includes(result.status)
  );
}

function statusLabel(job: ImportJob) {
  if (isSyncJob(job)) {
    const names: Record<ImportJob["status"], string> = {
      pending: "等待检查新增",
      running: "正在检查新增",
      paused: "新增同步已暂停",
      interrupted: "新增同步已中断",
      failed: "新增同步失败",
      completed: "本次新增检查已完成",
      cancelled: "本次新增同步已取消",
    };
    return `${names[job.status] ?? "状态待核对"} · 本次新增 ${job.stored.toLocaleString()} 条`;
  }
  const names: Record<ImportJob["status"], string> = {
    pending: "等待导入",
    running: "正在导入",
    paused: "导入已暂停",
    interrupted: "导入已中断",
    failed: "导入失败",
    completed: "本次导入已完成",
    cancelled: "本次导入已取消",
  };
  return `${names[job.status] ?? "状态待核对"} · 已保存 ${job.stored.toLocaleString()} 条`;
}

function operationLabel(job: ImportJob) {
  return isSyncJob(job) ? "新增同步" : "导入";
}

function isSyncJob(job: ImportJob) {
  return job.operation === "sync";
}

function anotherBusinessDialog() {
  return Array.from(document.querySelectorAll(modalSelector)).some(
    (node) => !node.closest(`${learningSelector}, [hidden]`),
  );
}

function focusable(element: HTMLElement | null): element is HTMLElement {
  return (
    !!element &&
    element.isConnected &&
    !element.matches(":disabled") &&
    !element.closest("[inert], [hidden]")
  );
}
