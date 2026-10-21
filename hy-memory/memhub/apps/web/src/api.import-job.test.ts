import { expect, it } from "vitest";
import { parseImportJob } from "./api";

const job = {
  job_id: "job-1",
  user_id: "local",
  source_id: "cursor",
  operation: "history",
  status: "pending",
  phase: null,
  checkpoint: null,
  discovered: 0,
  discovered_targets: 0,
  emitted: 0,
  stored: 0,
  revised: 0,
  merged: 0,
  skipped: 0,
  errors: 0,
  created_at: "2026-10-16T06:00:00Z",
  updated_at: "2026-10-16T06:00:00Z",
};

it("accepts the persisted cutoff carried by a volume-limited first import", () => {
  expect(
    parseImportJob({
      ...job,
      history_after: "2026-10-13T06:00:00Z",
    }),
  ).toMatchObject({
    job_id: "job-1",
    history_after: "2026-10-13T06:00:00Z",
  });
});

it("rejects malformed or unknown import-job fields", () => {
  expect(parseImportJob({ ...job, history_after: "not-a-date" })).toBeNull();
  expect(parseImportJob({ ...job, extra: true })).toBeNull();
});
