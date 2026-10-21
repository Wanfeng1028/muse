import { Download, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type {
  ApplySyncHookInput,
  RecallHostStatus,
  SyncHookPreview,
  SyncHookStatus,
} from "./global";
import "./sync-hook-control.css";

export type { SyncHookPreview, SyncHookStatus } from "./global";

interface SyncHookBridge {
  getSyncHookStatus(hostId: string): Promise<SyncHookStatus>;
  previewSyncHook(
    hostId: string,
    operation: "install" | "uninstall",
  ): Promise<SyncHookPreview>;
  applySyncHook(
    hostId: string,
    input: ApplySyncHookInput,
  ): Promise<SyncHookStatus>;
}
interface Snapshot {
  host: RecallHostStatus;
  key: string;
  operation: "install" | "uninstall";
  updating: boolean;
  bridge: SyncHookBridge;
  trigger: HTMLElement;
}
const statusNames: Record<SyncHookStatus["state"], string> = {
  unsupported: "此应用暂不支持同步 Hook",
  "connection-required": "需要重新关联 MCP 连接",
  "not-installed": "同步 Hook 未安装",
  installed: "同步 Hook 已安装",
  modified: "同步 Hook 文件已变化",
  unavailable: "同步 Hook 状态暂不可用",
};
const changedMessage =
  "连接已变化，请关闭后重新打开核对。本次确认不会用于变化后的连接。";
const focusSelector =
  'button:not(:disabled), input:not(:disabled), [tabindex="0"]';

function hookBridge(): SyncHookBridge | null {
  const api = window.oneMemory as
    | (Window["oneMemory"] & Partial<SyncHookBridge>)
    | undefined;
  return api &&
    typeof api.getSyncHookStatus === "function" &&
    typeof api.previewSyncHook === "function" &&
    typeof api.applySyncHook === "function"
    ? (api as SyncHookBridge)
    : null;
}
function hostKey(host: RecallHostStatus): string {
  const permission = host.permission;
  return JSON.stringify([
    host.hostId,
    host.present,
    host.installed,
    permission?.state,
    permission?.reason,
    permission?.receipt?.installationId,
    permission?.receipt?.revision,
    permission?.receipt?.status,
  ]);
}
function checkedStatus(value: SyncHookStatus, hostId: string): SyncHookStatus {
  if (
    !value ||
    value.hostId !== hostId ||
    !Object.hasOwn(statusNames, value.state) ||
    (value.reason !== null && typeof value.reason !== "string")
  )
    throw new Error("invalid_hook_status");
  return { hostId, state: value.state, reason: value.reason };
}
function checkedPreview(
  value: SyncHookPreview,
  snapshot: Snapshot,
): SyncHookPreview {
  const receipt = snapshot.host.permission?.receipt;
  if (
    !value ||
    value.hostId !== snapshot.host.hostId ||
    value.operation !== snapshot.operation ||
    typeof value.installationId !== "string" ||
    !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(
      value.installationId,
    ) ||
    !Number.isSafeInteger(value.revision) ||
    value.revision < 1 ||
    (receipt &&
      (receipt.installationId !== value.installationId ||
        receipt.revision !== value.revision)) ||
    typeof value.fingerprint !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.fingerprint) ||
    !Array.isArray(value.files) ||
    value.files.length > 64 ||
    value.files.some(
      (file) =>
        !file ||
        typeof file.path !== "string" ||
        file.path.length > 4096 ||
        !/^(?:\/|[A-Za-z]:[\\/])/.test(file.path) ||
        /\p{Cc}/u.test(file.path) ||
        !["create", "update", "remove"].includes(file.action) ||
        !["host", "one-memory"].includes(file.owner),
    ) ||
    new Set(value.files.map((file) => file.path)).size !== value.files.length
  )
    throw new Error("invalid_hook_preview");
  return {
    hostId: value.hostId,
    operation: value.operation,
    installationId: value.installationId,
    revision: value.revision,
    fingerprint: value.fingerprint,
    files: value.files.map((file) => ({
      path: file.path,
      action: file.action,
      owner: file.owner,
    })),
  };
}

