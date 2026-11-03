import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { run } from "./cli.js";

const transport = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("axios", () => ({
  default: { create: vi.fn(() => transport), get: vi.fn() },
}));

const runtime = vi.hoisted(() => ({
  inspectRuntimeStatus: vi.fn(),
  discoverRuntimeAttachment: vi.fn(),
}));
vi.mock("@one-memory/runtime-control", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@one-memory/runtime-control")>()),
  ...runtime,
}));

const RUNNING = {
  state: "running" as const,
  code: "runtime_verified",
  instanceId: "instance-1",
  host: "127.0.0.1",
  port: 8765,
  version: "1.2.3",
};
const ATTACHED = {
  instanceId: "instance-1",
  apiToken: "synthetic-runtime-token",
  host: "127.0.0.1" as const,
  port: 8765,
  servicePid: 4242,
  health: {
    status: "ok",
    service: "one-memory-core",
    version: "1.2.3",
    instance_id: "instance-1",
  },
};
const SOURCE = {
  source_id: "codex",
  display_name: "Codex",
  storage_kinds: ["history"],
  available: true,
  authorized: false,
  detected: null,
  root_label: "Codex history",
  candidate_path: "/SYNTHETIC_PRIVATE_PATH",
  candidate_kind: "default",
  candidate_revision: 0,
  candidate_root_id: "root-identity-1",
  imported_messages: 0,
  imported_conversations: 0,
  capabilities: {
    historical_import: "implemented",
    incremental_import: "implemented",
    live_sync: "implemented",
    recall: "implemented",
    installer: "not_implemented",
    verification: "fixture_only",
  },
  sync_completeness: "additions_only",
  location_state: "found",
};
const MISSING_SOURCE = {
  ...SOURCE,
  source_id: "workbuddy",
  display_name: "WorkBuddy",
  candidate_path: "/SYNTHETIC_MISSING_PATH",
  candidate_root_id: null,
  location_state: "not_found",
};

const PROFILE = {
  profile_id: "profile-1",
  name: "Synthetic",
  provider_kind: "openai_compatible",
  base_url: "https://example.invalid/v1",
  model: "synthetic-model",
  embedding_model: null,
  embedding_provider_kind: null,
  embedding_base_url: null,
  embedding_dimensions: null,
  has_api_key: true,
  credential_state: "available",
  timeout_seconds: 240,
  max_concurrency: 4,
  context_window: null,
  disable_thinking: true,
  capabilities: {
    endpoint_reachable: false,
    model_available: false,
    structured_output: false,
    embedding_available: false,
  },
  revision: 1,
  is_active: false,
  created_at: "T1",
  updated_at: "T1",
};
const PROBE_PROFILE = {
  ...PROFILE,
  profile_id: "22222222-2222-4222-8222-222222222222",
  revision: 3,
};

let directory: string;

beforeEach(async () => {
  vi.clearAllMocks();
  directory = await mkdtemp(path.join(tmpdir(), "om-headless-"));
  runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
  runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
  transport.get.mockImplementation(async (url: string) => {
    if (url === "/api/v1/sources") {
      return { status: 200, data: [SOURCE, MISSING_SOURCE] };
    }
    return { status: 404, data: { detail: "not_found" } };
  });
  transport.post.mockImplementation(
    async (url: string, body: Record<string, unknown>) => {
      if (url === "/api/v1/sources/connect") {
        return {
          status: 200,
          data: {
            request_id: body.request_id,
            accepted_source_ids: ["codex"],
            failed_sources: {},
            jobs: [importJob()],
          },
        };
      }
      if (url === "/api/v1/model-profiles") {
        return { status: 200, data: PROFILE };
      }
      return { status: 404, data: {} };
    },
  );
});

