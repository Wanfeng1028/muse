import { useApi } from "../../hooks/use-api";
import { useColors } from "../../hooks/use-colors";
import { tr } from "../../lib/app-language";
import type { Theme } from "../../hooks/use-theme";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Issue {
  code: string;
  level: "error" | "warning" | "info";
  message: string;
  nodeIds: string[];
}

interface AnalysisReport {
  ok: boolean;
  issues: Issue[];
}

interface PathDistribution {
  total: number;
  truncated: boolean;
  byEnding: Record<string, number>;
  lengthHistogram: Record<number, number>;
}

interface AnalysisData {
  report: AnalysisReport;
  distribution: PathDistribution;
}

type Colors = ReturnType<typeof useColors>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function levelClass(level: "error" | "warning" | "info"): string {
  if (level === "error") return "text-destructive";
  if (level === "warning") return "text-amber-500";
  return "text-muted-foreground";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function IssuesList({ report, c }: { report: AnalysisReport; c: Colors }) {
  return (
    <div className="border border-border rounded p-3" data-testid="validation-panel">
      <div className={`text-sm font-medium ${c.muted}`}>
        {tr("校验", "Validation")}{report.ok ? "" : tr("（有阻断问题）", " (blocking issues)")}
      </div>
      {report.issues.length === 0 ? (
        <div className={`text-sm mt-1 ${c.muted}`}>{tr("无问题", "No issues")}</div>
      ) : (
        <ul className="mt-1 space-y-1">
          {report.issues.map((issue, i) => (
            <li
              key={i}
              data-testid={`validation-issue-${issue.code}`}
              className="text-xs flex gap-2"
            >
              <span className={levelClass(issue.level)}>[{issue.level}]</span>
              <span className="text-foreground">{issue.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PathDistributionPanel({
  distribution,
  c,
}: {
  distribution: PathDistribution;
  c: Colors;
}) {
  const endingEntries = Object.entries(distribution.byEnding);
  const histEntries = Object.entries(distribution.lengthHistogram)
    .map(([len, count]) => ({ len: Number(len), count }))
    .sort((a, b) => a.len - b.len);
  const maxHistCount = Math.max(...histEntries.map((e) => e.count), 1);

  return (
    <div data-testid="path-distribution" className="border border-border rounded p-3">
      <div className={`text-sm font-medium mb-2 ${c.muted}`}>{tr("路径分布", "Path distribution")}</div>

      {distribution.truncated && (
        <div className={`text-xs mb-2 ${c.muted}`}>
          {tr(`路径过多，仅统计前 ${distribution.total} 条`, `Too many paths; only the first ${distribution.total} are counted`)}
        </div>
      )}

      {endingEntries.length === 0 ? (
        <div className={`text-sm ${c.muted}`}>{tr("暂无路径数据", "No path data")}</div>
      ) : (
        <div className="space-y-1.5 mb-4">
          {endingEntries.map(([endingId, count]) => {
            const pct = distribution.total > 0 ? (count / distribution.total) * 100 : 0;
            return (
              <div key={endingId} className="flex items-center gap-2 text-xs">
                <span
                  className={`shrink-0 w-28 truncate ${c.muted}`}
                  title={endingId}
                >
                  {endingId}
                </span>
                <div className="flex-1 bg-muted/30 rounded-full h-2 overflow-hidden">
                  <div
                    className="h-2 rounded-full bg-primary/70"
                    style={{ width: `${pct.toFixed(1)}%` }}
                  />
                </div>
                <span className="shrink-0 text-foreground w-8 text-right tabular-nums">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {histEntries.length > 0 && (
        <div>
          <div className={`text-xs font-medium mb-2 ${c.muted}`}>{tr("路径长度分布", "Path length distribution")}</div>
          <div className="flex items-end gap-1 h-12">
            {histEntries.map(({ len, count }) => {
              const heightPct = (count / maxHistCount) * 100;
              return (
                <div
                  key={len}
                  className="flex flex-col items-center gap-0.5 flex-1 min-w-0"
                >
                  <div
                    className="w-full bg-primary/50 rounded-t"
                    style={{ height: `${heightPct}%` }}
                    title={tr(`长度 ${len}: ${count} 条`, `Length ${len}: ${count} paths`)}
                  />
                  <span className={`text-xs leading-none ${c.muted}`}>{len}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AnalysisPanel (public)
// ---------------------------------------------------------------------------

export function AnalysisPanel({
  projectId,
  theme,
}: {
  projectId: string;
  theme: Theme;
}) {
  const c = useColors(theme);
  const { data, loading, error } = useApi<AnalysisData>(
    `/projects/${projectId}/story-graph/analysis`,
  );

  if (loading) {
    return <div className={`p-4 text-sm ${c.muted}`}>{tr("正在加载分析结果…", "Loading analysis…")}</div>;
  }

  if (error) {
    return <div className="p-4 text-sm text-destructive">{tr("加载失败：", "Load failed: ")}{error}</div>;
  }

  if (!data) {
    return <div className={`p-4 text-sm ${c.muted}`}>{tr("暂无分析数据", "No analysis data")}</div>;
  }

  return (
    <div className="p-4 max-w-2xl space-y-4">
      <IssuesList report={data.report} c={c} />
      <PathDistributionPanel distribution={data.distribution} c={c} />
    </div>
  );
}
