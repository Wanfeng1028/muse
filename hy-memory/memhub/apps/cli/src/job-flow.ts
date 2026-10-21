import type { ImportJob } from "@one-memory/contracts";

import type { CoreOperations } from "./core-operations.js";
import { validateImportJob } from "./core-responses.js";
import { PRODUCT } from "./version.js";

const SOURCE_ID = /^[a-z0-9][a-z0-9-]{0,127}$/;
const JOB_ID = /^[A-Za-z0-9][\w.-]{0,127}$/;

export type JobStartPlan = {
  kind: "import_job_start";
  source_id: string;
  operation: "history" | "sync";
};

export type JobActionPlan = {
  kind: "import_job_action";
  job_id: string;
  action: "pause" | "resume" | "cancel";
};

export type JobFlowDocument =
  | {
      schema_version: 1;
      product: string;
      command: "jobs";
      state: "preview";
      plan: JobStartPlan | JobActionPlan;
    }
  | {
      schema_version: 1;
      product: string;
      command: "jobs";
      state: "committed" | "recovered";
      operation_id: string;
      job?: ImportJob;
      jobs?: ImportJob[];
    }
  | {
      schema_version: 1;
      product: string;
      command: "jobs";
      state: "rejected" | "unknown" | "invalid" | "not_found";
      operation_id?: string;
      code: string;
    };

export function planJobStart(
  sourceId: string,
  operation: "history" | "sync",
): JobFlowDocument {
  if (!SOURCE_ID.test(sourceId)) return invalid("invalid_source_id");
  return {
    schema_version: 1,
    product: PRODUCT,
    command: "jobs",
    state: "preview",
    plan: {
      kind: "import_job_start",
      source_id: sourceId,
      operation,
    },
  };
}

export function planJobAction(
  jobId: string,
  action: "pause" | "resume" | "cancel",
): JobFlowDocument {
  if (!JOB_ID.test(jobId)) return invalid("invalid_job_id");
  return {
    schema_version: 1,
    product: PRODUCT,
    command: "jobs",
    state: "preview",
    plan: {
      kind: "import_job_action",
      job_id: jobId,
      action,
    },
  };
}

export async function executeJobStart(
  plan: JobStartPlan,
  operations: CoreOperations,
): Promise<JobFlowDocument> {
  const result = await operations.post<unknown>("/api/v1/import-jobs", {
    source_id: plan.source_id,
    operation: plan.operation,
  });
  return jobMutationResult(plan.source_id, result);
}

export async function executeJobAction(
  plan: JobActionPlan,
  operations: CoreOperations,
): Promise<JobFlowDocument> {
  const result = await operations.post<unknown>(
    `/api/v1/import-jobs/${encodeURIComponent(plan.job_id)}/${plan.action}`,
    {},
  );
  return jobMutationResult(plan.job_id, result);
}

function jobMutationResult(
  operationId: string,
  result:
    | { state: "committed"; data: unknown }
    | { state: "rejected"; code: string; http_status: number }
    | { state: "unknown"; code: string },
): JobFlowDocument {
  if (result.state === "rejected") {
    return {
      schema_version: 1,
      product: PRODUCT,
      command: "jobs",
      state: result.http_status === 404 ? "not_found" : "rejected",
      operation_id: operationId,
      code: result.code,
    };
  }
  if (result.state === "unknown") {
    return {
      schema_version: 1,
      product: PRODUCT,
      command: "jobs",
      state: "unknown",
      operation_id: operationId,
      code: result.code,
    };
  }
  const job = validateImportJob(result.data);
  if (!job) return invalid("job_receipt_invalid");
  return {
    schema_version: 1,
    product: PRODUCT,
    command: "jobs",
    state: "committed",
    operation_id: operationId,
    job,
  };
}

export function jobExitCode(document: JobFlowDocument): number {
  if (document.state === "preview" || document.state === "committed") return 0;
  if (document.state === "recovered") return 0;
  return document.state === "rejected" || document.state === "unknown" ? 1 : 2;
}

function invalid(code: string): JobFlowDocument {
  return {
    schema_version: 1,
    product: PRODUCT,
    command: "jobs",
    state: "invalid",
    code,
  };
}