describe("headless source setup and import", () => {
  it("creates a confirmation-bound plan without exposing the source path", async () => {
    const result = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    expect(result.code).toBe(0);
    const document = JSON.parse(result.stdout);
    expect(document).toMatchObject({
      state: "preview",
      plan: {
        kind: "source_import",
        source_ids: ["codex"],
        source_roots: { codex: "root-identity-1" },
        full_rescan: false,
        onboarding: true,
      },
    });
    expect(document.plan.request_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(document.plan.digest).toMatch(/^[0-9a-f]{64}$/);
    expect(result.stdout).not.toContain("SYNTHETIC_PRIVATE_PATH");
    expect(transport.post).not.toHaveBeenCalled();
  });

  it("executes exactly the saved plan only after explicit confirmation", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const planFile = path.join(directory, "source-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockImplementation(
      async (_url: string, body: Record<string, unknown>) => ({
        status: 200,
        data: {
          request_id: body.request_id,
          accepted_source_ids: ["codex"],
          failed_sources: {},
          jobs: [importJob()],
        },
      }),
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).toBe(0);
    expect(JSON.parse(result.stdout).state).toBe("committed");
    expect(transport.post).toHaveBeenCalledTimes(1);
    expect(transport.post).toHaveBeenCalledWith(
      "/api/v1/sources/connect",
      expect.objectContaining({
        source_ids: ["codex"],
        source_roots: { codex: "root-identity-1" },
        full_rescan: false,
        enable_sync: true,
      }),
      undefined,
    );
  });

  // C8 P2 (2026-09-29 H18r2): when every source was rejected, the receipt had
  // `accepted_source_ids: []` and `failed_sources: {claude-code:
  // "source_read_disabled"}`, yet the CLI still reported `committed` and exit 0.
  // "Nothing was accepted" is not success. Mirrors the A19 exit-code contract.
  it("reports all-rejected as rejected with a non-zero exit and the reason", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const planFile = path.join(directory, "reject-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockImplementation(
      async (_url: string, body: Record<string, unknown>) => ({
        status: 200,
        data: {
          request_id: body.request_id,
          accepted_source_ids: [],
          failed_sources: { codex: "source_read_disabled" },
          jobs: [],
        },
      }),
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).not.toBe(0);
    const document = JSON.parse(result.stdout);
    expect(document.state).toBe("rejected");
    expect(document.receipt.failed_sources).toEqual({
      codex: "source_read_disabled",
    });
  });

  it("reports partial success with a non-zero exit and keeps the receipt", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const planFile = path.join(directory, "partial-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockImplementation(
      async (_url: string, body: Record<string, unknown>) => ({
        status: 200,
        data: {
          request_id: body.request_id,
          accepted_source_ids: ["codex"],
          failed_sources: { cursor: "source_identity_changed" },
          jobs: [importJob()],
        },
      }),
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).not.toBe(0);
    const document = JSON.parse(result.stdout);
    expect(document.state).toBe("partial");
    expect(document.receipt.accepted_source_ids).toEqual(["codex"]);
    expect(document.receipt.failed_sources).toEqual({
      cursor: "source_identity_changed",
    });
  });

  // C8 H18r3 exact shape: the read-switch probe produced
  // accepted=[] / failed_sources={workbuddy:"source_read_disabled"} / jobs=[]
  // and the CLI reported committed + exit 0 with no text. Reproduced here with a
  // `jobs: []` batch (not a single-source plan) and asserted in both JSON and
  // text mode, because the package symptom was the *text* saying committed.
  it("classifies an empty-jobs all-rejected batch as rejected in JSON and text", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const planFile = path.join(directory, "probe-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockImplementation(
      async (_url: string, body: Record<string, unknown>) => ({
        status: 200,
        data: {
          request_id: body.request_id,
          accepted_source_ids: [],
          failed_sources: { codex: "source_read_disabled" },
          jobs: [],
        },
      }),
    );
    const jsonResult = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(jsonResult.code).toBe(1);
    const document = JSON.parse(jsonResult.stdout);
    expect(document.state).toBe("rejected");
    expect(document.code).toBe("source_import_all_rejected");
    expect(document.receipt.failed_sources).toEqual({
      codex: "source_read_disabled",
    });

    // Text mode must name the failed source and must not claim success.
    const textPlanFile = path.join(directory, "probe-plan-text.json");
    await writeFile(textPlanFile, preview.stdout, { mode: 0o600 });
    transport.post.mockImplementation(
      async (_url: string, body: Record<string, unknown>) => ({
        status: 200,
        data: {
          request_id: body.request_id,
          accepted_source_ids: [],
          failed_sources: { codex: "source_read_disabled" },
          jobs: [],
        },
      }),
    );
    const textResult = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      textPlanFile,
      "--confirm",
    ]);
    expect(textResult.code).toBe(1);
    expect(textResult.stdout).toContain("codex");
    expect(textResult.stdout).toContain("source_read_disabled");
    expect(textResult.stdout).not.toContain("操作状态：committed");
  });

  it("recovers an unknown source write by request ID without replay", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const document = JSON.parse(preview.stdout);
    const requestId = document.plan.request_id;
    const planFile = path.join(directory, "source-plan.json");
    await writeFile(planFile, preview.stdout);
    transport.post.mockRejectedValue(new Error("socket closed"));
    transport.get.mockImplementation(async (url: string) =>
      url === `/api/v1/source-connections/${requestId}`
        ? {
            status: 200,
            data: {
              request_id: requestId,
              accepted_source_ids: ["codex"],
              failed_sources: {},
              jobs: [importJob()],
            },
          }
        : { status: 404, data: {} },
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).toBe(0);
    expect(JSON.parse(result.stdout).state).toBe("recovered");
    expect(transport.post).toHaveBeenCalledTimes(1);
    expect(
      (transport.get.mock.calls as [string][]).filter(
        ([url]) => url === `/api/v1/source-connections/${requestId}`,
      ),
    ).toHaveLength(1);
  });

  // A fresh request that is refused because another import is in flight is a
  // refusal, not a recovered success. Only a matching-request-ID lookup with a
  // terminal accepted receipt may become `recovered`.
  it("rejects a fresh all-busy receipt as source_import_all_busy", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const planFile = path.join(directory, "busy-repeat-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockImplementation(
      async (_url: string, body: Record<string, unknown>) => ({
        status: 200,
        data: {
          request_id: body.request_id,
          accepted_source_ids: [],
          failed_sources: { codex: "source_import_busy" },
          jobs: [],
        },
      }),
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    const out = JSON.parse(result.stdout);
    expect(out.state).toBe("rejected");
    expect(out.code).toBe("source_import_all_busy");
    expect(out.receipt.failed_sources).toEqual({
      codex: "source_import_busy",
    });
    expect(result.code).toBe(1);
  });

  it("does not recover a prior nonterminal receipt", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const requestId = JSON.parse(preview.stdout).plan.request_id as string;
    const planFile = path.join(directory, "nonterminal-prior-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockRejectedValue(new Error("socket closed"));
    transport.get.mockImplementation(async (url: string) =>
      url === `/api/v1/source-connections/${requestId}`
        ? {
            status: 200,
            data: {
              request_id: requestId,
              accepted_source_ids: [],
              failed_sources: {},
              jobs: [],
            },
          }
        : { status: 404, data: {} },
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    const out = JSON.parse(result.stdout);
    expect(out.state).not.toBe("recovered");
    expect(result.code).not.toBe(0);
    expect(transport.post).toHaveBeenCalledTimes(1);
  });

  it("does not report a recovered all-rejected receipt as success", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const document = JSON.parse(preview.stdout);
    const requestId = document.plan.request_id;
    const planFile = path.join(directory, "recovered-reject-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    vi.clearAllMocks();
    runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    // POST result unknown (transport dropped)...
    transport.post.mockRejectedValue(new Error("socket closed"));
    // ...and the looked-up receipt says every source was refused.
    transport.get.mockImplementation(async (url: string) =>
      url === `/api/v1/source-connections/${requestId}`
        ? {
            status: 200,
            data: {
              request_id: requestId,
              accepted_source_ids: [],
              failed_sources: { codex: "source_read_disabled" },
              jobs: [],
            },
          }
        : { status: 404, data: {} },
    );
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).not.toBe(0);
    const out = JSON.parse(result.stdout);
    expect(out.state).toBe("rejected");
    expect(out.receipt.failed_sources).toEqual({
      codex: "source_read_disabled",
    });
  });

  it("never reposts a plan once its durable attempt fence exists", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const document = JSON.parse(preview.stdout);
    const requestId = document.plan.request_id;
    const planFile = path.join(directory, "source-plan.json");
    await writeFile(planFile, preview.stdout);
    const argv = [
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ];
    expect((await capturedRun(argv)).code).toBe(0);
    transport.get.mockImplementation(async (url: string) =>
      url === `/api/v1/source-connections/${requestId}`
        ? {
            status: 200,
            data: {
              request_id: requestId,
              accepted_source_ids: ["codex"],
              failed_sources: {},
              jobs: [importJob()],
            },
          }
        : { status: 404, data: {} },
    );
    expect((await capturedRun(argv)).code).toBe(0);
    expect(transport.post).toHaveBeenCalledTimes(1);
  });

  it("rejects missing confirmation or a tampered plan before POST", async () => {
    const preview = await capturedRun([
      "setup",
      "plan",
      "--source",
      "codex",
      "--json",
    ]);
    const validPlanFile = path.join(directory, "valid.json");
    await writeFile(validPlanFile, preview.stdout);
    const unconfirmed = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      validPlanFile,
      "--json",
    ]);
    expect(unconfirmed.code).toBe(2);
    expect(transport.post).not.toHaveBeenCalled();

    const document = JSON.parse(preview.stdout);
    document.plan.source_roots.codex = "tampered-root";
    const planFile = path.join(directory, "tampered.json");
    await writeFile(planFile, JSON.stringify(document));
    const result = await capturedRun([
      "sources",
      "import",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect([1, 2]).toContain(result.code);
    expect(transport.post).not.toHaveBeenCalled();
  });
});