export function SyncHookControl({
  host,
  disabled = false,
}: {
  host: RecallHostStatus;
  disabled?: boolean;
}) {
  const bridge = hookBridge();
  const visible =
    !!bridge && host.hostId === "claude-code" && host.present && host.installed;
  const key = hostKey(host);
  const currentKey = useRef(key);
  currentKey.current = key;
  const generation = useRef(0);
  const control = useRef<HTMLElement>(null);
  const [local, setLocal] = useState<{
    key: string;
    status: SyncHookStatus | null;
    loading: boolean;
    error: boolean;
  } | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const current = local?.key === key ? local : null;

  useEffect(() => {
    if (!visible || !bridge) return;
    const token = ++generation.current;
    setLocal({ key, status: null, loading: true, error: false });
    void bridge
      .getSyncHookStatus(host.hostId)
      .then((value) => {
        const status = checkedStatus(value, host.hostId);
        if (token === generation.current && currentKey.current === key)
          setLocal({ key, status, loading: false, error: false });
      })
      .catch(() => {
        if (token === generation.current && currentKey.current === key)
          setLocal({ key, status: null, loading: false, error: true });
      });
    return () => {
      generation.current++;
    };
  }, [key, visible, bridge, host.hostId]);

  async function refresh() {
    if (!bridge || disabled || snapshot || current?.loading) return;
    const token = ++generation.current;
    setLocal({
      key,
      status: current?.status ?? null,
      loading: true,
      error: false,
    });
    try {
      const status = checkedStatus(
        await bridge.getSyncHookStatus(host.hostId),
        host.hostId,
      );
      if (token === generation.current && currentKey.current === key)
        setLocal({ key, status, loading: false, error: false });
    } catch {
      if (token === generation.current && currentKey.current === key)
        setLocal({
          key,
          status: current?.status ?? null,
          loading: false,
          error: true,
        });
    }
  }
  function open(operation: Snapshot["operation"], trigger: HTMLElement) {
    if (
      !bridge ||
      !visible ||
      disabled ||
      snapshot ||
      current?.loading ||
      current?.error ||
      document.querySelector('[role="dialog"][aria-modal="true"]')
    )
      return;
    setSnapshot({
      host: {
        ...host,
        permission: host.permission
          ? structuredClone(host.permission)
          : undefined,
      },
      key,
      operation,
      updating:
        current?.status?.state === "installed" ||
        current?.status?.state === "modified",
      bridge,
      trigger,
    });
  }
  const installed =
    current?.status?.state === "installed" ||
    current?.status?.state === "modified";
  const canInstall =
    current?.status &&
    !current.error &&
    current.status.reason === null &&
    ["not-installed", "installed", "modified"].includes(current.status.state) &&
    host.permission?.state !== "revoked" &&
    host.permission?.state !== "relink-required";

  if (!visible && !snapshot) return null;
  return (
    <section
      ref={control}
      className="sync-hook-control"
      aria-label={`${host.label} 同步 Hook`}
      tabIndex={-1}
    >
      {visible && (
        <>
          <p role="status" className="sync-hook-status">
            {current?.loading
              ? "正在读取同步 Hook 状态…"
              : current?.status
                ? statusNames[current.status.state]
                : "同步 Hook 状态待核对"}
          </p>
          <p className="sync-hook-note">
            插件只通知新对话；读取与持续同步仍由来源权限控制。
          </p>
          {installed && current?.status?.reason !== null && (
            <p className="sync-hook-note">
              MCP 连接需要核对；仍可移除已有同步 Hook。
            </p>
          )}
          <div className="sync-hook-actions">
            {canInstall && (
              <button
                type="button"
                className="secondary"
                disabled={disabled || !!snapshot || current?.loading}
                onClick={(event) => open("install", event.currentTarget)}
              >
                {installed ? (
                  <RefreshCw size={16} aria-hidden="true" />
                ) : (
                  <Download size={16} aria-hidden="true" />
                )}
                {installed ? "更新同步 Hook" : "安装同步 Hook"}
              </button>
            )}
            {installed && (
              <button
                type="button"
                className="quiet"
                disabled={
                  disabled || !!snapshot || current?.loading || current?.error
                }
                onClick={(event) => open("uninstall", event.currentTarget)}
              >
                <Trash2 size={16} aria-hidden="true" />
                卸载同步 Hook
              </button>
            )}
            <button
              type="button"
              className="quiet sync-hook-icon"
              title="刷新同步 Hook 状态"
              aria-label="刷新同步 Hook 状态"
              disabled={disabled || !!snapshot || current?.loading}
              onClick={() => void refresh()}
            >
              <RefreshCw size={16} aria-hidden="true" />
            </button>
          </div>
          {current?.error && (
            <p role="alert" className="sync-hook-error">
              未能读取同步 Hook 状态，请刷新核对。未更改连接。
            </p>
          )}
        </>
      )}
      {snapshot && (
        <HookDialog
          snapshot={snapshot}
          currentKey={key}
          disabled={disabled || !bridge}
          onClose={() => setSnapshot(null)}
          fallbackFocus={control.current}
          onStatus={(status) => {
            if (currentKey.current === snapshot.key) {
              generation.current++;
              setLocal({
                key: snapshot.key,
                status,
                loading: false,
                error: false,
              });
            }
          }}
        />
      )}
    </section>
  );
}

