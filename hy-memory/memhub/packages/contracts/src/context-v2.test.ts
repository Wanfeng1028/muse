import { expect, expectTypeOf, it } from "vitest";
import type { ContextSearchRequest } from "./context";
import type {
  ContextRequestV2,
  ContextSearchRequestV2,
  EvidenceItemV2,
  RetrievalResponseV2,
} from "./context-v2";

it("keeps v2 explicit and v1 search unchanged at the type boundary", () => {
  const search: ContextSearchRequestV2 = {
    query: "昨天的设计链接",
    enhancement: "local",
    intent: "artifact",
  };
  const expand: ContextRequestV2 = {
    operation: "expand",
    expand_ref: "opaque-ref",
    message_limit: 4,
  };
  expect(search.enhancement).toBe("local");
  expect(expand.operation).toBe("expand");
  expectTypeOf<ContextSearchRequest>().not.toHaveProperty("intent");
  expectTypeOf<ContextSearchRequestV2>().not.toHaveProperty("user_id");
  expectTypeOf<ContextSearchRequestV2>().not.toHaveProperty("workspace_path");
});

it("distinguishes evidence identity and does not turn retrieval into adoption", () => {
  type Raw = Extract<EvidenceItemV2, { kind: "raw" }>;
  type Memory = Extract<EvidenceItemV2, { kind: "memory" }>;
  expectTypeOf<Raw>().toHaveProperty("evidence_id");
  expectTypeOf<Raw>().not.toHaveProperty("memory_id");
  expectTypeOf<Memory>().toHaveProperty("memory_id");
  expectTypeOf<Memory>().not.toHaveProperty("spans");
  expectTypeOf<RetrievalResponseV2["schema_version"]>().toEqualTypeOf<2>();
  expectTypeOf<RetrievalResponseV2["adoption"]>().toEqualTypeOf<"unknown">();
});