describe("headless model profile creation", () => {
  it("plans locally and refuses credentials embedded in config", async () => {
    const configFile = path.join(directory, "model.json");
    await writeFile(
      configFile,
      JSON.stringify({
        name: "Synthetic",
        provider_kind: "openai_compatible",
        base_url: "https://example.invalid/v1",
        model: "synthetic-model",
      }),
    );
    const result = await capturedRun([
      "models",
      "plan",
      "--config-file",
      configFile,
      "--json",
    ]);
    expect(result.code).toBe(0);
    expect(JSON.parse(result.stdout)).toMatchObject({
      state: "preview",
      plan: { kind: "model_profile_create" },
    });
    expect(runtime.inspectRuntimeStatus).not.toHaveBeenCalled();
    expect(transport.post).not.toHaveBeenCalled();

    await writeFile(
      configFile,
      JSON.stringify({
        name: "Synthetic",
        provider_kind: "openai_compatible",
        model: "synthetic-model",
        api_key: "SYNTHETIC_MUST_NOT_ENTER_PLAN",
      }),
    );
    const rejected = await capturedRun([
      "models",
      "plan",
      "--config-file",
      configFile,
      "--json",
    ]);
    expect(rejected.code).toBe(1);
    expect(rejected.stdout).not.toContain("SYNTHETIC_MUST_NOT_ENTER_PLAN");
  });

  it("reads the API key from a bounded file and never returns it", async () => {
    const planFile = await modelPlanFile();
    const keyFile = path.join(directory, "key");
    await writeFile(keyFile, "SYNTHETIC_SECRET_KEY\n", { mode: 0o600 });
    const result = await capturedRun([
      "models",
      "configure",
      "--plan-file",
      planFile,
      "--api-key-file",
      keyFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).toBe(0);
    expect(JSON.parse(result.stdout)).toMatchObject({
      state: "committed",
      receipt: {
        profile_id: "profile-1",
        credential_state: "available",
      },
    });
    expect(result.stdout + result.stderr).not.toContain("SYNTHETIC_SECRET_KEY");
    expect(transport.post.mock.calls[0][1]).toMatchObject({
      api_key: "SYNTHETIC_SECRET_KEY",
    });
  });

  it("refuses an API-key file readable by group or others", async () => {
    const planFile = await modelPlanFile();
    const keyFile = path.join(directory, "loose-key");
    await writeFile(keyFile, "SYNTHETIC_LOOSE_KEY\n", { mode: 0o644 });
    const result = await capturedRun([
      "models",
      "configure",
      "--plan-file",
      planFile,
      "--api-key-file",
      keyFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).toBe(2);
    expect(transport.post).not.toHaveBeenCalled();
    expect(result.stdout + result.stderr).not.toContain("SYNTHETIC_LOOSE_KEY");
  });

  it("recovers an unknown model create through its operation receipt", async () => {
    const planFile = await modelPlanFile();
    const plan = JSON.parse(
      await import("node:fs/promises").then((fs) =>
        fs.readFile(planFile, "utf8"),
      ),
    );
    const operationId = plan.plan.operation_id;
    transport.post.mockRejectedValue(new Error("socket closed"));
    transport.get.mockImplementation(async (url: string) =>
      url === `/api/v1/model-profile-creations/${operationId}`
        ? {
            status: 200,
            data: {
              operation_id: operationId,
              state: "committed",
              profile_id: "profile-1",
              created_revision: 1,
            },
          }
        : { status: 404, data: {} },
    );
    const result = await capturedRun([
      "models",
      "configure",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).toBe(0);
    expect(JSON.parse(result.stdout).state).toBe("recovered");
    expect(transport.post).toHaveBeenCalledTimes(1);
    expect(transport.get).toHaveBeenCalledTimes(1);
  });
});

describe("recoverable model probe operations", () => {
  it("lists and shows safe model configuration without endpoint leakage", async () => {
    transport.get.mockResolvedValue({
      status: 200,
      data: [
        {
          ...PROBE_PROFILE,
          base_url: "https://internal.example.invalid/v1",
          embedding_provider_kind: "local_onnx",
          embedding_model: "local-model",
        },
      ],
    });
    const listed = await capturedRun(["models", "list", "--json"]);
    expect(listed.code).toBe(0);
    expect(JSON.parse(listed.stdout)).toMatchObject({
      state: "ok",
      profiles: [
        {
          profile_id: PROBE_PROFILE.profile_id,
          generation_endpoint: "custom",
          embedding_mode: "local",
        },
      ],
    });
    expect(listed.stdout).not.toContain("internal.example.invalid");

    const shown = await capturedRun([
      "models",
      "show",
      PROBE_PROFILE.profile_id,
      "--json",
    ]);
    expect(shown.code).toBe(0);
    expect(JSON.parse(shown.stdout).profile.profile_id).toBe(
      PROBE_PROFILE.profile_id,
    );
  });

  it("preflights support, posts once, and reconciles repeated apply by GET", async () => {
    transport.get.mockResolvedValue({
      status: 200,
      data: [PROBE_PROFILE],
    });
    const preview = await capturedRun([
      "models",
      "probe-plan",
      PROBE_PROFILE.profile_id,
      "--json",
    ]);
    expect(preview.code).toBe(0);
    const previewDocument = JSON.parse(preview.stdout);
    expect(previewDocument).toMatchObject({
      state: "preview",
      plan: {
        kind: "model_profile_probe",
        profile_id: PROBE_PROFILE.profile_id,
        expected_profile_revision: 3,
      },
    });
    const operationId = previewDocument.plan.operation_id;
    const receipt = probeReceipt(operationId);
    const planFile = path.join(directory, "probe-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    transport.get.mockImplementation(async (url: string) =>
      url === `/api/v1/model-probe-operations/${operationId}`
        ? {
            status: 200,
            data:
              transport.post.mock.calls.length === 0
                ? probeNotFound(operationId)
                : receipt,
          }
        : { status: 404, data: {} },
    );
    transport.post.mockResolvedValue({ status: 200, data: receipt });

    const first = await capturedRun([
      "models",
      "probe",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(first.code).toBe(0);
    expect(JSON.parse(first.stdout).state).toBe("completed");

    const second = await capturedRun([
      "models",
      "probe",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(second.code).toBe(0);
    expect(JSON.parse(second.stdout).state).toBe("completed");
    expect(transport.post).toHaveBeenCalledTimes(1);
    expect(transport.post).toHaveBeenCalledWith(
      `/api/v1/model-profiles/${PROBE_PROFILE.profile_id}/probe`,
      {
        operation_id: operationId,
        expected_profile_revision: 3,
      },
      undefined,
    );
  });

  it("keeps the command disabled on a legacy Core and does not probe", async () => {
    transport.get.mockResolvedValue({
      status: 200,
      data: [PROBE_PROFILE],
    });
    const preview = await capturedRun([
      "models",
      "probe-plan",
      PROBE_PROFILE.profile_id,
      "--json",
    ]);
    const planFile = path.join(directory, "unsupported-probe-plan.json");
    await writeFile(planFile, preview.stdout, { mode: 0o600 });
    transport.get.mockResolvedValue({ status: 404, data: {} });
    const result = await capturedRun([
      "models",
      "probe",
      "--plan-file",
      planFile,
      "--confirm",
      "--json",
    ]);
    expect(result.code).toBe(1);
    expect(JSON.parse(result.stdout)).toMatchObject({
      state: "disabled",
      code: "model_probe_operations_unsupported",
    });
    expect(transport.post).not.toHaveBeenCalled();
  });
});

async function modelPlanFile(): Promise<string> {
  const configFile = path.join(directory, "model.json");
  await writeFile(
    configFile,
    JSON.stringify({
      name: "Synthetic",
      provider_kind: "openai_compatible",
      base_url: "https://example.invalid/v1",
      model: "synthetic-model",
    }),
  );
  const preview = await capturedRun([
    "models",
    "plan",
    "--config-file",
    configFile,
    "--json",
  ]);
  const planFile = path.join(directory, "model-plan.json");
  await writeFile(planFile, preview.stdout, { mode: 0o600 });
  vi.clearAllMocks();
  runtime.inspectRuntimeStatus.mockResolvedValue(RUNNING);
  runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
  transport.post.mockResolvedValue({ status: 200, data: PROFILE });
  return planFile;
}

function probeNotFound(operationId: string) {
  return {
    schema_version: 1,
    operation_id: operationId,
    profile_id: null,
    expected_profile_revision: null,
    state: "not_found",
    result: null,
    code: null,
    stale: null,
  };
}

function probeReceipt(operationId: string) {
  return {
    schema_version: 1,
    operation_id: operationId,
    profile_id: PROBE_PROFILE.profile_id,
    expected_profile_revision: 3,
    state: "completed",
    result: {
      profile_id: PROBE_PROFILE.profile_id,
      profile_revision: 3,
      input_profile_revision: 3,
      stages: [
        {
          stage: "authentication",
          ok: false,
          code: "missing_api_key",
          latency_ms: 0,
          embedding_dimensions: null,
        },
      ],
      capabilities: {
        endpoint_reachable: false,
        model_available: false,
        structured_output: false,
        embedding_available: false,
      },
    },
    code: null,
    stale: false,
  };
}

function importJob() {
  return {
    job_id: "job-1",
    user_id: "local",
    source_id: "codex",
    operation: "history",
    status: "pending",
    phase: "discover",
    checkpoint: null,
    discovered: 0,
    discovered_targets: 0,
    emitted: 0,
    stored: 0,
    revised: 0,
    merged: 0,
    skipped: 0,
    errors: 0,
    created_at: "T1",
    updated_at: "T1",
  };
}

async function capturedRun(argv: string[]) {
  let stdout = "";
  let stderr = "";
  const originalOut = process.stdout.write;
  const originalError = process.stderr.write;
  process.stdout.write = ((chunk: string) => {
    stdout += chunk;
    return true;
  }) as typeof process.stdout.write;
  process.stderr.write = ((chunk: string) => {
    stderr += chunk;
    return true;
  }) as typeof process.stderr.write;
  try {
    const code = await run(argv, {});
    return { code, stdout, stderr };
  } finally {
    process.stdout.write = originalOut;
    process.stderr.write = originalError;
  }
}
