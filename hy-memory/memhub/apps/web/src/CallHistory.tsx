import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { getConversation } from "./api";
import {
  CALL_HOSTS,
  CALL_TOOLS,
  type CallEvent,
  type CallHistoryPage,
  callDeliveryLabel,
  callDetailHeadline,
  callReturnDeliveryLabel,
  callRowDetail,
  callRowHeadline,
  clearAllCallEvents,
  clearCallEvents,
  getCallHistory,
  getCallReferences,
  type ResolvedCallReference,
} from "./call-history-client";
import { clockStamp } from "./clock-stamp";
import { R6Button } from "./R6Controls";
import { traceUiAction } from "./ui-trace";
import { isDefiniteRefusal } from "./write-outcome";
import "./call-history.css";

const PAGE_SIZE = 20;
const stateLabels: Record<CallEvent["state"], string> = {
  grounded: "查询成功",
  empty: "查询成功，没有找到相关记忆",
  partial: "查询成功，部分内容还在整理中",
  timed_out: "查询超时，没有提供记忆",
  unavailable: "One Memory 暂时不可用",
  denied: "当前未授权查询",
};

function toolName(tool: CallEvent["tool"]) {
  return CALL_TOOLS[tool];
}

function sourceLabel(id: string | null) {
  return id === null ? "未记录" : (CALL_HOSTS[id] ?? id);
}

