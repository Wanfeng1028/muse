import { createHash } from "node:crypto";
import { extname, join } from "node:path";
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";
import {
  ArtifactManifestSchema,
  ArtifactRevisionSchema,
  HarnessIdSchema,
  WorkResourceIdSchema,
  WorkManifestSchema,
  type ArtifactManifest,
  type ArtifactRevision,
  type WorkManifest,
} from "./contracts.js";
import { WORKS_DIRECTORY, WORK_MANIFEST_FILE } from "./work-store.js";

export async function stageArtifactRevision(input: {
  readonly projectRoot: string;
  readonly manifest: WorkManifest;
  readonly artifactId: string;
  readonly artifactKind: string;
  readonly revisionId: string;
  readonly content: string | Uint8Array;
  readonly contentType: string;
  readonly fileName: string;
  readonly episodeId?: string;
  readonly createdAt?: string;
  readonly promote?: boolean;
}): Promise<{ readonly manifest: WorkManifest; readonly revision: ArtifactRevision }> {
  const manifest = WorkManifestSchema.parse(input.manifest);
  const artifactId = WorkResourceIdSchema.parse(input.artifactId);
  const artifactKind = HarnessIdSchema.parse(input.artifactKind);
  const revisionId = HarnessIdSchema.parse(input.revisionId);
  const extension = extname(input.fileName);
  if (!extension || !/^\.[a-z0-9._-]+$/i.test(extension)) {
    throw new Error(`Artifact revision fileName must have a safe extension: ${input.fileName}`);
  }
  const bytes = typeof input.content === "string" ? Buffer.from(input.content) : Buffer.from(input.content);
  const path = join("artifacts", artifactId, "revisions", `${revisionId}${extension}`);
  const revision = ArtifactRevisionSchema.parse({
    id: revisionId,
    parentRevisionId: currentRevisionId(manifest, artifactId),
    path,
    contentType: input.contentType,
    status: input.promote ? "current" : "candidate",
    checksum: `sha256:${createHash("sha256").update(bytes).digest("hex")}`,
    byteLength: bytes.byteLength,
    episodeId: input.episodeId,
    createdAt: input.createdAt ?? new Date().toISOString(),
  });
  const artifacts = upsertArtifact(manifest.artifacts, {
    id: artifactId,
    kind: artifactKind,
    currentRevisionId: input.promote ? revisionId : currentRevisionId(manifest, artifactId),
    revisions: [
      ...(manifest.artifacts.find((artifact) => artifact.id === artifactId)?.revisions ?? []).map((item) => (
        input.promote && item.status === "current" ? { ...item, status: "superseded" as const } : item
      )),
      revision,
    ],
    metadata: manifest.artifacts.find((artifact) => artifact.id === artifactId)?.metadata ?? {},
  });
  const nextManifest = WorkManifestSchema.parse({
    ...manifest,
    artifacts,
    updatedAt: revision.createdAt,
  });
  await commitAtomicFileSet({
    rootDir: input.projectRoot,
    writes: [
      { relativePath: join(WORKS_DIRECTORY, manifest.id, path), content: bytes },
      {
        relativePath: join(WORKS_DIRECTORY, manifest.id, WORK_MANIFEST_FILE),
        content: `${JSON.stringify(nextManifest, null, 2)}\n`,
      },
    ],
  });
  return { manifest: nextManifest, revision };
}

export function createCurrentArtifact(input: {
  readonly artifactId: string;
  readonly artifactKind: string;
  readonly revisionId?: string;
  readonly path: string;
  readonly content: string | Uint8Array;
  readonly contentType: string;
  readonly createdAt: string;
  readonly episodeId?: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}): ArtifactManifest {
  const artifactId = WorkResourceIdSchema.parse(input.artifactId);
  const artifactKind = HarnessIdSchema.parse(input.artifactKind);
  const revisionId = HarnessIdSchema.parse(input.revisionId ?? "initial");
  const bytes = typeof input.content === "string" ? Buffer.from(input.content) : Buffer.from(input.content);
  const revision = ArtifactRevisionSchema.parse({
    id: revisionId,
    parentRevisionId: null,
    path: input.path,
    contentType: input.contentType,
    status: "current",
    checksum: `sha256:${createHash("sha256").update(bytes).digest("hex")}`,
    byteLength: bytes.byteLength,
    episodeId: input.episodeId,
    createdAt: input.createdAt,
  });
  return ArtifactManifestSchema.parse({
    id: artifactId,
    kind: artifactKind,
    currentRevisionId: revision.id,
    revisions: [revision],
    metadata: input.metadata ?? {},
  });
}

export async function promoteArtifactRevision(input: {
  readonly projectRoot: string;
  readonly manifest: WorkManifest;
  readonly artifactId: string;
  readonly revisionId: string;
  readonly updatedAt?: string;
}): Promise<WorkManifest> {
  const manifest = WorkManifestSchema.parse(input.manifest);
  const artifactId = WorkResourceIdSchema.parse(input.artifactId);
  const revisionId = HarnessIdSchema.parse(input.revisionId);
  const artifact = manifest.artifacts.find((candidate) => candidate.id === artifactId);
  if (!artifact) throw new Error(`Unknown artifact: ${artifactId}`);
  if (!artifact.revisions.some((revision) => revision.id === revisionId)) {
    throw new Error(`Unknown artifact revision: ${artifactId}.${revisionId}`);
  }
  const updatedAt = input.updatedAt ?? new Date().toISOString();
  const nextArtifact = ArtifactManifestSchema.parse({
    ...artifact,
    currentRevisionId: revisionId,
    revisions: artifact.revisions.map((revision) => {
      if (revision.id === revisionId) return { ...revision, status: "current" };
      return revision.status === "current" ? { ...revision, status: "superseded" } : revision;
    }),
  });
  const nextManifest = WorkManifestSchema.parse({
    ...manifest,
    artifacts: upsertArtifact(manifest.artifacts, nextArtifact),
    updatedAt,
  });
  await commitAtomicFileSet({
    rootDir: input.projectRoot,
    writes: [{
      relativePath: join(WORKS_DIRECTORY, manifest.id, WORK_MANIFEST_FILE),
      content: `${JSON.stringify(nextManifest, null, 2)}\n`,
    }],
  });
  return nextManifest;
}

function currentRevisionId(manifest: WorkManifest, artifactId: string): string | null {
  return manifest.artifacts.find((artifact) => artifact.id === artifactId)?.currentRevisionId ?? null;
}

function upsertArtifact(
  artifacts: ReadonlyArray<ArtifactManifest>,
  next: ArtifactManifest,
): ArtifactManifest[] {
  const found = artifacts.some((artifact) => artifact.id === next.id);
  return found
    ? artifacts.map((artifact) => artifact.id === next.id ? next : artifact)
    : [...artifacts, next];
}
