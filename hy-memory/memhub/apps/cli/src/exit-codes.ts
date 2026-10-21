export const EXIT_OK = 0;
export const EXIT_FAILED = 1;
export const EXIT_USAGE = 2;
export const EXIT_RUNTIME_STOPPED = 3;
export const EXIT_PLAN_BLOCKED = 4;

export type ExitCode = {
  readonly code: number;
  readonly name: string;
  readonly summary: string;
};

export const EXIT_CODES: readonly ExitCode[] = [
  { code: EXIT_OK, name: "ok", summary: "命令按请求完成。" },
  {
    code: EXIT_FAILED,
    name: "failed",
    summary: "命令执行失败或状态无法确认；结果未知时不要重放写操作。",
  },
  {
    code: EXIT_USAGE,
    name: "usage",
    summary: "参数或命令无效，没有执行任何操作。",
  },
  {
    code: EXIT_RUNTIME_STOPPED,
    name: "runtime_stopped",
    summary: "查询成功，本机 Runtime 未在运行。",
  },
  {
    code: EXIT_PLAN_BLOCKED,
    name: "plan_blocked",
    summary: "计划生成成功但当前平台或环境不允许执行，未做改动。",
  },
];