function CallReferences({
  event,
  onOpenMemory,
  onOpenEvidence,
}: {
  event: CallEvent;
  onOpenMemory?(id: string): void;
  onOpenEvidence?(id: string): void;
}) {
  const [result, setResult] = useState<{
    event: CallEvent;
    items: ResolvedCallReference[];
  } | null>(null);
  const [failure, setFailure] = useState<CallEvent | null>(null);
  const [transcript, setTranscript] = useState<{
    id: string;
    status: "loading" | "ready" | "failed";
    messages: { evidence_id: string; verbatim: string }[];
  } | null>(null);
  useEffect(() => {
    let stopped = false;
    setResult(null);
    setFailure(null);
    setTranscript(null);
    if (event.references.length) {
      void getCallReferences(event)
        .then((items) => {
          if (!stopped) setResult({ event, items });
        })
        .catch(() => {
          if (!stopped) setFailure(event);
        });
    }
    return () => {
      stopped = true;
    };
  }, [event]);
  const resolved = result?.event === event ? result.items : null;
  const failed = failure === event;
  const loading = event.references.length > 0 && !resolved && !failed;
  const references = new Map(
    event.references.map((reference, index) => [
      JSON.stringify([
        reference.kind,
        reference.id,
        reference.revision,
        reference.source_id,
      ]),
      { reference, current: resolved?.[index] },
    ]),
  );
  return (
    <section
      className="call-history-references"
      aria-label="相关内容"
      aria-busy={loading}
    >
      <h3>相关内容</h3>
      {loading && <p role="status">正在读取相关内容</p>}
      {failed && <p role="alert">相关内容暂时无法读取，请刷新重试。</p>}
      {event.references.length ? (
        <ul>
          {Array.from(references, ([key, { reference, current }]) => (
            <li key={key}>
              <div>
                <h4>
                  {reference.kind === "raw" ? "原文" : "记忆"} ·{" "}
                  {current?.available && current.reason === null
                    ? current.title
                    : current?.reason === "changed"
                      ? "版本已变更"
                      : loading
                        ? "待核对"
                        : "不可用"}
                </h4>
                {reference.source_id && (
                  <p>{sourceLabel(reference.source_id)}</p>
                )}
              </div>
              {current?.available && current.reason === null && (
                <R6Button
                  variant="quiet"
                  onClick={() => {
                    if (reference.kind === "memory") {
                      onOpenMemory?.(reference.id);
                      return;
                    }
                    onOpenEvidence?.(reference.id);
                    setTranscript({
                      id: reference.id,
                      status: "loading",
                      messages: [],
                    });
                    void getConversation(reference.id)
                      .then((value) => {
                        setTranscript({
                          id: reference.id,
                          status: "ready",
                          messages: value.messages.map((message) => ({
                            evidence_id: message.evidence_id,
                            verbatim: message.verbatim,
                          })),
                        });
                      })
                      .catch(() => {
                        setTranscript({
                          id: reference.id,
                          status: "failed",
                          messages: [],
                        });
                      });
                  }}
                >
                  {reference.kind === "raw" ? "查看原文" : "查看记忆"}
                </R6Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p>没有找到相关内容</p>
      )}
      {transcript && (
        <aside
          aria-label="原文正文"
          aria-busy={transcript.status === "loading"}
        >
          {transcript.status === "loading" && <p role="status">正在读取原文</p>}
          {transcript.status === "failed" && (
            <p role="alert">原文已不可用或版本已变更。</p>
          )}
          {transcript.status === "ready" &&
            transcript.messages.map((message) => (
              <p key={message.evidence_id}>{message.verbatim}</p>
            ))}
        </aside>
      )}
    </section>
  );
}

function shortTime(value: string) {
  return clockStamp(value);
}

function ClearConfirmation({
  title,
  description,
  confirmLabel,
  pending,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  pending: boolean;
  onCancel(): void;
  onConfirm(): void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current?.showModal();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="call-history-confirm"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) onCancel();
      }}
    >
      <h2 id={titleId}>{title}</h2>
      <p id={descriptionId}>{description}</p>
      <div className="call-history-actions">
        <R6Button disabled={pending} onClick={onCancel}>
          取消
        </R6Button>
        <R6Button variant="primary" pending={pending} onClick={onConfirm}>
          {confirmLabel}
        </R6Button>
      </div>
    </dialog>
  );
}

export function CallHistory({
  onBack,
  onOpenMemory,
  onOpenEvidence,
}: {
  onBack(): void;
  onOpenMemory?(id: string): void;
  onOpenEvidence?(id: string): void;
}) {
  const [request, setRequest] = useState({
    hostId: "",
    offset: 0,
    revision: 0,
  });
  const [result, setResult] = useState<{
    request: typeof request;
    page: CallHistoryPage;
  } | null>(null);
  const [failure, setFailure] = useState<typeof request | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<
    { kind: "page"; ids: string[] } | { kind: "all" } | null
  >(null);
  const [clearing, setClearing] = useState(false);
  const [clearNotice, setClearNotice] = useState("");
  const mounted = useRef(false);
  const clearFlight = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const previousSelection = useRef<string | null>(null);
  const titleId = useId();
  const filterId = useId();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    setResult(null);
    setFailure(null);
    void getCallHistory({
      limit: PAGE_SIZE,
      offset: request.offset,
      ...(request.hostId ? { hostId: request.hostId } : {}),
    })
      .then((page) => {
        if (stopped) return;
        setResult({ request, page });
      })
      .catch(() => {
        if (!stopped) setFailure(request);
      });
    return () => {
      stopped = true;
    };
  }, [request]);

  useEffect(() => {
    if (selectedId !== null) heading.current?.focus();
    else if (previousSelection.current !== null) {
      const row = Array.from(
        list.current?.querySelectorAll<HTMLButtonElement>("[data-event-id]") ??
          [],
      ).find((button) => button.dataset.eventId === previousSelection.current);
      (row ?? heading.current)?.focus();
    }
    previousSelection.current = selectedId;
  }, [selectedId]);

  const page = result?.request === request && !clearing ? result.page : null;
  const failed = failure === request;
  const loading = !page && !failed && !clearing;
  const events = page?.available ? page.items : [];
  const selected =
    selectedId === null
      ? null
      : events.find((item) => item.event_id === selectedId);
  const returnedFrom =
    selected?.references.find((item) => item.source_id)?.source_id ?? null;
  const refresh = () =>
    setRequest((current) => ({ ...current, revision: current.revision + 1 }));

  async function confirmClear() {
    if (!confirmation || clearFlight.current) return;
    const clearingAll = confirmation.kind === "all";
    clearFlight.current = true;
    setClearing(true);
    setClearNotice("");
    const trace = traceUiAction("calls", "confirm");
    try {
      if (clearingAll) await clearAllCallEvents(trace.traceId);
      else await clearCallEvents([...confirmation.ids], trace.traceId);
      trace.done("succeeded");
      if (!mounted.current) return;
      setClearNotice(clearingAll ? "已清空全部记录。" : "已清除所选记录。");
    } catch (reason) {
      // A 4xx (e.g. `409 call_history_disabled`) is Core answering and
      // refusing: nothing was deleted, so it is a definite failure, not an
      // unconfirmed one. Everything else (timeout/5xx/transport) may or may
      // not have landed and stays `unknown` with the no-auto-retry notice.
      const refused = isDefiniteRefusal(reason);
      trace.done(refused ? "failed" : "unknown", {
        reason: refused
          ? clearingAll
            ? "clear_all_failed"
            : "clear_selected_failed"
          : clearingAll
            ? "clear_all_unconfirmed"
            : "clear_selected_unconfirmed",
      });
      if (!mounted.current) return;
      setClearNotice(
        refused
          ? clearingAll
            ? "未能清空使用记录，当前记录保持不变。请核对后重试。"
            : "未能清除所选记录，当前记录保持不变。请核对后重试。"
          : "清除结果未确认，请核对重新读取的记录。未自动重试清除。",
      );
    } finally {
      clearFlight.current = false;
      if (mounted.current) {
        setClearing(false);
        setConfirmation(null);
        setSelectedId(null);
        setRequest((current) => ({
          ...current,
          offset: clearingAll ? 0 : current.offset,
          revision: current.revision + 1,
        }));
      }
    }
  }

  return (
    <section className="call-history" aria-labelledby={titleId}>
      <header className="call-history-heading">
        <h1 id={titleId} ref={heading} tabIndex={-1}>
          {selectedId === null ? "使用记录" : "这次查记忆"}
        </h1>
        <R6Button
          className="call-history-back"
          disabled={clearing}
          onClick={selectedId === null ? onBack : () => setSelectedId(null)}
        >
          <ArrowLeft size={16} aria-hidden="true" />
          {selectedId === null ? "返回应用" : "返回记录"}
        </R6Button>
      </header>
      <div
        className={`call-history-toolbar${selectedId !== null ? " call-history-detail-toolbar" : ""}`}
      >
        {selectedId === null ? (
          <div className="call-history-filter">
            <label className="call-history-sr-only" htmlFor={filterId}>
              按应用筛选
            </label>
            <select
              id={filterId}
              value={request.hostId}
              disabled={clearing}
              onChange={(event) => {
                setSelectedId(null);
                setRequest((current) => ({
                  hostId: event.target.value,
                  offset: 0,
                  revision: current.revision + 1,
                }));
              }}
            >
              <option value="">全部应用</option>
              {Object.entries(CALL_HOSTS).map(([host, label]) => (
                <option key={host} value={host}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span />
        )}
        <div className="call-history-actions">
          {selectedId === null && <span>最近记录</span>}
          <R6Button
            className="call-history-icon"
            variant="quiet"
            title="刷新记录"
            aria-label="刷新记录"
            disabled={clearing}
            onClick={refresh}
          >
            <RefreshCw size={18} aria-hidden="true" />
          </R6Button>
          {selectedId === null && (
            <>
              <R6Button
                className="call-history-icon"
                variant="quiet"
                title="清除本页记录"
                aria-label="清除本页记录"
                disabled={!events.length || clearing}
                onClick={() =>
                  setConfirmation({
                    kind: "page",
                    ids: events.map((item) => item.event_id),
                  })
                }
              >
                <Trash2 size={18} aria-hidden="true" />
              </R6Button>
              <R6Button
                variant="quiet"
                title="清空全部记录"
                aria-label="清空全部记录"
                disabled={!page?.total || clearing}
                onClick={() => setConfirmation({ kind: "all" })}
              >
                清空全部
              </R6Button>
            </>
          )}
        </div>
      </div>
      {clearNotice && (
        <p className="call-history-notice" role="status">
          {clearNotice}
        </p>
      )}
      <div aria-busy={loading || clearing}>
        {loading && (
          <p className="call-history-state" role="status">
            正在读取使用记录
          </p>
        )}
        {clearing && (
          <p className="call-history-state" role="status">
            正在清除所选记录
          </p>
        )}
        {failed && (
          <p className="call-history-state" role="alert">
            记录读取失败，请刷新重试。
          </p>
        )}
        {page && !page.available && (
          <p className="call-history-state" role="alert">
            使用记录暂不可用，请稍后刷新。
          </p>
        )}
        {page?.recording_error && (
          <p className="call-history-notice" role="alert">
            有几次调用没被记下来，列表可能不全。
          </p>
        )}
        {page?.available &&
          (selectedId !== null ? (
            selected ? (
              <article className="call-history-detail" aria-label="调用详情">
                <h2>{`${sourceLabel(selected.host_id)} · ${shortTime(selected.occurred_at)}`}</h2>
                <p className="call-history-summary">
                  {callDetailHeadline(selected)}
                  {returnedFrom ? ` · 来源 ${sourceLabel(returnedFrom)}` : ""}
                </p>
                <p className="call-history-stage">
                  {stateLabels[selected.state]}
                </p>
                <p className="call-history-stage">
                  找到原文 {selected.raw_count} 段 · 记忆{" "}
                  {selected.memory_count} 条 · 用时{" "}
                  {(selected.elapsed_ms / 1000).toFixed(1)} 秒
                </p>
                {callDeliveryLabel(selected) && (
                  <p className="call-history-stage">
                    {callDeliveryLabel(selected)}
                  </p>
                )}
                <CallReferences
                  event={selected}
                  onOpenMemory={onOpenMemory}
                  onOpenEvidence={onOpenEvidence}
                />
                {callReturnDeliveryLabel(selected) && (
                  <p className="call-history-adoption">
                    {callReturnDeliveryLabel(selected)}
                  </p>
                )}
                <section
                  className="call-history-metadata"
                  aria-label="记录详情"
                >
                  <h3>记录详情</h3>
                  <p>
                    为保护隐私，这里不保存你问的原话和回答，只保存时间、来源和结果。
                  </p>
                  <dl>
                    <div>
                      <dt>准确时间</dt>
                      <dd>
                        <time dateTime={selected.occurred_at}>
                          {selected.occurred_at}
                        </time>
                      </dd>
                    </div>
                    <div>
                      <dt>应用</dt>
                      <dd>{sourceLabel(selected.host_id)}</dd>
                    </div>
                    <div>
                      <dt>类型</dt>
                      <dd>{toolName(selected.tool)}</dd>
                    </div>
                    <div>
                      <dt>结果状态</dt>
                      {/* The tool above is already humanized in this same
                        panel ("查记忆", never `om_recall`); printing the raw
                        `grounded`/`partial` enum here leaks the internal state
                        vocabulary the rest of the page translates. */}
                      <dd>{stateLabels[selected.state]}</dd>
                    </div>
                  </dl>
                </section>
              </article>
            ) : (
              <p className="call-history-state" role="status">
                这条记录已不在当前页，请返回记录查看。
              </p>
            )
          ) : (
            <>
              <ul
                ref={list}
                className="call-history-list"
                aria-label="调用记录"
              >
                {events.map((item) => (
                  <li key={item.event_id}>
                    <time dateTime={item.occurred_at} title={item.occurred_at}>
                      {shortTime(item.occurred_at)}
                    </time>
                    <div className="call-history-row-content">
                      <h2>
                        <button
                          type="button"
                          data-event-id={item.event_id}
                          onClick={() => setSelectedId(item.event_id)}
                        >
                          {callRowHeadline(item)}
                        </button>
                      </h2>
                      <p>{callRowDetail(item)}</p>
                    </div>
                  </li>
                ))}
              </ul>
              {!events.length && (
                <p className="call-history-state" role="status">
                  {request.offset ? "本页暂无记录" : "暂无使用记录"}
                </p>
              )}
              <nav className="call-history-pagination" aria-label="记录分页">
                <R6Button
                  aria-label="上一页"
                  title="上一页"
                  disabled={request.offset === 0}
                  onClick={() =>
                    setRequest((current) => ({
                      ...current,
                      offset: Math.max(0, current.offset - PAGE_SIZE),
                    }))
                  }
                >
                  <ChevronLeft size={18} aria-hidden="true" />
                </R6Button>
                <span>
                  {events.length
                    ? `${page.offset + 1}–${page.offset + events.length}`
                    : "0"}{" "}
                  / {page.total}
                </span>
                <R6Button
                  aria-label="下一页"
                  title="下一页"
                  disabled={
                    page.offset + PAGE_SIZE >= page.total || !events.length
                  }
                  onClick={() =>
                    setRequest((current) => ({
                      ...current,
                      offset: current.offset + PAGE_SIZE,
                    }))
                  }
                >
                  <ChevronRight size={18} aria-hidden="true" />
                </R6Button>
              </nav>
            </>
          ))}
      </div>
      {page?.available &&
        page.retention_days !== null &&
        page.max_events !== null && (
          <p className="call-history-policy">
            保留 {page.retention_days} 天，最多{" "}
            {new Intl.NumberFormat("zh-CN").format(page.max_events)} 条记录
          </p>
        )}
      {confirmation && (
        <ClearConfirmation
          title={
            confirmation.kind === "all"
              ? "清空全部使用记录？"
              : `清除本页 ${confirmation.ids.length} 条记录？`
          }
          description={
            confirmation.kind === "all"
              ? "将删除当前保留的全部调用记录，不限于本页或当前筛选。不删除原文或记忆，不更改授权与留存规则。此操作无法撤销。"
              : "仅清除这批调用记录，不删除原文或记忆，不更改授权与留存规则。此操作无法撤销。"
          }
          confirmLabel={
            confirmation.kind === "all" ? "确认清空全部" : "确认清除"
          }
          pending={clearing}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => void confirmClear()}
        />
      )}
    </section>
  );
}
