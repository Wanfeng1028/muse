// @vitest-environment jsdom

import type { ModelProfileInput } from "@one-memory/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fake = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock("axios", () => ({
  default: {
    create: () => ({ ...fake, interceptors: { request: { use: vi.fn() } } }),
    isAxiosError: () => false,
  },
}));

import { createModelProfile } from "./api";

const OP = "11111111-2222-4333-8444-555555555555";

function input(patch: Partial<ModelProfileInput> = {}): ModelProfileInput {
  return {
    name: "Isolated model",
    provider_kind: "openai_compatible",
    base_url: "https://generation.example/v1",
    model: "generation-model",
    timeout_seconds: 30,
    max_concurrency: 1,
    ...patch,
  };
}

function profile() {
  return {
    profile_id: "22222222-3333-4444-8555-666666666666",
    name: "Isolated model",
    provider_kind: "openai_compatible",
    base_url: "https://generation.example/v1",
    model: "generation-model",
    embedding_model: null,
    embedding_provider_kind: null,
    embedding_base_url: null,
    embedding_dimensions: null,
    has_api_key: false,
    credential_state: "missing",
    timeout_seconds: 30,
    max_concurrency: 1,
    context_window: null,
    disable_thinking: false,
    capabilities: {
      endpoint_reachable: false,
      model_available: false,
      structured_output: false,
      embedding_available: false,
    },
    revision: 1,
    is_active: false,
    created_at: "2026-09-19T00:00:00Z",
    updated_at: "2026-09-19T00:00:01Z",
  };
}

beforeEach(() => vi.clearAllMocks());

describe("createModelProfile keeps the creation id out of the reviewable config", () => {
  it("sends a POST instead of rejecting its own config", async () => {
    // The caller supplies the durable creation id on the input, exactly as the
    // hook does. The shared builder refuses `creation_operation_id` *inside*
    // config, so the transport must lift it out; before this, every create
    // threw `creation_operation_id_not_allowed` and no request was ever sent.
    fake.post.mockResolvedValueOnce({ data: profile() });
    await expect(
      createModelProfile(
        { ...input(), creation_operation_id: OP },
        "aaaaaaa1-bbbb-4ccc-8ddd-eeeeeeeeeeee",
      ),
    ).resolves.toEqual(profile());
    expect(fake.post).toHaveBeenCalledOnce();
  });

  it("sends the id as a top-level field and never inside the config", async () => {
    fake.post.mockResolvedValueOnce({ data: profile() });
    await createModelProfile({ ...input(), creation_operation_id: OP });
    const [path, body] = fake.post.mock.calls[0];
    expect(path).toBe("/api/v1/model-profiles");
    expect(body.creation_operation_id).toBe(OP);
    expect(body).not.toHaveProperty("api_key");
    expect(Object.keys(body).sort()).toEqual([
      "base_url",
      "creation_operation_id",
      "max_concurrency",
      "model",
      "name",
      "provider_kind",
      "timeout_seconds",
    ]);
  });

  it("still refuses a malformed or missing creation id", async () => {
    // The id is what makes a create reconcilable after a lost response; a
    // missing one must not silently become a request Core cannot de-duplicate.
    await expect(createModelProfile(input())).rejects.toThrow(
      "creation_operation_id_invalid",
    );
    await expect(
      createModelProfile({ ...input(), creation_operation_id: "short" }),
    ).rejects.toThrow("creation_operation_id_invalid");
    expect(fake.post).not.toHaveBeenCalled();
  });

  it("forwards a resolved credential as a top-level field, not in config", async () => {
    fake.post.mockResolvedValueOnce({ data: profile() });
    await createModelProfile({
      ...input(),
      creation_operation_id: OP,
      api_key: "sk-secret",
    });
    const body = fake.post.mock.calls[0][1];
    expect(body.api_key).toBe("sk-secret");
    expect(body.creation_operation_id).toBe(OP);
  });
});