function HookDialog({
  snapshot,
  currentKey,
  disabled,
  onClose,
  onStatus,
  fallbackFocus,
}: {
  snapshot: Snapshot;
  currentKey: string;
  disabled: boolean;
  onClose(): void;
  onStatus(status: SyncHookStatus): void;
  fallbackFocus: HTMLElement | null;
}) {
  const id = useId();
  const panel = useRef<HTMLElement>(null);
  const mounted = useRef(false);
  const sequence = useRef(0);
  const flight = useRef<"preview" | "write" | "refresh" | null>(null);
  const latest = useRef({ currentKey, disabled });
  latest.current = { currentKey, disabled };
  const invalidated = useRef(false);
  if (currentKey !== snapshot.key) invalidated.current = true;
  const changed = invalidated.current;
  const [preview, setPreview] = useState<SyncHookPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState<
    "preview" | "write" | "refresh" | null
  >("preview");
  const [error, setError] = useState<string | null>(null);
  const [needsPreview, setNeedsPreview] = useState(false);
  const [result, setResult] = useState<SyncHookStatus | null>(null);
  const resultRef = useRef<SyncHookStatus | null>(null);
  const noChanges = preview !== null && preview.files.length === 0;
  const action =
    snapshot.operation === "uninstall"
      ? "卸载"
      : snapshot.updating
        ? "更新"
        : "安装";
  const active = useCallback(
    (token: number) => mounted.current && sequence.current === token,
    [],
  );
  const usable = useCallback(
    () =>
      !invalidated.current &&
      latest.current.currentKey === snapshot.key &&
      !latest.current.disabled &&
      hookBridge() === snapshot.bridge,
    [snapshot],
  );

  const loadPreview = useCallback(async () => {
    if (flight.current || resultRef.current || !usable()) return;
    const token = ++sequence.current;
    flight.current = "preview";
    setPending("preview");
    setError(null);
    setConfirmed(false);
    setNeedsPreview(true);
    try {
      const value = checkedPreview(
        await snapshot.bridge.previewSyncHook(
          snapshot.host.hostId,
          snapshot.operation,
        ),
        snapshot,
      );
      if (!active(token) || !usable()) return;
      setPreview(value);
      setNeedsPreview(false);
    } catch {
      if (active(token)) {
        setPreview(null);
        setError("未能核对文件变更，请重新预览。未提交本次操作。");
      }
    } finally {
      if (active(token)) {
        flight.current = null;
        setPending(null);
      }
    }
  }, [active, snapshot, usable]);
  useEffect(() => {
    mounted.current = true;
    void loadPreview();
    return () => {
      mounted.current = false;
      sequence.current++;
      flight.current = null;
    };
  }, [loadPreview]);

  useEffect(() => {
    const dialog = panel.current;
    const backdrop = dialog?.parentElement;
    if (!dialog || !backdrop) return;
    const prior = new Map<HTMLElement, boolean>();
    for (const child of document.body.children) {
      if (child instanceof HTMLElement && child !== backdrop) {
        prior.set(child, child.inert);
        child.inert = true;
      }
    }
    const focusInside = () =>
      (dialog.querySelector<HTMLElement>(focusSelector) ?? dialog).focus();
    const keepFocus = (event: FocusEvent) => {
      if (event.target instanceof Node && !dialog.contains(event.target))
        focusInside();
    };
    document.addEventListener("focusin", keepFocus);
    focusInside();
    return () => {
      document.removeEventListener("focusin", keepFocus);
      for (const [element, inert] of prior) element.inert = inert;
      if (
        snapshot.trigger.isConnected &&
        !(snapshot.trigger as HTMLButtonElement).disabled
      )
        snapshot.trigger.focus();
      else if (fallbackFocus?.isConnected) fallbackFocus.focus();
    };
  }, [snapshot, fallbackFocus]);
  useEffect(() => {
    if (pending === "write") panel.current?.focus();
  }, [pending]);
  function close() {
    if (flight.current !== "write") onClose();
  }

  async function refreshStatus() {
    if (flight.current || !resultRef.current || !usable()) return;
    const token = ++sequence.current;
    flight.current = "refresh";
    setPending("refresh");
    setError(null);
    try {
      const value = checkedStatus(
        await snapshot.bridge.getSyncHookStatus(snapshot.host.hostId),
        snapshot.host.hostId,
      );
      if (!active(token) || !usable()) return;
      onStatus(value);
      if (value.state !== resultRef.current.state)
        setError("本次操作已成功；当前文件状态已有变化，请关闭后重新核对。");
    } catch {
      if (active(token))
        setError(
          `${action}已成功，但状态刷新失败。刷新状态不会重复${action}。`,
        );
    } finally {
      if (active(token)) {
        flight.current = null;
        setPending(null);
      }
    }
  }
  async function submit() {
    if (
      !preview ||
      noChanges ||
      !confirmed ||
      needsPreview ||
      flight.current ||
      resultRef.current ||
      !usable()
    )
      return;
    const token = ++sequence.current;
    flight.current = "write";
    setPending("write");
    setError(null);
    try {
      const value = checkedStatus(
        await snapshot.bridge.applySyncHook(snapshot.host.hostId, {
          operation: preview.operation,
          installationId: preview.installationId,
          revision: preview.revision,
          fingerprint: preview.fingerprint,
          userConfirmed: true,
        }),
        snapshot.host.hostId,
      );
      if (
        snapshot.operation === "install"
          ? value.state !== "installed"
          : !["not-installed", "connection-required"].includes(value.state)
      )
        throw new Error("hook_write_unconfirmed");
      if (!active(token)) return;
      resultRef.current = value;
      setResult(value);
      setConfirmed(false);
      if (usable()) onStatus(value);
      flight.current = null;
      setPending(null);
      if (usable()) await refreshStatus();
    } catch {
      if (active(token)) {
        setError(`${action}结果尚未确认。请重新预览并核对后重试。`);
        setNeedsPreview(true);
        setConfirmed(false);
      }
    } finally {
      if (active(token)) {
        flight.current = null;
        setPending(null);
      }
    }
  }

  return createPortal(
    <div className="consent-backdrop sync-hook-backdrop">
      <section
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-scope`}
        aria-busy={!!pending}
        tabIndex={-1}
        className="consent-sheet sync-hook-sheet"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            close();
          }
          if (event.key === "Tab") {
            const items =
              panel.current?.querySelectorAll<HTMLElement>(focusSelector);
            const first = items?.[0],
              last = items?.[items.length - 1];
            if (!first || !last) {
              event.preventDefault();
              panel.current?.focus();
            } else if (
              event.shiftKey &&
              (document.activeElement === first ||
                document.activeElement === panel.current)
            ) {
              event.preventDefault();
              last.focus();
            } else if (
              !event.shiftKey &&
              (document.activeElement === last ||
                document.activeElement === panel.current)
            ) {
              event.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <header className="sync-hook-heading">
          <div>
            <p className="eyebrow">{snapshot.host.label}</p>
            <h2 id={`${id}-title`}>{action}同步 Hook</h2>
          </div>
          <button
            type="button"
            className="quiet sync-hook-icon"
            title="关闭"
            aria-label="关闭"
            disabled={pending === "write"}
            onClick={close}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="sync-hook-body">
          <p id={`${id}-scope`}>
            插件只通知新对话；读取与持续同步仍由来源权限控制。安装不会开启同步或授予模型处理权限。
          </p>
          {snapshot.operation === "uninstall" && (
            <p>不会关闭独立持续同步，也不会断开 MCP 记忆连接。</p>
          )}
          {preview && (
            <>
              <p className="sync-hook-note">
                安装身份 <code>{preview.installationId}</code> · 版本{" "}
                {preview.revision}
              </p>
              {!noChanges && (
                <ul className="sync-hook-files" aria-label="文件变更">
                  {preview.files.map((file) => (
                    <li key={file.path}>
                      <span>
                        {
                          { create: "新增", update: "更新", remove: "移除" }[
                            file.action
                          ]
                        }{" "}
                        ·{" "}
                        {file.owner === "host"
                          ? `${snapshot.host.label} 配置`
                          : "MemHub 文件"}
                      </span>
                      <code>{file.path}</code>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {noChanges && (
            <p role="status">
              {snapshot.operation === "install" && snapshot.updating
                ? "同步 Hook 已是当前版本，无需修改。"
                : "没有需要修改的文件，未提交操作。"}
            </p>
          )}
          {preview && !noChanges && !result && (
            <label className="sync-hook-confirm">
              <input
                type="checkbox"
                checked={confirmed && !changed}
                disabled={!!pending || disabled || changed || needsPreview}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              我确认以上文件变更
            </label>
          )}
          {result && (
            <p className="sync-hook-receipt" role="status">
              {snapshot.operation === "uninstall"
                ? "同步 Hook 已卸载。独立持续同步和 MCP 连接未改变。"
                : `同步 Hook 已${action}。来源持续同步设置未改变。`}
            </p>
          )}
          {pending && (
            <p role="status">
              {pending === "preview"
                ? "正在核对文件变更…"
                : pending === "write"
                  ? `正在${action}同步 Hook…`
                  : "正在刷新状态…"}
            </p>
          )}
          {(changed || error) && (
            <p role="alert" className="sync-hook-error">
              {changed ? changedMessage : error}
            </p>
          )}
        </div>
        <footer className="consent-actions sync-hook-footer">
          <button
            type="button"
            className="secondary"
            disabled={pending === "write"}
            onClick={close}
          >
            {result || noChanges ? "完成" : "取消"}
          </button>
          {error && !result && !changed && (
            <button
              type="button"
              className="secondary"
              disabled={!!pending || disabled}
              onClick={() => void loadPreview()}
            >
              <RefreshCw size={16} aria-hidden="true" />
              重新预览
            </button>
          )}
          {result && error && !changed && (
            <button
              type="button"
              className="secondary"
              disabled={!!pending || disabled}
              onClick={() => void refreshStatus()}
            >
              <RefreshCw size={16} aria-hidden="true" />
              刷新状态
            </button>
          )}
          {preview && !noChanges && !result && (
            <button
              type="button"
              disabled={
                !confirmed || !!pending || disabled || changed || needsPreview
              }
              onClick={() => void submit()}
            >
              {snapshot.operation === "uninstall" ? (
                <Trash2 size={16} aria-hidden="true" />
              ) : snapshot.updating ? (
                <RefreshCw size={16} aria-hidden="true" />
              ) : (
                <Download size={16} aria-hidden="true" />
              )}
              确认{action}
            </button>
          )}
        </footer>
      </section>
    </div>,
    document.body,
  );
}
