import type { ImportJob, SourceResponse } from "@one-memory/contracts";

interface SourceCardProps {
  source: SourceResponse;
  job?: ImportJob;
  busyKey: string | null;
  onAuthorize(source: SourceResponse, confirmedOverride?: boolean): void;
  onDetect(sourceId: string): void;
  onImport(sourceId: string): void;
  onChangeJob(jobId: string, action: "pause" | "resume" | "cancel"): void;
  onRevoke(sourceId: string): void;
}

export function SourceCard({
  source,
  job,
  busyKey,
  onAuthorize,
  onDetect,
  onImport,
  onChangeJob,
  onRevoke,
}: SourceCardProps) {
  const isBusy = busyKey?.endsWith(source.source_id) ?? false;
  const authorize = () => {
    if (source.candidate_kind !== "environment_override") {
      onAuthorize(source, false);
      return;
    }
    const confirmed = window.confirm(
      `此来源由环境变量指定。是否允许 MemHub 读取该目录中的 AI 对话？\n\n${source.candidate_path}`,
    );
    if (confirmed) onAuthorize(source, true);
  };
  return (
    <article
      className="source-card"
      aria-labelledby={`${source.source_id}-title`}
    >
      <div className="source-heading">
        <div>
          <h3 id={`${source.source_id}-title`}>{source.display_name}</h3>
          <p>{source.storage_kinds.join(" · ")}</p>
        </div>
        <span className="status-label">{statusLabel(source, job)}</span>
      </div>
      <p className="source-capability">
        {source.capabilities.verification === "real_replayed"
          ? "已通过真实样本回放"
          : "仅通过模拟样本"}
        {" · "}
        {source.capabilities.live_sync === "implemented"
          ? "持续增量同步"
          : "仅手动导入"}
        {" · "}
        {/* The plan requires every source to say which kind of following it
            offers: a source we can only read forward from will keep serving a
            memory whose original sentence the user has since deleted. Calling
            that "实时同步" would promise a copy that tracks the source. */}
        {source.sync_completeness === "one_time_snapshot"
          ? "一次性快照，不跟随原应用变化"
          : source.sync_completeness === "full_dynamic"
            ? "完整动态同步"
            : "仅新增同步，源头删除不跟随"}
        {" · "}
        {/* Whether *this* machine has recall wired into the host is read from
            its install journal and shown in the recall section; here we can
            only honestly say an installer exists for it. */}
        {source.capabilities.recall === "implemented"
          ? "支持应用内召回"
          : "暂不支持应用内召回"}
      </p>

      {job ? <ImportCounts job={job} /> : null}

      {sessionSummary(source)}

      <div className="source-actions">
        {!source.authorized ? (
          <button type="button" disabled={isBusy} onClick={authorize}>
            {source.candidate_kind === "environment_override"
              ? "确认并授权自定义目录"
              : "授权此来源"}
          </button>
        ) : (
          <>
            {source.detected === null ? (
              <button
                type="button"
                disabled={isBusy}
                onClick={() => onDetect(source.source_id)}
              >
                检测历史记录
              </button>
            ) : null}
            {source.detected === false ? (
              <button
                type="button"
                disabled={isBusy}
                onClick={() => onDetect(source.source_id)}
              >
                重新检测
              </button>
            ) : null}
            {source.detected === true && canStart(job) ? (
              <button
                type="button"
                disabled={isBusy}
                onClick={() => onImport(source.source_id)}
              >
                {job?.status === "completed"
                  ? source.sync_completeness === "one_time_snapshot"
                    ? "重新读取快照"
                    : "检查新增内容"
                  : "开始导入"}
              </button>
            ) : null}
            {job?.status === "running" || job?.status === "pending" ? (
              <>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onChangeJob(job.job_id, "pause")}
                >
                  暂停
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onChangeJob(job.job_id, "cancel")}
                >
                  取消
                </button>
              </>
            ) : null}
            {job && ["paused", "interrupted", "failed"].includes(job.status) ? (
              <>
                <button
                  type="button"
                  onClick={() => onChangeJob(job.job_id, "resume")}
                >
                  继续
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onChangeJob(job.job_id, "cancel")}
                >
                  取消
                </button>
              </>
            ) : null}
            <button
              type="button"
              className="quiet"
              disabled={isBusy}
              onClick={() => onRevoke(source.source_id)}
            >
              断开
            </button>
          </>
        )}
      </div>
    </article>
  );
}

function ImportCounts({ job }: { job: ImportJob }) {
  return (
    <dl className="import-counts" aria-live="polite">
      <div>
        <dt>发现</dt>
        <dd>{job.discovered}</dd>
      </div>
      <div>
        <dt>新增</dt>
        <dd>{job.stored}</dd>
      </div>
      <div>
        <dt>已存在</dt>
        <dd>{job.merged}</dd>
      </div>
      <div>
        <dt>跳过</dt>
        <dd>{job.skipped}</dd>
      </div>
      <div>
        <dt>错误</dt>
        <dd>{job.errors}</dd>
      </div>
    </dl>
  );
}

function sessionSummary(source: SourceResponse) {
  // Only print a number the core actually measured. An absent or null
  // session_count means "not measured", not zero, so it must never turn into
  // a number on screen. A detected host with nothing readable yet still owes
  // the person an honest sentence rather than a bare zero.
  if (source.detected !== true) return null;
  const count = source.session_count;
  if (count === null || count === undefined) return null;
  return (
    <p className="session-count">
      {count > 0 ? `找到 ${count} 个会话` : "已安装，暂未发现会话"}
    </p>
  );
}

function canStart(job: ImportJob | undefined): boolean {
  return !job || ["completed", "cancelled"].includes(job.status);
}

/** What the person is being asked to authorize, in the words they care about.
 *
 * A count the core did not send is not a count of zero, so an absent or null
 * `session_count` yields no line at all rather than "找到 0 个会话".
 */
function sessionCountLabel(source: SourceResponse): string | null {
  const count = source.session_count;
  if (count === undefined || count === null) return null;
  if (count <= 0) return "已安装，暂未发现会话";
  return `找到 ${count} 个会话`;
}

function statusLabel(
  source: SourceResponse,
  job: ImportJob | undefined,
): string {
  if (!source.authorized) return "未授权";
  if (source.detected === null) return "等待检测";
  if (!source.detected) return "未发现记录";
  if (!job) return "可导入";
  const labels: Record<ImportJob["status"], string> = {
    pending: "等待开始",
    running: "正在后台导入",
    paused: "已暂停",
    interrupted: "上次退出时中断",
    completed: "导入完成",
    failed: "导入失败",
    cancelled: "已取消",
  };
  return labels[job.status];
}
